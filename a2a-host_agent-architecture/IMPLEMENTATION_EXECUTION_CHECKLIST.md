# Supervisor Implementation Execution Checklist

> [!IMPORTANT]
> **구현 폴더**: `/Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/src/supervisor-agent`
> **코드 분리 원칙**: 추후 별도 서버에서 구동할 예정이므로, **sub-agent와 코드를 공유하거나 참고해서는 절대 안 됩니다.** 소스가 엮이지 않도록 독립적으로 구현해야 합니다. (단, 파이썬 가상환경 폴더는 공유 가능합니다.)
> **엔터프라이즈 환경 구성**: 엔터프라이즈 환경 구성을 위해 `/Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/platform-runtime-enterprise-spec` 폴더의 문서들을 반드시 구현에 반영해야 합니다.

Updated: 2026-04-25
Scope baseline: `document/a2a-host_agent-architecture/20`, `26`, `29`, `31`, `32`, `06`, `19`

## Purpose

이 문서는 현재 정리된 supervisor architecture를 실제 코드로 내리기 위한 구현 체크리스트다.
목표는 "아키텍처 리뷰를 더 하는 것"이 아니라, 구현자가 무엇을 어떤 순서로 만들고 어떤 조건을 만족해야 하는지 바로 실행 가능한 수준으로 고정하는 것이다.

본 문서는 특히 아래 두 주제를 구현 단위로 닫는다.

- `tasks/review/decide` approve/cancel 계약
- `STREAM` approve resume ordering + `initial_cursor` replay safety

## Implementation Principles

이 문서 기준의 구현은 아래 원칙을 반드시 따른다.

### Core Engineering Principles

- SOLID 원칙을 준수한다.
- 유지보수성과 가독성을 구현 편의보다 우선한다.
- 클래스와 메서드는 책임이 명확해야 하며, 한 곳에 여러 책임을 섞지 않는다.
- 구현은 "지금 돌아가는 코드"보다 "이후 수정 가능한 코드"를 목표로 한다.

### Class And Method Design Rules

- 클래스는 가능한 한 단일 책임을 가진다.
- 메서드는 가능한 한 짧고 단순하게 유지한다.
- 복잡한 분기, 검증, 상태 전이, 매핑 로직은 작은 메서드로 분해한다.
- 한 메서드 안에서 검증, 상태 변경, 응답 조립, 로깅을 모두 처리하지 않는다.
- 메서드 이름만 읽어도 역할이 드러나야 한다.
- 재사용보다 책임 분리가 우선이며, 억지 공통화는 피한다.

### Maintainability Rules

- 구현자는 "다음 사람이 바로 수정 가능한가"를 기준으로 코드를 작성한다.
- 의미가 불분명한 축약어, 암묵적 상태 공유, 숨겨진 부작용을 피한다.
- enum, result object, DTO, mapper, validator, coordinator 경계를 명확히 둔다.
- 테스트 가능한 구조를 우선하며, static helper나 거대한 service에 책임을 몰지 않는다.

### Comment Rules

- 클래스에는 해당 클래스가 맡는 구현 책임을 설명하는 주석을 작성한다.
- 주요 public 메서드에는 무엇을 보장하고 무엇을 하지 않는지 설명하는 주석을 작성한다.
- 복잡한 구현 메서드에는 로직 블록 앞에 왜 그렇게 동작하는지 설명하는 주석을 추가한다.
- 상태 전이, replay ordering, idempotency, drift block처럼 오해 가능성이 높은 로직에는 반드시 주석을 남긴다.
- 주석은 코드가 "무엇을 한다"만 반복하지 말고, 왜 그 순서와 규칙이 필요한지를 설명해야 한다.

### Complexity Control Rules

- 가능한 함수는 복잡하지 않게 유지한다.
- 조건문이 깊어지면 guard clause, result object, helper method로 분해한다.
- boolean flag가 많아지는 메서드는 역할 분리 신호로 보고 분리한다.
- 하나의 메서드가 지나치게 많은 도메인 개념을 다루면 메서드 또는 클래스를 나눈다.
- 구현 이후 리팩토링 없이 방치할 복잡한 메서드를 만들지 않는다.

### Review Standard For Implementation Quality

- 코드리뷰 시 기능 충족뿐 아니라 SOLID, 가독성, 유지보수성, 주석 충실도도 함께 본다.
- 문서 기준으로 맞더라도 클래스 책임이 과도하게 뭉쳐 있으면 개선 대상으로 본다.
- 복잡한 메서드에 주석이 없거나, 주석 없이 이해가 어려운 상태 전이 로직은 리뷰 finding 대상이다.

## Done Definition

관련 아키텍처 문서:

- `20` routing package / class spec
- `26` entry contract and runtime flow
- `29` security and reliability model
- `31` FrozenExecutionPlan schema
- `32` FrozenExecutionPlan implementation draft
- `06` supervisor A2A request sequence
- `19` supervisor runtime sequence

아래 조건을 모두 만족하면 이번 작업 범위는 완료로 본다.

- `tasks/review/decide`가 최소 입력 계약과 표준 결과 계약을 따른다.
- approve 검증은 client 입력이 아니라 server snapshot + current task truth를 source of truth로 사용한다.
- `WAITING_REVIEW -> RUNNING` approve resume 경로에서 `initial_cursor`가 durable event log 기준으로 확정된다.
- approve ack 이후 client가 `tasks/events`로 재구독했을 때 replay 대상 event를 놓치지 않는다.
- duplicate approve/cancel이 side effect 중복 없이 idempotent result로 수렴한다.
- 주요 실패 사유가 표준 reason code로 외부에 노출된다.
- 통합 테스트가 approve/reject/replay race 핵심 시나리오를 덮는다.

## Delivery Priority

### P0. Review Decide Contract

관련 아키텍처 문서:

- `26` 2. Review Decide / 2A / 2B / 2C
- `20` review approve delivery 규칙
- `06` review endpoints sequence
- `19` review endpoint sequence

반드시 구현:

- `tasks/review/decide` 최소 요청 계약
  - `task_id`
  - `decision`
- `decision` 허용값
  - `APPROVE`
  - `CANCEL`
- approve 결과 계약
  - `resume_accepted`
  - `resume_rejected`
  - `already_terminal`
  - `duplicate_decision`
- reject reason code 계약
  - `TASK_NOT_FOUND`
  - `SESSION_OWNERSHIP_MISMATCH`
  - `TASK_STATE_INVALID`
  - `SNAPSHOT_NOT_FOUND`
  - `SNAPSHOT_EXPIRED`
  - `RESUME_TOKEN_MISMATCH`
  - `STATE_VERSION_MISMATCH`
  - `REQUEST_HASH_MISMATCH`
  - `FROZEN_PLAN_HASH_MISMATCH`
  - `PLAN_DRIFT_BLOCKED`

수용 기준:

- endpoint/validator는 `task_id`, `decision` 누락을 계약 오류로 차단한다.
- approve 검증 실패는 내부 예외 메시지가 아니라 표준 reason code로 매핑된다.
- 이미 terminal이거나 이미 cancel된 task에 대한 approve는 side effect 없이 거부된다.
- duplicate approve/cancel은 현재 task truth를 읽어 동일한 의미의 응답으로 수렴한다.

### P0. Approve Verification

관련 아키텍처 문서:

- `31` Verification On Approve
- `31` Drift Policy
- `29` Review Integrity
- `26` 2A. Review Decide Request Contract

반드시 구현:

- server snapshot 기준 검증
  - session ownership
  - current task state
  - snapshot existence
  - resume token
  - state version
  - request hash
  - frozen plan hash
  - snapshot TTL
- drift block 판정
  - route allowlist
  - method allowlist
  - downstream stream capability
  - agent disabled
  - terminally invalid endpoint

수용 기준:

- approve 요청이 최소 필드만 오더라도 최종 검증은 server snapshot과 task truth로 수행된다.
- client가 추가 검증 필드를 보내더라도 그것이 source of truth를 대체하지 않는다.
- fail-open이 아니라 reject 또는 controlled response로만 수렴한다.

### P0. STREAM Approve Resume Ordering

관련 아키텍처 문서:

- `26` 2B. Approved Resume Delivery Rule
- `26` 4A. STREAM Approve Resume Ordering Rule
- `31` Write Order
- `31` STREAM Resume Contract
- `29` Stream Resume Reliability
- `06` review endpoints sequence
- `19` review endpoint sequence

반드시 구현:

- `WAITING_REVIEW -> RUNNING` CAS
- durable event log 기준 `initial_cursor` 확보
- approve ack 반환
- runtime event append/publish
- client `tasks/events` 재구독

고정 순서:

1. snapshot verify
2. task `WAITING_REVIEW -> RUNNING` CAS
3. durable event stream 기준 `initial_cursor` 확정
4. approve ack 반환
5. runtime event append/publish

수용 기준:

- `initial_cursor`는 best-effort live emitter 값이 아니어야 한다.
- client가 ack의 `initial_cursor` 다음부터 재구독하면 approve 이후 replay 대상 event를 놓치지 않아야 한다.
- 최소 `chunk`, `a2ui`, `done`, `error`는 replay 가능해야 한다.
- `heartbeat`는 replay 대상이 아니어도 된다.

### P1. Task Event Replay

관련 아키텍처 문서:

- `26` 4. Task Event Stream Subscription
- `26` Streaming Rules
- `29` Stream Resume Reliability
- `31` STREAM Resume Contract

반드시 구현:

- task 단위 단조 증가 cursor
- replay retention
- `tasks/events` 재구독
- cursor 만료 시 `CURSOR_EXPIRED`

수용 기준:

- terminal event 이후에는 동일 task에서 새 live cursor가 증가하지 않는다.
- client가 늦게 붙어도 retention 윈도우 안에서는 replay가 가능하다.
- approve 직후 매우 빠른 실행에서도 첫 `chunk` 또는 즉시 `done`을 replay로 받을 수 있다.

### P1. Audit And Logging

관련 아키텍처 문서:

- `29` Logging And Audit
- `27` Fallback Policy
- `29` Recovery Matrix

반드시 구현:

- approve accepted log
- approve rejected log
- reject reason code log
- `task_id`, `session_id`, `state_version`, `initial_cursor` log
- drift blocked audit

수용 기준:

- INFO 로그에는 식별자와 결과만 남기고 raw payload는 남기지 않는다.
- approve reject 사유는 운영자가 추적 가능한 수준의 reason code로 남는다.

## Concrete Implementation Work Items

### 1. Request/Response DTO 정리

관련 아키텍처 문서:

- `26` 2A. Review Decide Request Contract
- `26` 2B. Approved Resume Delivery Rule
- `26` 2C. Review Decide Result And Error Rule
- `20` review approve delivery 규칙
- `32` `ReviewApproveAck` draft

필요 작업:

- review decide request DTO 생성 또는 정리
- `decision` enum 도입
- approve ack DTO 정리
- reject result DTO 정리

권장 필드:

- request
  - `task_id`
  - `decision`
  - `review_id` optional
  - `comment` optional
  - `client_request_id` optional
- approve ack
  - `task_id`
  - `state_version`
  - `execution_mode`
  - `resume_accepted`
  - `stream_resume_required`
  - `stream_method`
  - `stream_endpoint`
  - `initial_cursor`
- reject result
  - `task_id`
  - `resume_accepted=false`
  - `reason_code`
  - `current_state`
  - `state_version`

후보 클래스 위치:

- `endpoint` / `transport` DTO 패키지
- `model.supervisor`
- `a2a.jsonrpc.response`

### 2. Reason Code Enum 도입

관련 아키텍처 문서:

- `26` 2C. Review Decide Result And Error Rule
- `31` Verification On Approve
- `29` Review Integrity

필요 작업:

- review approve reject 전용 enum 생성
- exception translator 또는 response mapper에 매핑 추가

필수 enum 값:

- `TASK_NOT_FOUND`
- `SESSION_OWNERSHIP_MISMATCH`
- `TASK_STATE_INVALID`
- `SNAPSHOT_NOT_FOUND`
- `SNAPSHOT_EXPIRED`
- `RESUME_TOKEN_MISMATCH`
- `STATE_VERSION_MISMATCH`
- `REQUEST_HASH_MISMATCH`
- `FROZEN_PLAN_HASH_MISMATCH`
- `PLAN_DRIFT_BLOCKED`

구현 원칙:

- low-level store exception을 외부에 직접 노출하지 않는다.
- reason code는 domain/application 경계에서 확정한다.
- JSON-RPC error와 business reject result를 섞지 않는다.
  - envelope/schema 오류는 JSON-RPC error
  - approve 검증 실패는 business reject result

### 3. Validator 구현

관련 아키텍처 문서:

- `26` Layer Responsibilities On Entry / `supervisor_a2a_request_validator`
- `26` 2. Review Decide
- `20` Method Compatibility Policy

필요 작업:

- `tasks/review/decide` method family 인식
- `task_id`, `decision` 필수값 검증
- 허용 decision enum 검증

수용 기준:

- `task_id` 누락 시 즉시 계약 오류
- `decision` 오탈자 시 즉시 계약 오류
- `APPROVE`, `CANCEL` 외 값은 허용하지 않음

### 4. Snapshot Verification Query/Service 구현

관련 아키텍처 문서:

- `31` Verification On Approve
- `31` Persistence Boundary
- `29` Review Integrity
- `29` Source Of Truth

필요 작업:

- snapshot + task read를 한 번에 묶는 verification query 또는 service 구현
- approve 검증 결과를 풍부한 도메인 객체로 반환

권장 반환 객체:

- `allowed`
- `reason_code`
- `task_state`
- `state_version`
- `execution_mode`
- `resume_token_verified`
- `request_hash_verified`
- `frozen_plan_hash_verified`
- `snapshot_expires_at`
- `task_id`
- `session_id`

구현 원칙:

- boolean 하나만 반환하지 말고 reject 이유가 살아있는 결과 객체를 반환한다.
- 이후 response mapper가 그대로 외부 응답으로 바꿀 수 있어야 한다.

### 5. Approved Resume Persistence Strategy 구현

관련 아키텍처 문서:

- `31` Write Order
- `29` Atomic Transition
- `29` Recovery Matrix
- `20` Swarm / State Policy
- `32` approve flow draft / write order

필요 작업:

- `APPROVED_RESUME` strategy 정리
- `execution_consistency_coordinator.start_approved_resume(...)` 구현 보강
- `WAITING_REVIEW -> RUNNING` CAS 구현
- durable event stream 기준 `initial_cursor` 예약/확정 로직 추가

필수 보장:

- 같은 task에 approve가 중복 들어와도 CAS 선점 1회만 성공
- CAS 실패 시 현재 task truth를 읽어 duplicate 또는 already terminal로 수렴
- ack 이전에 `initial_cursor`가 확정됨

권장 coordinator 결과 객체:

- `transition_accepted`
- `task_id`
- `state_version`
- `execution_mode`
- `initial_cursor`
- `duplicate_decision`
- `already_terminal`
- `reason_code`

### 6. Task Event Stream Service 구현

관련 아키텍처 문서:

- `26` 4. Task Event Stream Subscription
- `26` 4A. STREAM Approve Resume Ordering Rule
- `29` Stream Resume Reliability
- `31` STREAM Resume Contract
- `32` Review Resume Stream Contract Draft

필요 작업:

- durable event append API
- cursor generation API
- replay read API
- live publish API
- approve용 `initial_cursor` 확보 API

권장 contract:

- `reserve_cursor_boundary(task_id)`
- `append_replayable_event(task_id, event)`
- `publish_live_event(task_id, event)`
- `subscribe(task_id, cursor, replay)`
- `read_from_cursor(task_id, cursor)`

구현 원칙:

- `current_cursor(task_id)` 같은 best-effort 조회값을 ack에 그대로 쓰지 않는다.
- ack에 넣는 `initial_cursor`는 replay contract를 보장하는 경계값이어야 한다.
- replay 가능한 이벤트와 live-only 이벤트를 구분한다.

replay 대상:

- `chunk`
- `a2ui`
- `done`
- `error`
- 필요 시 `progress`

replay 비대상:

- `heartbeat`

### 7. Review Application Service / hitl_gate_service 정리

관련 아키텍처 문서:

- `30` `hitl_gate_service` ownership
- `26` 2. Review Decide
- `27` HITL Architecture
- `25` Current Assessment

필요 작업:

- approve/cancel 분기 명확화
- approve는 snapshot verification + coordinator transition + execution resume 조합으로 정리
- cancel은 task truth 기준 terminal 또는 idempotent cancel로 정리

구현 원칙:

- review service가 직접 low-level store를 두드리지 않는다.
- verify, transition, resume, response shaping의 경계를 분리한다.
- planner 재호출 금지

### 8. Response Mapper 구현

관련 아키텍처 문서:

- `26` 2B. Approved Resume Delivery Rule
- `26` 2C. Review Decide Result And Error Rule
- `20` review approve delivery 규칙

필요 작업:

- approve accepted 응답 매핑
- resume rejected 응답 매핑
- already terminal 응답 매핑
- duplicate decision 응답 매핑

수용 기준:

- `execution_mode=STREAM` approve ack에 `stream_resume_required`, `stream_method`, `stream_endpoint`, `initial_cursor`가 포함된다.
- `execution_mode=SEND`는 stream 관련 필드를 생략하거나 null-safe 정책으로 일관되게 처리한다.
- reason code는 응답 body에 안정적으로 노출된다.

### 9. TaskEvents Endpoint 구현

관련 아키텍처 문서:

- `26` 4. Task Event Stream Subscription
- `20` Method Compatibility Policy
- `21` Compatibility Rules
- `29` Session Ownership

필요 작업:

- `tasks/events` / `TaskEvents` alias 처리
- `task_id` 필수 검증
- `cursor`, `replay` 선택 파라미터 처리
- session ownership 검증

수용 기준:

- retention 밖 cursor는 `CURSOR_EXPIRED`
- 없는 task는 `TASK_NOT_FOUND` 또는 표준 task read 오류
- cursor가 없으면 live attach
- cursor가 있으면 다음 event부터 전달

### 10. Replay-Safe Runtime Publisher 구현

관련 아키텍처 문서:

- `26` Streaming Rules
- `29` Stream Resume Reliability
- `31` STREAM Resume Contract
- `27` Persistence Boundary

필요 작업:

- runtime event 생성 시 replay 대상 여부 명시
- append 후 publish 또는 append/publish 일관 순서 결정
- terminal event 이후 stream 종료 처리

권장 원칙:

- replay 대상 event는 publish 전에 durable append가 완료되어야 한다.
- `done`, `error`는 항상 replay 가능해야 한다.
- terminal 이후 새 replay 대상 event append를 금지한다.

## Suggested Class Ownership

관련 아키텍처 문서:

- `30` responsibility separation guide
- `03` component architecture
- `20` core classes / core contracts

아래는 권장 책임 분리다. 실제 클래스명은 현재 코드에 맞춰 조정해도 되지만 책임은 유지해야 한다.

- `supervisor_a2a_request_validator`
  - review decide 최소 입력 계약 검증
- `supervisor_agent_service`
  - review use case routing
- `supervisor_review_application_service` 또는 `hitl_gate_service`
  - approve/cancel orchestration
- `supervisor_read_facade`
  - snapshot/task/review verification read
- `execution_consistency_coordinator`
  - `WAITING_REVIEW -> RUNNING` CAS
  - `initial_cursor` 확보
- `task_event_stream_service`
  - durable cursor/replay/live publish
- `supervisor_execution_service`
  - approved snapshot resume 실행
- `supervisor_exception_translator` / response mapper
  - reason code 외부 응답 변환

## Test Plan

관련 아키텍처 문서:

- `29` Reliability Test Matrix
- `26` 4A. STREAM Approve Resume Ordering Rule
- `31` Verification On Approve
- `31` STREAM Resume Contract

### Contract Tests

- `tasks/review/decide` with missing `task_id`
- `tasks/review/decide` with invalid `decision`
- approve ack for `STREAM` contains `initial_cursor`
- approve reject exposes `reason_code`

### Verification Tests

- session mismatch -> `SESSION_OWNERSHIP_MISMATCH`
- snapshot missing -> `SNAPSHOT_NOT_FOUND`
- snapshot expired -> `SNAPSHOT_EXPIRED`
- request hash mismatch -> `REQUEST_HASH_MISMATCH`
- frozen plan hash mismatch -> `FROZEN_PLAN_HASH_MISMATCH`
- drift blocked -> `PLAN_DRIFT_BLOCKED`

### State Transition Tests

- valid approve -> `WAITING_REVIEW -> RUNNING`
- duplicate approve -> `duplicate_decision`
- cancel wins before approve -> later approve reject
- terminal task approve -> `already_terminal` or `TASK_STATE_INVALID`

### Stream Resume Tests

- approve ack 직후 client가 늦게 재구독해도 첫 `chunk` replay 가능
- approve 직후 바로 `done` 발생해도 replay 가능
- `heartbeat`는 replay 안 되어도 무방
- terminal 이후 새 cursor 증가 없음

### Integration Tests

- `APPROVE` on `SEND`
- `APPROVE` on `STREAM`
- `CANCEL` on `WAITING_REVIEW`
- `tasks/events` with cursor replay
- retention expired cursor

## Anti-Patterns To Avoid

관련 아키텍처 문서:

- `31` What Must Not Be Frozen
- `31` Drift Policy
- `29` Atomic Transition
- `30` separation rules

- approve ack에 live emitter의 현재 메모리 cursor를 그대로 넣기
- approve 요청에 client가 보낸 hash만 믿고 server snapshot 검증 생략
- approve 검증 실패를 500 또는 raw exception message로 반환
- duplicate approve를 새 실행으로 처리
- terminal event를 replay 불가능하게 만들기
- review approve 이후 planner 재호출
- review service에서 persistence ordering을 직접 하드코딩

## Recommended Execution Order

관련 아키텍처 문서:

- `25` Delivery Priority
- `13` implementation roadmap
- `22` architecture document index

1. DTO / enum / reason code 추가
2. validator + response mapper 추가
3. snapshot verification read path 구현
4. approved resume strategy + coordinator 구현
5. task event durable cursor/replay 구현
6. execution resume 연결
7. contract tests
8. integration tests
9. audit/logging 보강

## File Output Expectation

관련 아키텍처 문서:

- `20` Core Contracts
- `31` Required Fields
- `32` implementation draft

최종적으로 코드 기준에서 아래 산출물이 보여야 한다.

- review decide request/response DTO
- reject reason code enum
- snapshot verification result object
- approved resume coordinator result object
- durable task event stream service API
- replay-safe integration test

## Post-Implementation Architecture Code Review

관련 아키텍처 문서:

- `20` routing package / class spec
- `26` entry contract and runtime flow
- `29` security and reliability model
- `30` responsibility separation guide
- `31` FrozenExecutionPlan schema
- `32` FrozenExecutionPlan implementation draft
- `06` supervisor A2A request sequence
- `19` supervisor runtime sequence

구현 완료 후에는 반드시 아키텍처 정본 문서를 기준으로 코드리뷰를 수행해야 한다.
이 단계는 선택이 아니라 구현 완료 정의의 일부다.

코드리뷰의 목적은 "코드가 돌아가는가"만 확인하는 것이 아니라, 아래 질문에 답하는 것이다.

- 아키텍처 문서에서 정의한 계약을 코드가 실제로 지키는가
- 구현 편의 때문에 정본 문서와 다른 동작이 들어가지는 않았는가
- 문서에는 있는데 코드에 빠진 보장이나 테스트가 무엇인가
- 코드에는 있는데 문서에 없는 비공식 동작이 생기지는 않았는가

### Review Completion Criteria

코드리뷰는 아래 관점으로 구현 충실도를 평가해야 한다.

- 계약 충실도
  - `tasks/review/decide` 최소 입력, 결과, reason code가 문서와 일치하는가
- 상태 전이 충실도
  - `WAITING_REVIEW -> RUNNING` CAS 및 duplicate/terminal 처리 규칙이 일치하는가
- resume ordering 충실도
  - `snapshot verify -> RUNNING CAS -> initial_cursor 확정 -> approve ack -> runtime event append/publish` 순서를 지키는가
- replay 충실도
  - `initial_cursor`와 replay-safe event delivery가 문서 의미와 일치하는가
- 책임 분리 충실도
  - validator/service/coordinator/event stream 책임이 문서 경계대로 분리됐는가
- 오류 처리 충실도
  - raw exception이 아니라 표준 reason code/result로 수렴하는가
- 테스트 충실도
  - 문서에서 요구한 approve/reject/replay race 시나리오를 테스트가 덮는가

### Mandatory Review Checklist

코드리뷰 시 반드시 확인:

- 구현된 endpoint / method family가 `20`, `26`과 일치하는가
- approve/cancel 흐름이 `06`, `19` sequence와 논리적으로 일치하는가
- approve verification 항목이 `31` Verification On Approve를 빠짐없이 반영하는가
- drift block 처리가 `31` Drift Policy와 일치하는가
- stream resume reliability가 `29`와 충돌하지 않는가
- persistence ordering이 `31` Write Order와 일치하는가
- 책임 분리가 `30` guide를 위반하지 않는가
- 테스트가 `29` Reliability Test Matrix와 이번 구현 범위를 덮는가

### Review Findings Classification

코드리뷰 결과는 아래 심각도로 분류한다.

- `Critical`
  - 문서상 필수 안전 규칙 위반
  - 중복 실행, 이벤트 유실, 잘못된 ownership, terminal state 오염 가능성
- `Major`
  - 계약은 대체로 맞지만 외부 계약/테스트/오류 처리 불완전
- `Minor`
  - 리팩토링, 명확화, 로깅/테스트 보강 필요
- `Note`
  - 현행 설계상 허용되지만 추후 정리 권장

## Code Review Result Document

구현 완료 후에는 코드리뷰 결과를 별도 문서로 반드시 남겨야 한다.

권장 파일명:

- 루트 기준 `IMPLEMENTATION_ARCHITECTURE_CODE_REVIEW_REPORT.md`

문서 목적:

- "얼마나 구현을 충실하게 완료했는지"를 아키텍처 정본 기준으로 기록
- 남은 갭과 리스크를 구조적으로 남김
- 이후 추가 코드 수정과 리팩토링의 입력 문서로 사용

결과서에는 최소 아래 항목이 포함되어야 한다.

### 1. Review Scope

- 리뷰한 코드 범위
- 기준으로 삼은 아키텍처 문서 번호
- 리뷰 시점의 브랜치/커밋/작업 상태

### 2. Architecture Compliance Summary

- 전체 구현 충실도 요약
- 구현 완료 비율 또는 상태
  - `Implemented`
  - `Partially Implemented`
  - `Not Implemented`
  - `Diverged`

### 3. Checklist-by-Checklist Review

아래 항목별로 판정:

- Review Decide Contract
- Approve Verification
- STREAM Approve Resume Ordering
- Task Event Replay
- Audit And Logging
- Tests

각 항목에는 반드시 포함:

- 관련 문서 번호
- 관련 코드 파일
- 판정
- 근거
- 남은 갭

### 4. Findings

반드시 severity 순으로 정리:

- `Critical`
- `Major`
- `Minor`
- `Note`

각 finding에는 반드시 포함:

- 제목
- 관련 문서 번호
- 관련 코드 파일 / 라인
- 현재 구현
- 왜 문제인지
- 권장 수정 방향

### 5. Refactoring / Follow-up Actions

- 즉시 수정해야 하는 항목
- 다음 배치에서 수정할 항목
- 문서 수정이 필요한 항목
- 테스트 추가가 필요한 항목

### 6. Final Verdict

반드시 아래 중 하나로 결론:

- `Architecture-Aligned`
- `Architecture-Aligned With Gaps`
- `Implementation Diverges From Architecture`

## Mandatory Follow-Up Rule

코드 구현 완료 후 작업을 종료하면 안 된다.
반드시 아래 순서를 따른다.

1. 구현 완료
2. 아키텍처 기준 코드리뷰 수행
3. `IMPLEMENTATION_ARCHITECTURE_CODE_REVIEW_REPORT.md` 작성
4. 결과서의 `Critical`, `Major` 항목 기준으로 코드 추가 수정 및 리팩토링 수행
5. 필요한 테스트 보강
6. 결과서 verdict 갱신

즉 코드리뷰 결과서는 보고서가 아니라 후속 수정의 실행 입력이어야 한다.

## Harness Prompt Requirement

하네스 또는 작업 프롬프트에는 아래 요구사항을 반드시 포함해야 한다.

```text
이 작업은 IMPLEMENTATION_EXECUTION_CHECKLIST.md를 정본으로 따른다.
구현 완료 후 작업을 종료하지 말고, 반드시 아키텍처 문서(20, 26, 29, 30, 31, 32, 06, 19) 기준 코드리뷰를 수행하라.
코드리뷰 결과는 루트의 IMPLEMENTATION_ARCHITECTURE_CODE_REVIEW_REPORT.md에 작성하라.
결과서에는 구현 충실도, 관련 문서 번호, 관련 코드 파일, finding severity(Critical/Major/Minor/Note), 수정 필요 항목을 포함하라.
그 다음 결과서의 Critical/Major 항목을 기준으로 코드 추가 수정과 리팩토링을 수행하라.
최종 보고는 "구현 완료"만이 아니라 "코드리뷰 결과 반영 후 최종 상태"까지 포함해야 한다.
```

### Harness Enforcement Rule

하네스 프롬프트 또는 작업 지시문은 아래를 강제해야 한다.

- 구현 완료만으로 종료 금지
- 코드리뷰 결과서 작성 의무
- 결과서 기반 후속 수정 의무
- 아키텍처 문서 번호 추적 의무
- review finding severity 분류 의무
- Critical/Major 미해결 시 종료 불가 또는 명시적 잔여 리스크 선언 의무

### Recommended Harness Output Order

최종 산출 순서:

1. 코드 구현
2. 테스트 실행
3. 아키텍처 기준 코드리뷰
4. `IMPLEMENTATION_ARCHITECTURE_CODE_REVIEW_REPORT.md` 작성
5. 결과서 기반 추가 수정 / 리팩토링
6. 최종 요약

## Final Note

지금 단계에서 추가 아키텍처 리뷰를 늘리는 것은 효율이 낮다.
이 문서의 남은 가치는 "무엇을 구현해야 하는가"를 닫는 데 있다.
이후 검토는 문서 품질이 아니라 코드가 이 체크리스트를 따르는지 기준으로 진행한다.
