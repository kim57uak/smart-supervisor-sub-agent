# 20. Supervisor Routing Package / Class Spec

Updated: 2026-04-28 (Implementation Refined)
Source baseline: `settings/supervisor.yml`, `src/app`

## Scope

- **Decoupled Architecture**: API(FastAPI)와 Worker(Background)를 분리하여 운영한다.
- **Reliable Invocation**: 모든 downstream 호출은 `a2a_invocation_service`를 거치며 서킷 브레이커와 재시도를 자동 적용한다.
- **Consistency First**: 모든 상태 전이는 `ExecutionConsistencyCoordinator`를 통해 원자적(Atomic)으로 처리한다.
- **Idempotency**: Redis `SET NX` 기반의 분산 락을 통해 중복 실행을 방지한다.

## Runtime Flow

1. **Submission Phase (API Tier)**:
   - `supervisor_a2a_endpoint`가 요청 수신.
   - `validator`가 스키마 및 메서드 허용 여부 체크.
   - `consistency_coordinator`가 `request_id` 기반 멱등성 선점.
   - `hitl_gate_service`가 플래닝 및 리뷰 필요성 평가.
   - 리뷰 불필요 시 `task_queue_service`에 작업 적재 후 즉시 `STREAMING` 응답.

2. **Execution Phase (Worker Tier)**:
   - `worker.py`가 Redis Queue에서 작업 추출.
   - `supervisor_graph_execution_service`가 실행 문맥 복원 및 LangGraph 실행.
   - `invocation_service`가 downstream agent 호출.
   - `progress_publisher`가 Redis Stream에 실시간 진행 상태 발행.
   - `compose_service`가 결과를 합성하고 최종 완료 처리.

## Core Components (Actual Class Names)

- **`SupervisorAgentService`**: API 유즈케이스 진입점.
- **`WorkerExecutionService`**: 워커 루프 및 작업 실행 관리.
- **`ExecutionConsistencyCoordinator`**: Redis CAS 기반 일관성 제어기.
- **`SupervisorGraphExecutionService`**: 그래프 실행 오케스트레이터.
- **`LangGraphSupervisorStateGraphFactory`**: LangGraph 정의 및 컴파일.
- **`DefaultA2AInvocationService`**: A2A 통신 및 탄력성(Resilience) 처리.
- **`SnapshotVerificationQuery`**: 승인 전 무결성 검증 쿼리.
- **`PromptInjectionGuard`**: 보안 필터링 서비스.

## Core Contracts

- `agent_service.execute_task(session_id, message, request_id) -> Dict`
- `consistency_coordinator.check_and_reserve_request(request_id, task_id) -> (bool, task_id)`
- `graph_execution.execute_plan(session_id, task_id, plan) -> Dict`
- `invocation_service.invoke(agent_key, method, arguments) -> Result`
- `event_publisher.publish_chunk(session_id, task_id, agent, payload)`

## Method Compatibility Policy

| Operation | Legacy JSON-RPC | Current JSON-RPC |
|---|---|---|
| send message | `message/send` | `SendMessage` |
| stream message | `message/stream` | `SendStreamingMessage` |
| get task | `tasks/get` | `GetTask` |
| list tasks | `tasks/list` | `ListTasks` |
| cancel task | `tasks/cancel` | `CancelTask` |
| task events stream | `tasks/events` | `TaskEvents` |

## Progress / Stream Policy

- 모든 진행 상태는 Redis Stream(`XADD`)을 통해 발행된다.
- 클라이언트는 `/stream` 엔드포인트에서 SSE를 통해 이벤트를 수신한다.
- 이벤트 타입: `progress`, `reasoning`, `chunk`, `a2ui`, `done`, `error`.
