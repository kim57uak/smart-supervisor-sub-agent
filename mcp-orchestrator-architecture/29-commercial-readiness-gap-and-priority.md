# 29. Commercial Readiness Gap And Priority

Updated: 2026-04-25

## Strength

- endpoint / facade / orchestrator / graph / compose 경계가 분리되어 있다.
- `LangGraph`를 이용한 `plan -> execute -> finalize` 제어 흐름이 정의되어 있다.
- protocol target과 runtime dependency를 분리해 관리할 수 있는 구조다.

## Mandatory Gap

- request correlation(`trace_id + request_id + session_id`) 전 구간 전달
- correlation key는 supervisor 전달값 우선, 누락 시에만 생성
- Redis key에 `session_id`를 포함하는 정책은 유지하되 correlation 전파를 대체하지 못한다.
- planner가 전체 tool registry를 보지 않도록 scoped tool catalog loading을 강제해야 한다.

## Priority

1. runtime protection
2. trace propagation
3. idempotency
4. scoped tool allowlist
5. streaming hardening
