# 20. Supervisor Routing Package / Class Spec

Updated: 2026-04-25
Source baseline: `settings/supervisor.yml`, `settings/supervisor-system-prompt.yml`

## Scope

- supervisor 진입점은 단일 endpoint 계열을 사용한다.
- supervisor는 downstream agent 호출을 `a2a_invocation_service`를 통해서만 수행한다.
- supervisor는 아래 공통 런타임 규칙을 자체적으로 유지한다.
  - `legacy + v1.0` method compatibility
  - idempotency
  - correlation key propagation
  - Redis TTL `30분`
  - prompt/endpoint 하드코딩 금지
- LLM provider 연결 정보는 settings에서만 관리하고 별도 MCP/tool 설정은 두지 않는다.

## Runtime Flow

1. `supervisor_a2a_endpoint`가 JSON-RPC envelope를 수신한다.
2. `supervisor_a2a_request_validator`가 허용 method와 요청 형식을 검증한다.
3. `supervisor_request_idempotency_service`가 재전송 여부를 판단한다.
4. `supervisor_agent_service`가 request를 `supervisor_execution_request`로 정규화한다.
5. pre-HITL A2UI 대상이면 즉시 `A2UI` 응답을 반환할 수 있다.
6. `hitl_gate_service`가 `supervisor_planning_service.plan(...)`을 호출해 routing + review_required를 함께 판단한다.
7. reviewable execution이면 planner 결과를 freeze해 승인 대상 실행 계획으로 확정한다.
8. 검토가 필요하면 review task를 생성하고 `WAITING_REVIEW` 상태를 반환한다.
9. 검토가 불필요하면 `supervisor_execution_service`가 orchestration을 시작한다.
10. `supervisor_agent_orchestrator`가 LangGraph supervisor graph를 실행한다.
11. `supervisor_plan_runner`가 `a2a_invocation_service`를 통해 downstream agent를 호출한다.
12. `supervisor_response_compose_service`가 downstream 결과를 바탕으로 최종 응답과 필요 시 A2UI envelope를 생성한다.

## Core Components

- `supervisor_a2a_endpoint`
- `supervisor_a2a_request_validator`
- `supervisor_agent_service`
- `supervisor_request_idempotency_service`
- `hitl_gate_service`
- `supervisor_execution_service`
- `supervisor_review_application_service`
- `supervisor_task_facade`
- `supervisor_agent_orchestrator`
- `supervisor_planning_service`
- `a2a_invocation_service`
- `handoff_policy_service`
- `supervisor_swarm_coordinator`
- `supervisor_response_compose_service`
- `supervisor_a2ui_service`
- `supervisor_progress_publisher`
- `supervisor_execution_persistence_service`
- `execution_consistency_coordinator`
- `reviewed_execution_snapshot_store`

## Core Contracts

- `supervisor_planning_service.plan(context) -> SupervisorPlanningDecision`
- `a2a_invocation_service.invoke(context) -> DownstreamCallResult`
- `handoff_policy_service.evaluate(result, context) -> list[HandoffValidationResult]`
- `supervisor_response_compose_service.stream_compose_events(context) -> AsyncIterator[SupervisorOutputEvent]`
- `supervisor_a2ui_service.build(context, selected_view, message) -> A2uiRenderResult | None`
- `supervisor_request_idempotency_service.execute(request, action)`
- `supervisor_execution_persistence_service.persist(command)`
- `execution_consistency_coordinator.create_waiting_review_with_snapshot(...)`
- `execution_consistency_coordinator.start_approved_resume(...)`
- `execution_consistency_coordinator.complete_execution(...)`
- `reviewed_execution_snapshot_store.verify(task_id, session_id, resume_token, state_version, request_hash, frozen_plan_hash)`

## Method Compatibility Policy

supervisor는 아래 method family를 동시에 지원해야 한다.

| Operation | Legacy JSON-RPC | Current JSON-RPC |
|---|---|---|
| send message | `message/send` | `SendMessage` |
| stream message | `message/stream` | `SendStreamingMessage` |
| get task | `tasks/get` | `GetTask` |
| list tasks | `tasks/list` | `ListTasks` |
| cancel task | `tasks/cancel` | `CancelTask` |
| task events stream | `tasks/events` | `TaskEvents` |

## Progress / Stream Policy

- progress 출력은 `supervisor_progress_publisher` 공통 포맷을 사용한다.
- stream 응답은 FastAPI SSE 정책으로 일관되게 유지한다.
- handoff, hitl, invoke, merge, compose 단계는 progress stage를 노출해야 한다.
- endpoint는 typed `SupervisorOutputEvent`를 최종 SSE event/data로 매핑하는 마지막 adapter 역할만 담당한다.
