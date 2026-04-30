# 24. Domain Class Model And Implementation Pseudocode

Updated: 2026-04-29 (Final Synchronization with Source Code)

## Purpose

이 문서는 Python 기반 agentic MCP runtime(Sub-agent)의 최종 구현 사양서다.
모든 의사코드는 `src/sub-agent`의 실제 구현 로직과 일치한다.

## Architecture Principles

- **Separation of Concerns**: API, Application, Infrastructure를 명확히 분리.
- **Hexagonal Architecture**: 도메인 로직은 `ports`에 의존하고, 구체 기술은 `adapters`에서 구현.
- **Decoupled Execution**: API는 작업 접수(`enqueue`)만 담당, 실제 실행은 워커가 수행.
- **Centralized Config**: Pydantic Settings를 이용한 설정 관리.

## Package Layout (Final)

```text
src/sub-agent/app
├── adapters/         # Implementation of Ports (Redis, LLM, MCP, Orchestration)
│   ├── llm/          # LlmPlanner, LlmComposer
│   ├── mcp/          # McpExecutor
│   ├── orchestration/ # WorkflowFactory
│   └── store/        # RedisAdapter (Store, TaskQueue, ProgressPublisher 구현)
├── api/              # FastAPI Routers (chat.py, discovery.py, stream.py)
├── application/      # Business Logic (CQRS)
│   ├── execution/    # AgentChatUseCase, AgentExecutor, WorkerExecutionService
│   ├── persistence/  # AgentPersistence, StateCoordinator
│   └── read/         # AgentReader
├── ports/            # Abstract Interface Definitions (interfaces.py)
├── domain/           # Entities (models.py), Enums (enums.py)
├── infrastructure/   # RedisClient, LlmRuntime
└── core/             # Centralized Settings (config.py, dependencies.py)
```

## Representative Contracts (Ports)

```python
class Store(Protocol):
    async def save_task(self, task: AgentTask) -> None: ...
    async def check_and_reserve_idempotency(self, request_id: str, task_id: str) -> bool: ...

class TaskQueue(Protocol):
    async def enqueue(self, task_data: Dict[str, Any]) -> None: ...
    async def dequeue(self) -> Dict[str, Any]: ...

class Planner(Protocol):
    async def plan(self, context: PlanningContext) -> List[ToolPlan]: ...
```

## Implementation Flow (Final)

1.  **API (`AgentChatUseCase`)**:
    *   `request_id` 기반 멱등성 체크.
    *   `AgentTask` 초기 상태 저장 (`AgentPersistence`).
    *   `TaskQueue`에 작업 데이터 주입.
2.  **Worker (`WorkerExecutionService`)**:
    *   큐에서 작업 데이터를 꺼내 **`AgentExecutor`** 호출.
    *   **`WorkflowFactory`**를 통해 LangGraph 실행.
    *   `Planning -> Tool Execution -> Compose` 단계를 순차 수행.
    *   **`ProgressPublisher`**를 통해 Redis Stream으로 이벤트 발행.
    *   최종 상태를 저장하고 종료.

## Implementation Guidelines

- **Traceability**: 모든 로그와 Redis 이벤트에 `trace_id`를 강제 포함.
- **Centralized Prompts**: `prompts.yml`에서 템플릿을 읽어 실시간 치환.
- **Enum-First**: 모든 상태 및 역할 정의는 `enums.py`를 사용.
