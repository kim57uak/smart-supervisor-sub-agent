# 29. Supervisor Security & Reliability Model

Updated: 2026-04-28 (Implementation Refined)

## Security & Integrity Guard (Audit-First)

Supervisor는 모든 실행 승인(Approve) 시점에 **`SnapshotVerificationQuery`**를 통해 무결성을 전수 조사한다.

- **Request Hash Verification**: 원본 요청 메시지가 위변조되었는지 재계산하여 대조한다. (`PlanHashCalculator`)
- **Plan Hash Verification**: 생성된 라우팅 계획 및 실행 제약 조건이 변조되지 않았는지 검증한다.
- **Drift Policy Enforcement**: 승인 시점에는 가용했던 에이전트가 실행 시점에 차단되거나 은퇴했는지 체크하여 보안 드리프트를 차단한다.
- **Session Ownership Guard**: 세션 소유자만이 해당 태스크의 상태를 조회하거나 승인/취소할 수 있도록 모든 레이어에서 검증한다.

## Reliability & Consistency (Atomic-First)

- **Atomic State Transition**: Redis `WATCH/MULTI/EXEC` 기반의 CAS 로직을 통해 여러 워커가 경합하더라도 중복 승인이나 상태 꼬임이 발생하지 않도록 보장한다. (`ExecutionConsistencyCoordinator`)
- **Durable Event Log**: Redis Stream을 사용하여 모든 진행 이벤트를 영속화하며, 연결 유실 시 `cursor` 기반의 정확한 Replay를 지원한다.
- **Decoupled Worker Resilience**: API 서버와 분리된 워커가 독립적으로 실행되며, 워커 장애 시 Redis Queue의 비가시성 타임아웃 또는 재큐잉 메커니즘을 통해 실행 안정성을 확보한다.

## Runtime Guardrails

- **Circuit Breaker**: 에이전트별 연속 실패 시 자동 차단하여 전체 시스템으로의 장애 전파를 방지한다.
- **Idempotency Guard**: `request_id` 기반의 분산 락을 통해 동일 요청에 대한 중복 실행을 원천 차단한다.
- **Prompt Sanitization**: `PromptInjectionGuard`를 통한 모든 외부 입력의 유해 패턴 필터링을 강제한다.
