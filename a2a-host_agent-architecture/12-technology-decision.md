# 12. Supervisor Agent Technology Decision

Updated: 2026-04-28 (Implementation Refined)

## 2026-04-28 아키텍처 확정 및 반영 결정

- **분리된 실행 모델(Decoupled Execution)**: API 계층(FastAPI)과 실행 계층(Background Worker)을 Redis Queue를 통해 분리한다. 이는 대규모 트래픽 분산과 실행 안정성을 보장한다.
- **오케스트레이션**: `LangGraph + Swarm State Store` 하이브리드 모델을 사용하며, 실제 노드 실행은 백그라운드 워커(`worker.py`)에서 담당한다.
- **멱등성(Idempotency)**: 별도의 복잡한 서비스 대신 `ExecutionConsistencyCoordinator`에 통합하여 Redis `SET NX` 기반의 분산 락/예약 방식을 사용하여 중복 요청을 원자적으로 차단한다.
- **무결성 및 보안(Integrity & Audit)**: `SnapshotVerificationQuery`와 `PlanHashCalculator`를 통해 실행 계획의 해시 검증, 세션 소유권 체크, 버전 기반 낙관적 잠금(Optimistic Locking)을 수행한다.
- **이벤트 스트리밍**: Redis Stream(`XADD/XREAD`) 기반의 `task_event_stream_service`를 사용하여 진행 상태를 영속화하고 신뢰할 수 있는 Replay를 지원한다.
- **에러 핸들링**: `SupervisorExceptionTranslator`를 통해 도메인 예외를 표준 JSON-RPC 에러로 변환하며, 워커 내부 예외는 태스크 이벤트 스트림으로 안전하게 전파한다.

## Final Choice

- `Python 3.11+ + FastAPI + LangChain + LangGraph + Redis (Queue/Stream/Store) + A2A(JSON-RPC/SSE)`

## Why

- **Redis (Multi-role)**: 단순 저장소를 넘어 Task Queue(비동기 실행), Event Stream(실시간 상태 전파), Request Lock(멱등성 보장)의 중추 역할을 수행한다.
- **LangGraph (Node-based)**: `select -> invoke -> handoff -> merge`의 상태 전이를 명확히 강제하여 복잡한 오케스트레이션 가독성을 높인다.
- **Decoupled Worker**: HTTP 요청 수명 주기에 얽매이지 않는 견고한 실행 환경을 제공하며, 장애 시 NACK/Re-queue 메커니즘을 지원한다.

## Scope

- Supervisor agent는 하위 에이전트를 A2A로만 호출한다.
- **Direct Answer Shortcut**: 하위 에이전트 호출이 필요 없는 단순 응답은 그래프를 타지 않고 즉시 Compose로 분기하여 자원을 절약한다.
- **Plan Drift Block**: 승인 시점과 실행 시점 사이의 에이전트 상태 변화(차단/은퇴 등)를 감지하여 실행을 거부한다.

## Python Implementation Baseline

- **request/response schema**: `pydantic`
- **runtime configuration**: `pydantic-settings` + `yaml`
- **async HTTP client**: `httpx`
- **event stream delivery**: FastAPI `StreamingResponse` + `redis.asyncio`
- **logging/audit**: `structlog` (Structured Contextual Logging)
- **test baseline**: `pytest`, `pytest-asyncio`
