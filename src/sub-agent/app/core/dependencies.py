"""
[Sub-Agent] 의존성 주입 컨테이너 — Factory Functions + FastAPI Depends
====================================================================
책임: 모든 Adapter/Service/UseCase 인스턴스 생성과 Wiring을 중앙 관리
아키텍처 위치: Core / DI Layer (Hexagonal Architecture의 Composition Root)

원칙:
  1. Global Shared Infrastructure: MCP Transport Factory는 싱글톤으로 공유
  2. Factory Functions: FastAPI Depends 없이 독립적으로 사용 가능
  3. FastAPI Depends Wrappers: Factory Functions를 FastAPI 라우터에서 사용할 수 있게 wrapping
  4. Cache Layer: MCP Tool Registry는 재사용 (초기화 비용 절감)

주의:
  - create_redis_adapter()는 호출마다 새 Redis 연결 생성 → 연결 풀 관리 검토 필요
  - 두 Orchestration Engine(LangGraph/Burr)를 create_orchestration_engine()에서 switch
"""

import structlog
from typing import Any, Optional

from fastapi import Depends
from .config import settings
from ..infrastructure.redis_client import get_redis
from ..domain.enums import OrchestrationEngineType

logger = structlog.get_logger(__name__)

from ..adapters.store.redis_store import RedisAdapter
from ..adapters.mcp.mcp_tool_registry import McpToolRegistry
from ..adapters.mcp.mcp_adapters import McpExecutor
from ..adapters.llm.llm_adapters import LlmPlanner, LlmComposer
from ..adapters.mcp.mcp_infrastructure import McpTransportFactory, McpClientSessionManager
from ..adapters.orchestration.langgraph_factory import WorkflowFactory
from ..adapters.orchestration.langgraph_adapter import LangGraphAdapter
from ..adapters.orchestration.burr_factory import BurrWorkflowFactory
from ..adapters.orchestration.burr_adapter import BurrAdapter

from ..application.execution.chat_usecase import AgentChatUseCase
from ..application.execution.executor import AgentExecutor
from ..application.execution.worker import WorkerExecutionService
from ..application.persistence.agent_persistence import AgentPersistence
from ..application.read.agent_read_facade import AgentReader

from ..services.agent_authorization_service import AgentAuthorizationService

# ============================================================
# 전역 공유 인프라 (싱글톤)
# ============================================================
_mcp_tool_registry: Optional[McpToolRegistry] = None
_mcp_transport_factory = McpTransportFactory()

# ============================================================
# Factory Functions (FastAPI 비의존)
# Worker 프로세스에서도 동일한 생성 로직 재사용 목적
# ============================================================

async def create_redis_adapter() -> RedisAdapter:
    """RedisStore/TaskQueue/ProgressPublisher 통합 어댑터 생성"""
    return RedisAdapter(settings.redis_url)

async def create_mcp_tool_registry() -> McpToolRegistry:
    """MCP 도구 레지스트리 (싱글톤 캐싱) — 첫 호출 시 전체 MCP 서버에서 도구 목록 실시간 수집"""
    global _mcp_tool_registry
    if _mcp_tool_registry is None:
        _mcp_tool_registry = McpToolRegistry(_mcp_transport_factory)
        await _mcp_tool_registry.refresh_tools()
    return _mcp_tool_registry

async def create_mcp_session_manager() -> McpClientSessionManager:
    """MCP 클라이언트 세션 관리자 생성"""
    return McpClientSessionManager(_mcp_transport_factory)

async def create_tool_executor() -> McpExecutor:
    """MCP 도구 실행기 생성 (Registry + SessionManager 조합)"""
    registry = await create_mcp_tool_registry()
    sessions = await create_mcp_session_manager()
    return McpExecutor(registry, sessions)

async def create_workflow_factory() -> WorkflowFactory:
    """LangGraph 워크플로 팩토리 생성"""
    planner = LlmPlanner()
    executor = await create_tool_executor()
    composer = LlmComposer()
    adapter = await create_redis_adapter()
    registry = await create_mcp_tool_registry()
    return WorkflowFactory(planner, executor, composer, adapter, registry)

async def create_burr_factory() -> BurrWorkflowFactory:
    """Burr 워크플로 팩토리 생성"""
    planner = LlmPlanner()
    executor = await create_tool_executor()
    composer = LlmComposer()
    adapter = await create_redis_adapter()
    registry = await create_mcp_tool_registry()
    return BurrWorkflowFactory(planner, executor, composer, adapter, registry)

async def create_orchestration_engine() -> Any:
    """
    설정에 따라 Orchestration Engine 선택 생성
    - BURR → BurrAdapter
    - 기본값 → LangGraphAdapter
    """
    engine_type = settings.orchestration_engine
    
    if engine_type == OrchestrationEngineType.BURR:
        factory = await create_burr_factory()
        return BurrAdapter(factory)
    
    factory = await create_workflow_factory()
    return LangGraphAdapter(factory)

async def create_agent_executor() -> AgentExecutor:
    """AgentExecutor 생성 (Engine + Persistence + Publisher)"""
    engine = await create_orchestration_engine()
    adapter = await create_redis_adapter()
    persistence = AgentPersistence(adapter)
    return AgentExecutor(engine, persistence, adapter)

async def create_worker_service() -> WorkerExecutionService:
    """
    Worker 전용 서비스 생성.
    FastAPI Depends 없이 독립 프로세스(worker.py)에서 직접 호출.
    """
    adapter = await create_redis_adapter()
    executor = await create_agent_executor()
    
    logger.info("instantiating_worker_service", 
                adapter_type=str(type(adapter)), 
                executor_type=str(type(executor)))
                
    return WorkerExecutionService(
        task_queue=adapter,
        executor=executor,
        publisher=adapter
    )

# ============================================================
# FastAPI Dependency Injection Wrappers
# FastAPI 라우터에서 Depends()로 주입받기 위한 async 함수들
# ============================================================

async def get_redis_adapter() -> RedisAdapter:
    return await create_redis_adapter()

async def get_mcp_tool_registry() -> McpToolRegistry:
    return await create_mcp_tool_registry()

async def get_mcp_session_manager() -> McpClientSessionManager:
    return await create_mcp_session_manager()

async def get_tool_executor(
    registry: McpToolRegistry = Depends(get_mcp_tool_registry),
    sessions: McpClientSessionManager = Depends(get_mcp_session_manager)
) -> McpExecutor:
    return McpExecutor(registry, sessions)

async def get_planner() -> LlmPlanner:
    return LlmPlanner()

async def get_composer() -> LlmComposer:
    return LlmComposer()

async def get_persistence(
    adapter: RedisAdapter = Depends(get_redis_adapter)
) -> AgentPersistence:
    return AgentPersistence(adapter)

async def get_auth_service() -> AgentAuthorizationService:
    return AgentAuthorizationService(allowed_scopes=settings.a2a.scopes)

async def get_workflow_factory(
    planner: LlmPlanner = Depends(get_planner),
    executor: McpExecutor = Depends(get_tool_executor),
    composer: LlmComposer = Depends(get_composer),
    adapter: RedisAdapter = Depends(get_redis_adapter),
    registry: McpToolRegistry = Depends(get_mcp_tool_registry)
) -> WorkflowFactory:
    return WorkflowFactory(planner, executor, composer, adapter, registry)

async def get_burr_factory(
    planner: LlmPlanner = Depends(get_planner),
    executor: McpExecutor = Depends(get_tool_executor),
    composer: LlmComposer = Depends(get_composer),
    adapter: RedisAdapter = Depends(get_redis_adapter),
    registry: McpToolRegistry = Depends(get_mcp_tool_registry)
) -> BurrWorkflowFactory:
    return BurrWorkflowFactory(planner, executor, composer, adapter, registry)

async def get_orchestration_engine(
    engine_type: OrchestrationEngineType = settings.orchestration_engine,
    lg_factory: WorkflowFactory = Depends(get_workflow_factory),
    br_factory: BurrWorkflowFactory = Depends(get_burr_factory)
) -> Any:
    if engine_type == OrchestrationEngineType.BURR:
        return BurrAdapter(br_factory)
    return LangGraphAdapter(lg_factory)

async def get_agent_executor(
    engine: Any = Depends(get_orchestration_engine),
    persistence: AgentPersistence = Depends(get_persistence),
    adapter: RedisAdapter = Depends(get_redis_adapter)
) -> AgentExecutor:
    return AgentExecutor(engine, persistence, adapter)

async def get_agent_usecase(
    persistence: AgentPersistence = Depends(get_persistence),
    adapter: RedisAdapter = Depends(get_redis_adapter)
) -> AgentChatUseCase:
    return AgentChatUseCase(persistence, adapter)

async def get_worker_execution_service(
    adapter: RedisAdapter = Depends(get_redis_adapter),
    executor: AgentExecutor = Depends(get_agent_executor)
) -> WorkerExecutionService:
    return WorkerExecutionService(adapter, executor, adapter)

# worker.py 호환성 유지 (FastAPI Depends 없이 사용)
async def resolve_worker_service() -> WorkerExecutionService:
    return await create_worker_service()
