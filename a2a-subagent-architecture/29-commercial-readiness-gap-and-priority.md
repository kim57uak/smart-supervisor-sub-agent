# 29. Commercial Readiness Gap And Priority

Updated: 2026-04-28 (Aligned with Supervisor Enterprise Architecture)

## Strength

- **Hexagonal Architecture**: 기술 변화(Redis, MCP, LLM)에 유연하게 대응 가능한 구조 확보.
- **Decoupled Worker**: 트래픽 부하 분산 및 실행 안정성을 위한 비동기 처리 구조 완성.
- **Unified Traceability**: Supervisor와 연계된 `trace_id + request_id + session_id` 전파 체계 수립.
- **Consistency**: Supervisor Agent와 동일한 설계 철학 및 패키지 구조 적용.

## Mandatory Gap (Resolved in Design)

- **Worker separation**: API 부하와 LLM/MCP 실행 부하 격리 완료.
- **Atomic Persistence**: Redis `MULTI/EXEC` 기반의 원자적 상태 관리 설계 반영.
- **Scoped Tool Loading**: Planner가 권한이 없는 도구에 접근하는 것을 원천 차단하는 도구 카탈로그 서비스 설계.

## Next Action Priority (Implementation)

1. **Work Package A. Runtime Protection & Guardrails** (P0)
   - 토큰 제한, 타임아웃, 도구 호출 횟수 제한 구현.
2. **Trace & Correlation Service** (P0)
   - 전 계층 로그 및 요청 헤더에 correlation key 전파.
3. **Idempotency Logic (Redis CAS)** (P1)
   - 중복 요청 방지 및 결과 캐싱.
4. **LangGraph Persistence Checkpointers** (P1)
   - 실행 중단 시 복구 및 상태 전이 추적.
5. **Streaming Hardening (Progress Events)** (P2)
   - Redis Stream을 통한 정규화된 진행 상태 메시지 발행.
