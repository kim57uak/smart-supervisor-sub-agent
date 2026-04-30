# 25. Agentic Implementation Priority

Updated: 2026-04-25

## P0. Runtime Protection

- `Work Package A. Runtime Protection`을 최우선으로 구현한다.
- `P0. Guardrails And Runtime Limits` 항목을 즉시 반영한다.
- `Operational Safety And Resilience` 항목을 즉시 반영한다.
- runtime 관련 값(timeout/iteration/token/tool-call/concurrency/parallel-tool)은 `settings/agent.yml`로 외부화한다.
- request correlation(`trace_id + request_id + session_id`)을 endpoint -> orchestrator -> runtime -> store/log까지 전달한다.
- `trace_id`, `request_id`, `session_id`는 supervisor 전달값을 우선 사용하고 누락 시에만 생성한다.
- tool 병렬 호출은 기본 비활성(`enabled=false`, `max_parallel_tool_calls=1`)로 시작한다.

## P1. Keep Existing MCP Runtime Concepts

- 현재 MCP runtime의 registry/session/transport 개념은 재사용한다.
- 새 구현은 이 계층을 교체하지 않고 Python adapter로 감싼다.

## P2. Agent Core First

- `agent_chat_request`
- `agent_scope`
- `planning_context`
- `tool_plan`
- `tool_execution_result`
- `agent_orchestrator`

## P3. LangGraph

- graph factory
- node definitions
- loop guard
- checkpoint integration

## P4. Redis Stores

- conversation store
- checkpoint store
- A2A task store

## P5. Endpoint Refactor

- endpoint support 계층 도입
- prompt/history 조립 공통화
- request validation 추가

## P6. A2A

- DTO
- endpoint
- lifecycle
- response mapping
