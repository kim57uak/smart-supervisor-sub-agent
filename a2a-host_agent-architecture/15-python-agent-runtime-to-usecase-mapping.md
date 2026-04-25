# 15. Python Agent Runtime To Supervisor Usecase Mapping

Updated: 2026-04-25
Source baseline: `smart-supervisor supervisor target architecture`

## Supervisor Runtime Mapping

주의:

- 본 문서는 Python supervisor target architecture 기준이다.
- 파일명은 유지하지만 내용 기준선은 `LangChain + LangGraph + FastAPI`다.
- 레거시 `mcp` 경로는 기준선이 아니다.
- reservation은 direct endpoint/application-service 레거시가 아니라 downstream A2A agent + supervisor A2UI 연계 대상으로 본다.
- 신규 downstream agent는 `routing yml + agent card`만으로 planner/routing/invocation 대상이 되어야 한다.
- raw payload normalization과 A2UI rendering만 예외적으로 domain adapter를 허용한다.

- `supervisor_a2a_endpoint`
  - supervisor의 단일 A2A JSON-RPC 진입점이다.
  - unary, streaming, tasks, review endpoints를 FastAPI router에서 처리한다.
- `supervisor_a2a_request_validator`
  - `jsonrpc`, `method`, `params` 계약 검증과 send/review params 해석을 담당한다.
- `supervisor_agent_service`
  - 현재 use case entry service다.
  - pre-HITL A2UI shortcut, HITL gate, execution, review delegation을 조합한다.
- `supervisor_pre_hitl_a2ui_service`
  - planner 결과의 `__pre_hitl_a2ui` 힌트를 기반으로 실행 전 입력 A2UI를 먼저 띄운다.
- `hitl_gate_service`
  - planner의 `review_required` 결과와 waiting-review task 생성을 묶는 application service다.
  - planner review parse/runtime failure는 fail-open이 아니라 review-required 또는 명시적 오류로 수렴한다.
  - review 필요 시 planner 결과를 freeze해서 승인 대상 snapshot으로 만든다.
- `supervisor_execution_service`
  - sync/stream/review-resume 실행 경계다.
  - persistence용 최종 결과와 stream transport 이벤트를 분리한다.
- `supervisor_review_application_service`
  - approve/cancel review 흐름과 재실행을 담당한다.
  - approve는 raw request 재실행이 아니라 reviewed snapshot resume을 담당한다.
- `supervisor_read_facade`
  - supervisor read의 단일 진입점이다.
- `supervisor_agent_orchestrator`
  - graph execution, compose, persistence, failure translation을 총괄한다.
- `supervisor_graph_execution_service`
  - read facade를 통해 history/swarm/checkpoint/snapshot을 복원한 뒤 compiled LangGraph를 실행한다.
- `langgraph_supervisor_state_graph_factory`
  - 현재 graph node 순서:
    - `select`
    - `invoke`
    - `handoff_evaluate`
    - `handoff_apply`
    - `merge`
    - `compose`
- `default_a2a_invocation_service`
  - downstream agent 호출, retry/backoff, method fallback, per-agent circuit breaker를 담당한다.
  - agent별 하드코딩 분기 대신 registry + agent card 해석 결과를 기반으로 공통 호출 경로를 유지한다.
- `llm_supervisor_response_compose_service`
  - downstream 결과를 text 또는 A2UI payload로 합성한다.
- `default_supervisor_swarm_coordinator`
  - swarm state 기반 soft cooldown, invocation/handoff event log, shared facts 관리를 담당한다.

## Python Stack Mapping

- HTTP entry layer -> FastAPI router/endpoint
- application logic layer -> application service class/function
- runtime settings object -> settings object + dependency provider
- model runtime client -> `langchain_openai.ChatOpenAI` 또는 provider runtime wrapper
- graph runtime -> LangGraph `StateGraph`
- typed schema model -> Pydantic model
- async outbound client -> `httpx.AsyncClient`
- async stream contract -> `async def`, async iterator, SSE stream

## Generic Onboarding Rule

- 기본 경로:
  - 신규 agent 추가는 `supervisor.yml` routing 등록 + agent card 인식만으로 끝나야 한다.
- 코드 수정 없이 가능해야 하는 범위:
  - planner 후보 포함
  - allowlist 통과
  - method 선택
  - invoke
  - text compose 기본 경로
- 예외적으로 코드 확장을 허용하는 범위:
  - raw payload normalization
  - domain-specific A2UI form/view mapping

## Current Usecases

- `pre-hitl-input-form`
- `hitl-gated-mutation`
- `review-approve-resume`
- `review-cancel`
- `single-agent-route`
- `multi-agent-route`
- `handoff-route`
- `compose-to-a2ui`
- `reservation-agent-form-seed`
- `sale-product-create-form-seed`

## Current Storage / Lifecycle Mapping

- `supervisor_a2a_lifecycle_service`
  - task lifecycle policy와 read model 조회를 담당한다.
- `supervisor_task_facade`
  - task 응답 view 조립 facade다.
- `supervisor_read_query_factory`
  - read intent에 맞는 query handler를 선택한다.
- `execution_restore_read_query`
  - history/checkpoint/swarm/snapshot restore read를 담당한다.
- `task_read_model_query`
  - task get/list read model 조회를 담당한다.
- `review_read_query`
  - review get/decide 전 조회를 담당한다.
- `snapshot_verification_query`
  - approve resume 이전 snapshot ownership/version/hash 검증 read를 담당한다.
- `supervisor_execution_persistence_service`
  - review open / approved resume / completion 같은 Redis write 시나리오의 단일 facade 진입점이다.

## Current A2A Mapping

- `A2ARequestMapper`
  - legacy/current JSON-RPC method alias를 내부 enum과 DTO로 정규화한다.
- `A2AResponseMapper`
  - `JsonRpcResponse`, `TaskView`, stream event를 공통 규칙으로 직렬화한다.
- `A2AChannelAssembler`
  - 최종 응답을 `raw-data`와 `compose-result` 채널로 조립한다.
- `A2AClientRegistry`
  - `routing config`에 등록된 agent를 런타임 registry로 노출한다.
- `AgentCardReader`
  - registry에 등록된 agent의 agent card를 조회해 capability/source metadata를 해석한다.
- `SupervisorRequestIdempotencyService`
  - 내부 기준 `session_id + method + request_id + normalized params hash` 기준으로 재전송 요청을 단일 실행으로 수렴시킨다.

## Current LLM Mapping

- `default_supervisor_llm_runtime`
  - supervisor 계층의 공통 complete/stream 포트다.
- `llm_supervisor_planning_service`
  - planning + `review_required` JSON output + repair prompt 사용
- `llm_supervisor_response_compose_service`
  - compose prompt + compose A2UI prompt + repair prompt 사용

## Source-backed Constraints

- supervisor는 `/a2a/supervisor`만 노출하며, 내부에서 다른 endpoint로 포워딩하지 않는다.
- pre-HITL A2UI가 있으면 HITL/실행보다 우선한다.
- streaming path는 `SupervisorOutputEvent`를 SSE `chunk/a2ui/done/error`로 직렬화한다.
- progress/reasoning 이벤트는 transport 전용이며 task payload persistence에는 포함되지 않는다.
- review decide는 unary와 stream 재개 경로를 모두 지원한다.
- `request_id` 기본 소스는 JSON-RPC `id`다.
- 내부 correlation key(`trace_id`, `request_id`, `session_id`)는 요청 전 구간에 전달되어야 한다.
- 최종 A2A 응답은 `raw-data + compose-result` 2채널 구조를 유지한다.
