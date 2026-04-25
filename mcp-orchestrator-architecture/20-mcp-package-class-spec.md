# 20. MCP Package / Class Specification

Updated: 2026-04-25
Source baseline: `src/app`

## Target Baseline

이 문서는 `mcp-orchestrator` 아키텍처를 Python 기준으로 정의한다.

- 공통 기반
  - `Python 3.11+ + FastAPI + LangChain + LangGraph + A2A + Redis`
- 핵심 책임
  - scope별 MCP tool orchestration
  - auth / allowlist / idempotency
  - conversation / checkpoint / task persistence
  - unary / streaming / A2A 응답 경계

## Folder Rule

- 최상위 애플리케이션 패키지는 `app`을 유지한다.
- `api`, `application`, `domain`, `a2a`, `infrastructure`, `common`은 최상위 역할 패키지다.
- Python 내부 구현 명칭은 `snake_case`를 기준으로 한다.
- 클래스명이 필요할 때만 `PascalCase`를 사용한다.
- 외부 A2A 계약 alias만 compatibility layer에서 PascalCase 또는 legacy field alias 원문을 유지할 수 있다.

## New Packages

- `app/api/agent`
- `app/api/a2a`
- `app/application/agent`
- `app/application/agent/plan`
- `app/application/agent/execute`
- `app/application/agent/compose`
- `app/application/agent/runtime`
- `app/application/agent/security`
- `app/application/agent/auth`
- `app/application/agent/persistence`
- `app/application/prompt`
- `app/domain/agent`
- `app/infrastructure/mcp`
- `app/infrastructure/redis`
- `app/infrastructure/settings`
- `app/infrastructure/llm`
- `app/a2a/dto`
- `app/a2a/mapper`
- `app/a2a/task`

## New Modules / Components

- `agent_endpoint`
- `a2a_agent_endpoint`
- `agent_card_endpoint`
- `agent_authorization_service`
- `session_scope_authorization_service`
- `ai_chat_service`
- `agent_scope_resolver`
- `agent_request_factory`
- `agent_orchestrator`
- `tool_catalog_service`
- `llm_planning_service`
- `mcp_tool_execution_service`
- `response_compose_service`
- `agent_llm_runtime`
- `conversation_store`
- `graph_checkpoint_store`
- `a2a_task_store`
- `request_idempotency_policy`
- `agent_trace_propagation_service`
- `redis_store_facade`
- `redis_key_factory`
- `redis_ttl_policy`
- `mcp_tool_registry`
- `mcp_client_session_manager`
- `mcp_transport_factory`

## Key Contracts

- `ai_chat_service.stream_agent_chat(request) -> AsyncIterator[AiChatChunk]`
- `ai_chat_service.execute_agent_for_a2a(request) -> AgentExecutionResult`
- `agent_orchestrator.execute(request) -> AsyncIterator[AiChatChunk]`
- `agent_orchestrator.execute_to_result(request) -> AgentExecutionResult`
- `llm_planning_service.plan(context) -> list[ToolPlan]`
- `tool_catalog_service.load_scoped_tools(scope) -> list[ToolDefinition]`
- `mcp_tool_execution_service.execute(context) -> PlanningContext`
- `response_compose_service.stream_compose(context) -> AsyncIterator[AiChatChunk]`
- `conversation_store.load/save/clear`
- `graph_checkpoint_store.load/save/clear`
- `a2a_task_store.create/get/mark_running/mark_completed/mark_failed/cancel`

## Dependency Policy

- `agent_endpoint -> agent_authorization_service -> ai_chat_service`
- `a2a_agent_endpoint -> agent_authorization_service + ai_chat_service + a2a_task_store + a2a_response_mapper`
- `ai_chat_service -> agent_orchestrator`
- `agent_orchestrator -> tool_catalog_service + llm_planning_service + mcp_tool_execution_service + response_compose_service`
- `agent_orchestrator -> conversation_store + graph_checkpoint_store + request_idempotency_policy`
- `mcp_tool_execution_service -> mcp_tool_registry + mcp_client_session_manager + mcp_transport_factory`
- `conversation_store/graph_checkpoint_store/a2a_task_store -> redis_store_facade`

## Naming And Architecture Rule

- Python에서 과거 계층형 CRUD 구조를 그대로 복제하는 것은 권장하지 않는다.
- 내부 문서와 구현은 `endpoint -> application -> domain -> infrastructure`로 설명한다.
- `repository` 대신 `store`, `gateway`, `client`, `adapter`처럼 역할 중심 명칭을 우선한다.
