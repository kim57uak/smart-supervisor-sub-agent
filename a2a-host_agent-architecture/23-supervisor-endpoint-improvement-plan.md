# 23. Supervisor A2A Endpoint Implementation & Improvement

Updated: 2026-04-28 (Implementation Refined)

## Implementation Status ✅

- **Single Entrypoint**: `/a2a/supervisor`에서 JSON-RPC를 단일하게 수용하도록 구현 완료.
- **Protocol Separation**: Unary 요청(Submission)과 Stream 구독(SSE)을 분리하여 안정성 확보.
- **Validation**: `method-allowlist` 및 Pydantic 기반 파라미터 검증 통합 완료.
- **Idempotency**: Redis `SET NX` 기반 멱등성 선점 로직 적용 완료.

## Refined Interface Plan

1. **Submission & Polling Model**
   - 모든 실행 요청은 즉시 `task_id`를 반환하며, 클라이언트는 해당 ID로 진행 상태를 구독한다.
   - `tasks/events` (TaskEvents) 메서드를 통해 Redis Stream의 이벤트를 안전하게 Replay/Subscribe 한다.

2. **Error Normalization**
   - `SupervisorExceptionTranslator`를 통해 모든 내부 오류를 표준 JSON-RPC 에러 코드(-32600 계열)로 매핑.
   - 보안을 위해 외부 응답에서는 상세 Stack trace를 제거하고 `ReasonCode` 위주로 전달.

3. **Method Alias Management**
   - `legacy` (snake_case)와 `v1.0` (PascalCase) 메서드 명칭을 `validator` 계층에서 정규화하여 비즈니스 로직의 복잡도 제거.

4. **SSE Framing Rule**
   - 모든 스트리밍은 `event: {type}\ndata: {json}\n\n` 규격을 엄격히 준수.
   - `chunk`, `reasoning`, `a2ui`, `progress`, `done`, `error` 타입으로 고정.
