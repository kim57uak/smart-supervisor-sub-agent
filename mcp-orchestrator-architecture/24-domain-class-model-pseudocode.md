# 24. Domain Class Model And Implementation Pseudocode

Updated: 2026-04-25

## Purpose

이 문서는 Python 기반 agentic MCP runtime의 기준 사양서다.
현재 프로젝트의 MCP runtime 개념을 재사용하고, 그 위에 `FastAPI + LangChain + LangGraph + A2A + Redis` 계층을 추가하는 방식으로 작성한다.

## Architecture Principles

- 상위 계층은 interface와 factory를 통해 하위 구현을 사용한다.
- prompt, Redis key, tool property, lifecycle mapping은 공용 서비스/정책 객체로 분리한다.
- `conversation_store`, `graph_checkpoint_store`, `a2a_task_store`는 상위 계층에서 repository 역할의 store port로 사용한다.
- planning, execute, compose, store, runtime, lifecycle를 분리한다.
- 기존 MCP registry/session/transport 개념은 Python adapter로 감싼다.
- 내부 naming은 `snake_case`를 기준으로 한다.

## Package Layout

```text
src/app
├── api
│   ├── agent
│   ├── a2a
│   └── support
├── application
│   ├── agent
│   │   ├── plan
│   │   ├── execute
│   │   ├── compose
│   │   ├── runtime
│   │   ├── auth
│   │   └── security
│   └── prompt
├── domain
│   └── agent
├── infrastructure
│   ├── mcp
│   ├── redis
│   ├── settings
│   └── llm
└── a2a
    ├── dto
    ├── mapper
    ├── task
    └── lifecycle
```

## Representative Contracts

```python
class AgentChatRequest(BaseModel):
    session_id: str
    request_id: str
    trace_id: str | None = None
    scope_name: str
    user_message: str


class planning_service(Protocol):
    async def plan(self, context: PlanningContext) -> list[ToolPlan]: ...


class tool_execution_service(Protocol):
    async def execute(self, context: PlanningContext) -> PlanningContext: ...


class response_compose_service(Protocol):
    async def stream_compose(self, context: PlanningContext) -> AsyncIterator[AiChatChunk]: ...
```

## Implementation Notes

- `agent_orchestrator`는 LangGraph state machine을 실행하고 compose 단계만 별도로 스트리밍한다.
- compose 단계에서는 MCP tool 재호출을 금지한다.
- `request_id` 기본 소스는 A2A JSON-RPC `id`다.
- Redis key에는 `session_id`를 포함하되, correlation의 대체 수단으로 보지 않는다.
- compatibility layer에서만 legacy field alias를 매핑한다.
