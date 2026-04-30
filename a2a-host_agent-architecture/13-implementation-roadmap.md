# 13. Supervisor Agent Implementation Roadmap

Updated: 2026-04-28 (Status Updated)
Source baseline: `smart-supervisor-sub-agent`

## Phase 0 ~ 6: Completed (Core Foundation & Features) ✅

- **Phase 0: Documentation Sync**: Java 표기 제거 및 Python 패키지 구조 동기화 완료.
- **Phase 1: Configuration**: `settings/*.yml` 및 Pydantic 기반 설정 로더 구현 완료.
- **Phase 2: Persistence**: Redis 기반 Store들 및 `ExecutionConsistencyCoordinator` (CAS 로직) 구현 완료.
- **Phase 3: Application Layer**: `SupervisorAgentService`, `HitlGateService`, API Endpoint 구현 완료.
- **Phase 4: LangGraph Core**: `select -> invoke -> handoff -> merge` 그래프 및 상태 전이 구현 완료.
- **Phase 5: Routing / Handoff**: `A2AInvocationService` (서킷 브레이커/재시도 포함) 및 핸드오프 정책 구현 완료.
- **Phase 6: HITL / Security**: `APPROVE/CANCEL` 흐름 및 `SnapshotVerificationQuery` (해시/버전 검증) 구현 완료.

## Phase 7: Background Worker & Event Streaming ✅

- **Decoupled Execution**: `worker.py` (EnterpriseWorker) 구현 및 Redis Queue 연동 완료.
- **Event Streaming**: Redis Stream 기반의 `TaskEventStreamService` 및 SSE 구독 엔드포인트 구현 완료.
- **Idempotency**: Redis `SET NX` 기반 멱등성 체크 로직 `ExecutionConsistencyCoordinator`에 통합 완료.

## Phase 8: Hardening & Optimization (In-Progress) 🔄

- **Direct Answer Shortcut**: 플래너가 바로 답변 가능하다고 판단할 경우 그래프를 스킵하는 최적화 경로 보완.
- **Plan Drift Guard**: 에이전트 은퇴/차단 상태 실시간 반영 로직 고도화.
- **Observability**: `structlog` 기반의 맥락적 로깅(Contextual Logging) 강화.
- **Automated Testing**: `pytest-asyncio` 기반의 시나리오별 통합 테스트 확충.

## Phase 9: Future Extensions (Plan) 🚀

- **REVISE Decision**: 사용자가 계획을 수정하여 다시 제출하는 인터랙티브 HITL 확장.
- **Multi-modal Support**: A2A 프로토콜 확장에 따른 이미지/파일 처리 지원.
- **Advanced Swarm Governance**: 여러 Supervisor 간의 상태 공유 및 협업 모델 연구.
