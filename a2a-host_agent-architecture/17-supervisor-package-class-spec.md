# 17. Supervisor Package / Class Specification

Updated: 2026-04-25
Source baseline: `src/app`

## Target Baseline

이 문서는 `smart-supervisor` 프로젝트의 supervisor 아키텍처를 Python 기준으로 정의한다.
Supervisor는 downstream A2A agent를 통제하는 독립 orchestration 계층이며, 라우팅, HITL, handoff, swarm, A2UI 책임을 자신의 문서 안에서 완결적으로 정의한다.
`FrozenExecutionPlan`의 필드 정본은 `31-frozen-execution-plan-schema.md`를 따른다.
구현 초안은 `32-frozen-execution-plan-implementation-draft.md` 문서에 Python 대응 형태로 유지한다.

- 공통 기반
  - `Python 3.11+ + FastAPI + LangChain + LangGraph + A2A + Redis`
- supervisor 전용 책임
  - downstream A2A agent routing
  - HITL(review gate / approve / cancel)
  - swarm shared state / handoff policy
  - supervisor progress / A2UI envelope

## Reuse First

현재 소스에서 우선 재사용할 계층은 다음이다.

- provider chat model 계층
- `settings/app.yml`
- `settings/supervisor.yml`
- `settings/supervisor-hitl.yml`
- `settings/supervisor-system-prompt.yml`
- 공통 web/security/config 기반

## Current Source Baseline

실제 구현 베이스라인은 아래와 같다.

```text
src/app
├── api
├── application
├── domain
├── a2a
├── infrastructure
└── common
```

## Folder Rule

- 최상위 애플리케이션 패키지는 `app`을 유지한다.
- `api`, `application`, `domain`, `a2a`, `infrastructure`, `common`은 최상위 역할 패키지다.
- `application` 아래에 역할별 하위 폴더를 둔다.
  - `application/agent/*`
  - `application/prompt/*`
  - `application/a2ui/*`
- supervisor 도메인 모델은 `domain/supervisor/*`로 묶는다.
- A2A 계약 객체는 `a2a/*` 아래에 둔다.
- prompt 문자열, JSON-RPC method, progress stage, Redis key prefix, error code는 하드코딩하지 않는다.

## New Packages To Build

- `app/api/supervisor`
- `app/api/support`
- `app/application/agent`
- `app/application/agent/plan`
- `app/application/agent/hitl`
- `app/application/agent/invoke`
- `app/application/agent/compose`
- `app/application/agent/graph`
- `app/application/agent/handoff`
- `app/application/agent/persistence`
- `app/application/agent/persistence/strategy`
- `app/application/agent/persistence/template`
- `app/application/agent/read`
- `app/application/agent/read/query`
- `app/application/agent/swarm`
- `app/application/agent/runtime`
- `app/application/agent/security`
- `app/application/a2ui/common`
- `app/application/a2ui/product`
- `app/application/a2ui/reservation`
- `app/application/prompt`
- `app/infrastructure/redis`
- `app/infrastructure/http`
- `app/infrastructure/settings`
- `app/infrastructure/idempotency`
- `app/a2a/dto`
- `app/a2a/mapper`
- `app/a2a/task`
- `app/a2a/lifecycle`
- `app/domain/supervisor`
- `app/common/exceptions`

## Naming Convention

- Python 내부 구현 명칭은 `snake_case`를 기준으로 한다.
- 클래스명이 필요할 때만 `PascalCase`를 사용하고, 문서의 기본 명칭은 모듈/함수/서비스 식별자 기준으로 적는다.
- 외부 A2A 계약에서 요구하는 JSON-RPC method alias와 payload key는 protocol 호환 때문에 원문을 유지할 수 있다.
- 즉 내부 코드에서는 `session_id`, `request_id`, `trace_id`, `review_required`를 사용하고, 외부 계약 호환 계층에서만 legacy field alias를 매핑한다.

## New Modules / Components

- `supervisor_a2a_endpoint`
- `supervisor_a2a_request_validator`
- `base_a2a_endpoint_support`
- `agent_card_endpoint`
- `a2a_execution_context`
- `supervisor_agent_service`
- `supervisor_agent_orchestrator`
- `supervisor_execution_service`
- `supervisor_review_application_service`
- `supervisor_task_facade`
- `supervisor_read_facade`
- `supervisor_read_query_factory`
- `execution_restore_read_query`
- `task_read_model_query`
- `review_read_query`
- `snapshot_verification_query`
- `hitl_gate_service`
- `hitl_decision_service`
- `supervisor_planning_service`
- `llm_supervisor_planning_service`
- `a2a_client_registry`
- `a2a_invocation_service`
- `default_a2a_invocation_service`
- `supervisor_response_compose_service`
- `llm_supervisor_response_compose_service`
- `supervisor_state_graph_factory`
- `langgraph_supervisor_state_graph_factory`
- `supervisor_plan_runner`
- `supervisor_execution_persistence_service`
- `supervisor_persistence_command`
- `supervisor_persistence_strategy_factory`
- `supervisor_persistence_strategy`
- `abstract_supervisor_persistence_strategy`
- `review_open_persistence_strategy`
- `approved_resume_persistence_strategy`
- `execution_completion_persistence_strategy`
- `handoff_policy_service`
- `default_handoff_policy_service`
- `supervisor_swarm_coordinator`
- `default_supervisor_swarm_coordinator`
- `supervisor_llm_runtime`
- `default_supervisor_llm_runtime`
- `prompt_injection_guard`
- `scope_guard`
- `supervisor_execution_limiter`
- `supervisor_a2ui_service`
- `composite_supervisor_a2ui_service`
- `supervisor_prompt_render_service`
- `prompt_template_renderer`
- `date_hint_service`
- `conversation_store`
- `graph_checkpoint_store`
- `supervisor_review_store`
- `supervisor_swarm_state_store`
- `redis_key_factory`
- `redis_ttl_policy`
- `supervisor_request_trace_context`
- `supervisor_trace_propagation_service`
- `execution_consistency_coordinator`

## Key Contracts

- `supervisor_agent_service.execute(request) -> JsonRpcResponse`
- `supervisor_agent_service.execute_stream(request) -> AsyncIterator[SupervisorOutputEvent]`
- `supervisor_execution_service.execute_sync(request) -> SupervisorExecutionResult`
- `supervisor_execution_service.execute_stream_events(request) -> AsyncIterator[SupervisorOutputEvent]`
- `supervisor_review_application_service.decide_review(...) -> SupervisorExecutionResult`
- `supervisor_read_facade.read(query) -> T`
- `supervisor_read_query_factory.select(query_type) -> supervisor_read_query`
- `execution_restore_read_query.load_runtime_state(session_id, task_id, state_version)`
- `task_read_model_query.get_or_list(...)`
- `review_read_query.get_or_lookup(...)`
- `snapshot_verification_query.verify(task_id, session_id, resume_token, state_version, request_hash, frozen_plan_hash)`
- `supervisor_agent_orchestrator.execute(request) -> AsyncIterator[SupervisorOutputEvent]`
- `supervisor_planning_service.plan(context) -> SupervisorPlanningDecision`
- `a2a_invocation_service.invoke(context) -> DownstreamCallResult`
- `handoff_policy_service.evaluate(result, context) -> list[HandoffValidationResult]`
- `supervisor_response_compose_service.stream_compose_events(context) -> AsyncIterator[SupervisorOutputEvent]`
- `supervisor_state_graph_factory.get_compiled_graph() -> CompiledStateGraph`
- `a2a_task_store.create/get/list/cancel/mark_running/mark_completed/mark_failed`
- `supervisor_a2a_lifecycle_service.get/list/build_task_view`
- `supervisor_request_idempotency_service.execute(request, action)`
- `conversation_store.load/save/clear`
- `graph_checkpoint_store.load/save/clear`
- `supervisor_swarm_state_store.load/save/clear`
- `supervisor_review_store.open/get/decide`
- `reviewed_execution_snapshot_store.create/get/verify`
- `supervisor_execution_persistence_service.persist(command)`
- `execution_consistency_coordinator.open_review(snapshot, review, task)`
- `execution_consistency_coordinator.start_approved_resume(task_id, snapshot_version)`
- `execution_consistency_coordinator.complete_execution(task_id, final_result)`

## Dependency Policy

- `supervisor_a2a_endpoint -> supervisor_a2a_request_validator -> supervisor_agent_service`
- `supervisor_agent_service -> supervisor_request_idempotency_service + hitl_gate_service + supervisor_execution_service + supervisor_review_application_service + supervisor_task_facade`
- `supervisor_agent_service -> supervisor_read_facade + supervisor_execution_persistence_service`
- `hitl_gate_service -> supervisor_planning_service + supervisor_read_facade + supervisor_execution_persistence_service`
- `supervisor_execution_service -> supervisor_agent_orchestrator + supervisor_task_facade + supervisor_read_facade + supervisor_execution_persistence_service`
- `supervisor_agent_orchestrator -> supervisor_state_graph_factory + supervisor_response_compose_service + supervisor_a2a_lifecycle_service + supervisor_read_facade + supervisor_execution_persistence_service`
- `supervisor_read_facade -> supervisor_read_query_factory`
- `supervisor_execution_persistence_service -> supervisor_persistence_strategy_factory`
- `langgraph_supervisor_state_graph_factory -> supervisor_swarm_coordinator + supervisor_plan_runner + handoff_policy_service`
- `supervisor_plan_runner -> a2a_invocation_service`
- `default_a2a_invocation_service -> a2a_client_registry + a2a_request_mapper + a2a_json_rpc_client`
- `llm_supervisor_planning_service / llm_supervisor_response_compose_service -> default_supervisor_llm_runtime`
- `default_supervisor_llm_runtime -> provider chat model 계층`

## Supervisor-specific Rules

- supervisor는 내부 도구 실행 계층이 아니라 downstream A2A agent를 호출하는 제어 계층이다.
- supervisor 내부 LLM은 planning, compose, a2ui-select 용도로만 사용한다.
- planner는 graph 외부 service gate에서 1회 호출하고 graph 내부에서 다시 호출하지 않는다.
- planner의 `review_required` 누락, schema 불일치, parse/runtime 실패는 모두 fail-closed가 기본이다.
- LLM provider 연결 정보는 `settings/*.yml` 또는 settings object만 기준으로 관리한다.
- compose 단계에서 downstream 재호출을 금지한다.
- supervisor는 `raw-data + compose-result` 채널 구조를 최종 A2A 응답에 유지한다.
- review approve는 immutable reviewed snapshot을 검증한 후 그 snapshot으로만 재개한다.
- `review_required` 경로는 planner output을 freeze해서 승인 대상으로 저장한다.
- 공개 함수와 핵심 클래스에는 docstring과 타입힌트를 필수 적용한다.
