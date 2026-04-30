# 18. Python Agent Runtime To Usecase Mapping

Updated: 2026-04-29 (Aligned with Final Class Names)

## Planning

- **`LlmPlanner`**
  - `LangChain` structured output을 사용해 `ToolPlan` 목록을 생성한다.
  - input: `PlanningContext` (history, available_tools, etc.)

## Tool Execution

- **`McpExecutor`**
  - Planner가 선택한 `ToolPlan`을 MCP adapter runtime으로 실행한다.
  - uses: `McpToolRegistry`, `McpClientSessionManager`, `McpTransport`

## Composition

- **`LlmComposer`**
  - Tool execution 결과와 history를 기반으로 최종 스트림을 생성한다.
  - MCP tool 재호출 없이 최종 문장만 생성한다.
  - output: `AsyncIterator[AiChatChunk]`

## Runtime

- **`LlmRuntime`**
  - Provider(OpenAI, Anthropic 등) 선택 및 호출 추상화.

## A2A

- A2A endpoint는 내부적으로 **`AgentChatUseCase`** -> **`AgentExecutor`** 경로를 재사용한다.
- `a2a_handler.py`에서 JSON-RPC 요청을 표준 메서드(SendMessage 등)로 변환하여 처리한다.

## Python Stack Mapping

- request entry layer -> FastAPI router (`api/`)
- application layer -> UseCase / Service (`application/execution`)
- persistence layer -> `AgentPersistence` / `StateCoordinator`
- read layer -> `AgentReader`
- model runtime -> `LlmRuntime`
- graph runtime -> LangGraph `StateGraph` (`WorkflowFactory`)
- async streaming layer -> `async def`, `AsyncIterator`, SSE stream

## Domain Mapping (Scopes)

- **`weather`**: weather MCP tools
- **`supply-cost`**: supply-cost MCP tools
- **`reservation`**: reservation MCP tools
- **`sale-product`**: sale-product MCP tools
