# 26. Supervisor Entry Contract & Runtime Flow

Updated: 2026-04-28 (Implementation Refined)

## Entry Contract

- **`POST /a2a/supervisor`**: 단일 통합 진입점 (SendMessage, SendStreamingMessage 등).
- **`POST /a2a/supervisor/stream`**: 태스크 이벤트 구독 및 Replay 엔드포인트.
- **`tasks/review/decide`**: 리뷰 승인/취소 액션.

## Canonical Runtime Flow (Decoupled Worker)

### 1. Execution Request (SendMessage)
1. **Admission**: `consistency_coordinator`가 `request_id` 기반 멱등성을 체크하고 `task_id`를 선점한다. 중복 요청 시 기존 태스크 정보를 즉시 반환한다.
2. **Sanitization**: `PromptInjectionGuard`가 입력 텍스트의 유해 패턴을 필터링한다.
3. **HITL Evaluation**: `hitl_gate_service`가 플래닝을 수행하고 리뷰 필요 여부를 판단한다.
4. **Enqueuing**: 리뷰 불필요 시 `task_queue_service`를 통해 백그라운드 워커로 작업을 이관하고 `STREAMING` 응답을 반환한다.
5. **Execution (Worker)**: 워커가 그래프를 실행하고 진행 상태를 Redis Stream에 발행한다.

### 2. Review Decision
1. **Verification**: `SnapshotVerificationQuery`가 스냅샷의 해시, 소유권, 버전, 드리프트 여부를 전수 검증한다.
2. **Approval**: 승인 시 `consistency_coordinator`가 상태를 원자적으로 `RUNNING`으로 전이시키고 워커 큐에 적재한다.
3. **Resume**: 클라이언트는 승인 Ack 수신 후 `/stream` 엔드포인트에서 이벤트를 다시 구독한다.

## Task Event Subscription Rules

- **Polling**: 클라이언트는 `tasks/events` 메서드로 구독을 시작한다.
- **Persistence**: 모든 이벤트(`chunk`, `reasoning`, `a2ui` 등)는 Redis Stream에 영속화되어 연결 유실 시 `cursor` 기반 Replay를 지원한다.
- **Isolation**: 각 태스크는 독립된 이벤트 스트림을 가지며 타 세션의 이벤트 접근이 차단된다.
