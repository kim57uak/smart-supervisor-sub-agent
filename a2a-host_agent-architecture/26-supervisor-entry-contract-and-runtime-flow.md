# 26. Supervisor Entry Contract And Runtime Flow

Updated: 2026-04-25
Current baseline: `src/app`

## Purpose

본 문서는 supervisor의 유일한 entry contract와 send, stream, review resume의 기준 실행 흐름을 Python runtime 기준으로 정의한다.

## Entry Contract

supervisor entrypoint는 아래 계열만 사용한다.

- `POST /a2a/supervisor`
- `POST /a2a/supervisor/stream`
- `POST /a2a/supervisor/review/decide`
- `GET /a2a/supervisor/tasks/{task_id}`
- `GET /.well-known/agent.json`

추가 HTTP endpoint를 기능별로 늘리지 않는다.

## Supported Method Families

- `message/send` / `SendMessage`
- `message/stream` / `SendStreamingMessage`
- `tasks/get` / `GetTask`
- `tasks/list` / `ListTasks`
- `tasks/cancel` / `CancelTask`
- `tasks/events` / `TaskEvents`
- `tasks/review/get`
- `tasks/review/decide`

## Layer Responsibilities On Entry

### `supervisor_a2a_endpoint`

- JSON-RPC envelope 수신
- HTTP/SSE 프로토콜 처리
- validator 호출
- service 결과를 `JsonRpcResponse`, `TaskView`, SSE event로 직렬화

### `supervisor_a2a_request_validator`

- method allowlist 검증
- params schema 검증
- review decision 값 검증
- correlation key 추출/보정

### `supervisor_agent_service`

- use case 분기
- pre-HITL A2UI, HITL gate, execution, review decision 흐름 조립
- task/read model 요청과 실행 요청 분리

## Canonical Runtime Flow

### 1. Send / Stream Request

1. endpoint가 envelope를 수신하고 validator로 검증한다.
2. service가 request를 `SupervisorExecutionRequest`로 정규화한다.
3. `supervisor_pre_hitl_a2ui_service`가 선제 UI shortcut 대상인지 판단한다.
4. shortcut이 없으면 `hitl_gate_service`가 planner를 호출해 `routing + review_required`를 함께 결정한다.
5. review 필요 시 planner 결과를 freeze하고 immutable snapshot 저장 후 waiting review task를 연다.
6. review 불필요 시 `supervisor_execution_service`가 orchestration을 시작한다.
7. orchestrator가 graph 실행과 compose를 조정하고, persistence는 `supervisor_execution_persistence_service` facade에 위임한다.
8. endpoint가 unary 또는 stream 응답으로 변환한다.

### 2. Review Decide

1. endpoint가 `tasks/review/decide`를 수신한다.
2. validator가 decision type과 필수 식별자를 검증한다.
3. service가 `hitl_gate_service`에 위임한다.
4. `APPROVE`는 snapshot 검증 후 `supervisor_execution_service.resume_approved_snapshot(...)`으로 이어진다.
5. `CANCEL`은 task terminal state를 먼저 확정한다.

## Task Event Stream Subscription

- runtime event 재구독은 `POST /a2a/supervisor/stream`에서 `tasks/events` 또는 `TaskEvents` method로만 수행한다.
- stream event type은 최소 `accepted`, `heartbeat`, `progress`, `reasoning`, `chunk`, `a2ui`, `done`, `error`를 지원한다.
- 모든 event에는 내부 기준 `task_id`, `event_id`, `cursor`, `event_type`, `created_at`가 포함되어야 한다.
- cursor는 task 단위 단조 증가 값이어야 하며 재구독과 replay 기준으로 사용한다.

## Pre-HITL A2UI Rule

pre-HITL A2UI는 "먼저 정보를 보여주고 이후 사용자의 명시적 선택을 받는 것이 더 좋은 경우"에만 사용한다.

- product summary / product detail candidate
- 입력 보완이 필요한 product selection
- 즉시 데이터 변경이 일어나지 않는 안내성 화면

pre-HITL A2UI가 생성되면 downstream invoke와 review open을 바로 진행하지 않는다.

## Streaming Rules

- stream은 최소 `progress`, `chunk`, `a2ui`, `done`, `error` 타입을 지원한다.
- reasoning은 일반 answer chunk와 섞지 않고 별도 event type으로 취급한다.
- progress는 transport 이벤트이며 persistence 대상이 아니다.
- unary와 stream은 같은 business result를 표현해야 하며, 단지 delivery 방식만 달라야 한다.
- review approve 후 `STREAM` 재개는 기존 응답을 이어붙이는 개념이 아니라 task event stream 재구독으로만 처리한다.

## Runtime Decisions That Are Fixed

- `review_required` 판단은 planner output에 포함되며 graph 외부 service 레벨 게이트로 처리한다.
- `review_required` 누락, planner schema 불일치, parse/runtime 실패는 fail-closed로 처리한다.
- review approve는 raw request 재실행이 아니라 immutable snapshot resume이다.
- compose 단계에서 downstream 재호출을 금지한다.
- stream transport와 sync/resume persistence를 분리한다.
