# 29. Supervisor Security And Reliability Model

Updated: 2026-04-25
Current baseline: `src/app`

## Purpose

본 문서는 supervisor의 보안, 상태 무결성, 장애 복구, 운영 안전장치를 Python runtime 기준으로 정의한다.

## Security Assumption

- 내부 기준 `session_id`는 외부 인증을 통과한 신뢰 가능한 식별자라고 가정한다.
- 이 가정 위에서도 supervisor 내부에서 ownership과 consistency를 강제해야 한다.

## Mandatory Security Rules

### Session Ownership

- `tasks/get`, `tasks/list`, `tasks/cancel`, `tasks/review/get`, `tasks/review/decide`는 모두 caller session ownership을 검증한다.
- endpoint, lifecycle, store 중 한 레이어에만 맡기지 않고 방어적으로 중복 검증한다.

### Idempotency

- key는 `session_id + method + request_id + normalized params hash`를 사용한다.
- `request_id` 단독 dedupe를 금지한다.
- review decide도 별도 idempotency 경계를 가진다.

### Review Integrity

- review open 전에 immutable snapshot 저장
- approve 시 snapshot ownership과 version 검증
- approve 시 `frozen_plan_hash` 검증
- mismatch 시 resume 거부

### Prompt And Route Safety

- planner, HITL, compose 입력 sanitize
- route allowlist는 planning 결과와 invoke 직전 모두에서 검증
- method allowlist는 validator와 invoker 양쪽에서 검증

## Reliability Rules

### Source Of Truth

- task lifecycle이 source of truth다.
- review, checkpoint, swarm, snapshot은 subordinate record다.
- lifecycle service는 state mutation intent를 만들 수 있지만 실제 Redis write는 facade/coordinator 경계에서만 수행한다.

### Partial Write Recovery

- 다중 저장소 write는 `supervisor_execution_persistence_service` facade 경로로만 진입한다.
- 부분 실패 시 retry 또는 reconciliation marker를 남긴다.
- recovery는 task terminal state와 subordinate record version을 대조해 수행한다.

### Atomic Transition

- 단일 원자 전이를 보장해야 한다.
- terminal state 우선순위를 명시한다.
- `cancel`, `complete`, `fail` 경합 시 마지막 write wins를 허용하지 않는다.

## Runtime Guardrails

- timeout
- retry with bounded backoff
- circuit breaker
- cooldown
- degraded completion
- explicit controlled failure

## Logging And Audit

- INFO 로그에는 식별자, 상태, 요약만 남긴다.
- raw message, arguments, downstream payload는 DEBUG 또는 마스킹 대상으로 제한한다.
- review open, approve, cancel, degraded completion, forced recovery path는 audit 대상이다.

## Stream Resume Reliability

- `tasks/events`는 task 단위 단조 증가 cursor를 사용해야 한다.
- `heartbeat`는 retention 대상이 아니어도 되지만 `progress/chunk/a2ui/done/error`는 replay 가능해야 한다.
- approve ack의 `initial_cursor`는 client가 재구독 시작점으로 사용할 수 있어야 한다.
- approve 처리에서 `WAITING_REVIEW -> RUNNING` CAS와 replay 가능한 첫 event 기준점 확보는 논리적으로 하나의 resume transaction처럼 동작해야 한다.

## Reliability Test Matrix

1. 다른 session의 task/read access 차단
2. 같은 JSON-RPC `id` 재사용 시 session 경계 유지
3. concurrent cancel/complete/fail 충돌에서 상태 일관성 유지
4. snapshot version mismatch에서 approve 거부
5. frozen plan hash mismatch에서 approve 거부
6. partial write 후 reconciliation 가능
7. circuit open과 cooldown이 동시에 걸린 route의 안전한 처리
8. compose/A2UI failure가 final result channel 전체를 훼손하지 않음
