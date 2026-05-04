# 14. Supervisor Agent Package And Dependency Policy

Updated: 2026-05-04 (Class Sync)

## Base Package

- `app` (at `src/supervisor-agent/app`)

## Dependency Rules

- `api -> application/execution -> ports(plan/invoke/compose/graph)`
- `api -> application/read -> read facade -> query factory/query -> store`
- `api -> application/persistence -> persistence facade -> strategy -> coordinator -> store`
- `application/execution -> application/persistence (via facade)`
- `application/execution -> application/read (via facade)`
- `invoke -> a2a client/registry` logic
- `plan/compose -> llm runtime` only
- 상위 계층은 구현체가 아니라 protocol/interface(ports)에 의존한다.

## Python Layering Rule (CQRS Optimized)

- **Decoupled Worker Architecture**: API 계층과 Background Worker 계층을 분리하여 확장성과 안정성을 보장한다.
- **CQRS Patterns**:
  - `application/execution`: Command 및 전체 유즈케이스 흐름 제어 (`SupervisorAgentService`, `WorkerExecutionService`).
  - `application/persistence`: 상태 변경(Write) 및 트랜잭션/일관성 관리 (`SupervisorExecutionPersistenceService`, `ExecutionConsistencyCoordinator`).
  - `application/read`: 상태 조회(Read) 및 복합 쿼리/검증 로직 (`SupervisorReadFacade`).
- **Infrastructure Isolation**: Redis Client, LLM Runtime 등 외부 의존성은 `infrastructure` 하위에 격리한다.

## Independence & Environment Policy

- **Single Shared Venv**: 개발 환경에서는 루트의 `.venv`를 공유하여 의존성을 관리한다.
- **Independent PYTHONPATH**: 각 에이전트는 기동 시 `PYTHONPATH=.`를 설정하여 서로의 소스 코드를 참조할 수 없도록 격리한다.
- **Separate Server Ready**: 각 에이전트 폴더(`src/*`)는 물리적으로 다른 서버로 이전하더라도 루트에 `.venv`만 구성하면 즉시 동작 가능한 독립적 구조를 가진다.
- **Standard Env Naming**: `load_dotenv()`를 명시적으로 호출하여 `.env`의 시스템 환경 변수를 자동 등록한다.

## Hardcoding Elimination (Enum First)

- **AgentRole**: `user`, `assistant`, `supervisor` 등 모든 역할은 `domain/enums.py`의 `AgentRole`을 사용한다.
- **EventType**: 모든 진행 상태 및 이벤트 메시지는 `EventType` Enum을 통해 정의한다.
- **RedisNamespace**: Redis 키의 접두사(`package:`) 및 상세 네임스페이스는 `RedisNamespace` Enum으로 관리한다.

## Folder Rules

- `main.py`: FastAPI 서버 진입점.
- `worker.py`: 백그라운드 워커 진입점.
- `app/api`: FastAPI Routers 및 Endpoints.
- `app/application`: 비즈니스 로직.
- `app/domain`: 엔티티, VO, Enums.
- `app/infrastructure`: 외부 시스템 연동 (Redis, LLM).
- `app/adapters`: 외부 인터페이스 구현체.
- `app/ports`: 추상 인터페이스 정의.
- `app/schemas`: Pydantic 기반 모델.

## Design Rules

- **Idempotency**: `request_id` 기반의 Redis `SET NX` 분산 락을 사용하여 중복 실행을 원자적으로 차단한다.
- **Redis Prefixing**: 모든 Redis 키는 `package:` 접두사를 사용하여 다른 시스템 데이터와 격리한다.
- **Direct Answer**: 하위 에이전트가 필요 없는 요청은 즉시 답변 경로(Shortcut)를 제공한다.
