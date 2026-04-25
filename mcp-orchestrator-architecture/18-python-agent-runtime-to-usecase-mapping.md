# 18. Python Agent Runtime To Usecase Mapping

Updated: 2026-04-25

## Planning

- `llm_planning_service`
  - `LangChain` structured output을 사용해 `tool_plan` 목록을 생성한다.
  - input
    - user message
    - history summary
    - scope allowlist
    - available tool schema

## Tool Execution

- `mcp_tool_execution_service`
  - planner가 선택한 `tool_plan`을 MCP adapter runtime으로 실행한다.
  - uses
    - `mcp_tool_registry`
    - `mcp_client_session_manager`
    - `mcp_transport_factory`

## Composition

- `llm_response_compose_service`
  - tool execution 결과와 history를 기반으로 최종 스트림을 생성한다.
  - MCP tool 재호출 없이 최종 문장만 생성한다.
  - output
    - `AsyncIterator[AiChatChunk]`

## Runtime

- `agent_llm_runtime`
  - provider 선택
  - sync / stream / structured 호출 추상화

## A2A

- A2A endpoint는 내부적으로 같은 `ai_chat_service -> agent_orchestrator` 경로를 재사용한다.
- 차이는 `a2a_execution_context`가 추가되고 lifecycle sync가 켜진다는 점이다.

## Python Stack Mapping

- request entry layer -> FastAPI router/endpoint
- application layer -> application service
- runtime settings layer -> settings object + dependency provider
- model runtime -> LangChain model runtime wrapper
- graph runtime -> LangGraph `StateGraph`
- async streaming layer -> `async def`, `AsyncIterator`, SSE stream
- typed schema model -> Pydantic model / dataclass

## Domain Mapping

- `weather`
  - weather MCP + provider compose
- `supply-cost`
  - supply-cost MCP + NDJSON chunk response 가능
- `reservation`
  - reservation MCP + create reservation tool plan
- `sale-product`
  - sale-product MCP + product tools
