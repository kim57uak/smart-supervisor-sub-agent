import structlog
from typing import Any, Optional

from fastapi import Depends
from .config import settings
from ..infrastructure.redis_client import get_redis
from ..domain.enums import OrchestrationEngineType

logger = structlog.get_logger(__name__)


# Adapters
from ..adapters.store.redis_store import RedisAdapter
from ..adapters.mcp.mcp_tool_registry import McpToolRegistry
from ..adapters.mcp.mcp_adapters import McpExecutor
from ..adapters.llm.llm_adapters import LlmPlanner, LlmComposer
from ..adapters.mcp.mcp_infrastructure import McpTransportFactory, McpClientSessionManager
from ..adapters.orchestration.langgraph_factory import WorkflowFactory
from ..adapters.orchestration.langgraph_adapter import LangGraphAdapter
from ..adapters.orchestration.burr_factory import BurrWorkflowFactory
from ..adapters.orchestration.burr_adapter import BurrAdapter

# Use Cases & Application logic
from ..application.execution.chat_usecase import AgentChatUseCase
from ..application.execution.executor import AgentExecutor
from ..application.execution.worker import WorkerExecutionService
from ..application.persistence.agent_persistence import AgentPersistence
from ..application.read.agent_read_facade import AgentReader

# Domain Services
from ..services.agent_authorization_service import AgentAuthorizationService

# --- Global Shared Infrastructure ---
_mcp_tool_registry: Optional[McpToolRegistry] = None
_mcp_transport_factory = McpTransportFactory()

# --- Factory Functions (FastAPI Independent) ---
# Rationale (Why): Separating creation logic from FastAPI Depends to avoid NameErrors and attribute errors in standalone processes.

async def create_redis_adapter() -> RedisAdapter:
    return RedisAdapter(settings.redis_url)

async def create_mcp_tool_registry() -> McpToolRegistry:
    global _mcp_tool_registry
    if _mcp_tool_registry is None:
        _mcp_tool_registry = McpToolRegistry(_mcp_transport_factory)
        await _mcp_tool_registry.refresh_tools()
    return _mcp_tool_registry

async def create_mcp_session_manager() -> McpClientSessionManager:
    return McpClientSessionManager(_mcp_transport_factory)

async def create_tool_executor() -> McpExecutor:
    registry = await create_mcp_tool_registry()
    sessions = await create_mcp_session_manager()
    return McpExecutor(registry, sessions)

async def create_workflow_factory() -> WorkflowFactory:
    planner = LlmPlanner()
    executor = await create_tool_executor()
    composer = LlmComposer()
    adapter = await create_redis_adapter()
    registry = await create_mcp_tool_registry()
    return WorkflowFactory(planner, executor, composer, adapter, registry)

async def create_burr_factory() -> BurrWorkflowFactory:
    planner = LlmPlanner()
    executor = await create_tool_executor()
    composer = LlmComposer()
    adapter = await create_redis_adapter()
    registry = await create_mcp_tool_registry()
    return BurrWorkflowFactory(planner, executor, composer, adapter, registry)

async def create_orchestration_engine() -> Any:
    """
    Factory for creating the orchestration engine based on settings.
    """
    engine_type = settings.orchestration_engine
    
    if engine_type == OrchestrationEngineType.BURR:
        factory = await create_burr_factory()
        return BurrAdapter(factory)
    
    # Default: LANGGRAPH
    factory = await create_workflow_factory()
    return LangGraphAdapter(factory)

async def create_agent_executor() -> AgentExecutor:
    engine = await create_orchestration_engine()
    adapter = await create_redis_adapter()
    persistence = AgentPersistence(adapter)
    return AgentExecutor(engine, persistence, adapter)

async def create_worker_service() -> WorkerExecutionService:
    # Rationale (Why): Explicitly instantiating to avoid any FastAPI wrapper interference.
    adapter = await create_redis_adapter()
    executor = await create_agent_executor()
    
    # Debug: Confirming types at instantiation time
    logger.info("instantiating_worker_service", 
                adapter_type=str(type(adapter)), 
                executor_type=str(type(executor)))
                
    return WorkerExecutionService(
        task_queue=adapter,
        executor=executor,
        publisher=adapter
    )

# --- FastAPI Dependency Wrappers ---

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

# For compatibility with existing worker.py
async def resolve_worker_service() -> WorkerExecutionService:
    return await create_worker_service()
