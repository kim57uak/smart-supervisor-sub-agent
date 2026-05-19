"""
[Sub-Agent] Port 정의 — Hexagonal Architecture의 추상화 계층
=============================================================
책임: Application Layer가 Adapter Layer에 요구하는 인터페이스(포트) 정의
아키텍처 위치: Ports Layer — Domain과 Adapter 사이의 경계 (DIP 준수)

Python Protocol 사용:
  - 구조적 서브타이핑 (Duck Typing)
  - 별도 상속 없이 인터페이스 충족 가능
  - IDE 자동 완성과 타입 검사 지원

Port 목록:
  OrchestrationEngine: LangGraph/Burr 엔진 추상화
  Planner: LLM 도구 선택 계획
  ToolExecutor: MCP 도구 실행
  Composer: LLM 최종 응답 생성
  Store: Redis 영속성
  TaskQueue: 작업 큐 (Reliable Queue 패턴)
  ProgressPublisher: 실시간 이벤트 발행
"""

from typing import Protocol, List, Dict, Any, AsyncIterator, Optional
from ..domain.models import PlanningContext, ToolPlan, AgentExecutionResult, AgentTask, AiChatChunk
from ..domain.enums import ProcessStatus

class OrchestrationEngine(Protocol):
    """
    오케스트레이션 엔진 포트.
    LangGraphAdapter / BurrAdapter가 이 프로토콜을 구현.
    execute()는 session_id + task_id + initial_state → final_state
    """
    async def execute(self, 
                      session_id: str, 
                      task_id: str, 
                      initial_state: Dict[str, Any]) -> Dict[str, Any]:
        ...

class Planner(Protocol):
    """LLM 기반 도구 선택 계획 수립 포트"""
    async def plan(self, context: PlanningContext) -> List[ToolPlan]: ...

class ToolExecutor(Protocol):
    """MCP 도구 실행 포트 — inputSchema 검증 포함"""
    async def execute(self, plan: ToolPlan, runtime_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]: ...

class Composer(Protocol):
    """LLM 기반 최종 응답 생성 포트 (스트리밍)"""
    async def stream_compose(self, context: PlanningContext) -> AsyncIterator[AiChatChunk]: ...

class Store(Protocol):
    """
    영속성 포트 — Redis CRUD + Idempotency.
    save_task: 낙관적 락(CAS) 기반 저장
    check_and_reserve_idempotency: 중복 요청 방지
    save_swarm_state: Swarm(Federation) 상태 저장
    """
    async def save_task(self, task: AgentTask) -> None: ...
    async def load_task(self, task_id: str) -> Optional[AgentTask]: ...
    async def check_and_reserve_idempotency(self, request_id: str, task_id: str) -> bool: ...
    async def update_task_status(self, task_id: str, status: ProcessStatus) -> None: ...
    async def save_swarm_state(self, session_id: str, state: Dict[str, Any]) -> None: ...
    async def load_swarm_state(self, session_id: str) -> Dict[str, Any]: ...
    async def save_message(self, session_id: str, message: Dict[str, Any]) -> None: ...
    async def get_messages(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]: ...

class TaskQueue(Protocol):
    """
    작업 큐 포트 — At-Least-Once Delivery 보장.
    BRPOPLPUSH + ACK/NACK 패턴 (Reliable Queue).
    """
    async def enqueue(self, task_data: Dict[str, Any]) -> None: ...
    async def dequeue(self, timeout: int = 10) -> Optional[Dict[str, Any]]: ...
    async def ack(self, task_data: Dict[str, Any]) -> None: ...
    async def nack(self, task_data: Dict[str, Any]) -> None: ...

class ProgressPublisher(Protocol):
    """실시간 진행 이벤트 발행 포트 (SSE → Redis Stream)"""
    async def publish(
        self, 
        session_id: str, 
        task_id: str, 
        event_data: Dict[str, Any],
        trace_id: Optional[str] = None
    ) -> None: ...
