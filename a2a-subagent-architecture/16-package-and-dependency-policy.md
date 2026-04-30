# 16. Package And Dependency Policy

Updated: 2026-04-29 (Independence & Class Sync)

## Base Package

- `app` (at src/sub-agent/app)

## Folder Structure (Hexagonal + CQRS)

- `main.py`: FastAPI server entry point.
- `worker.py`: Background worker entry point.
- `app/adapters`: Implementation of Ports (Stores, LLM, MCP, Orchestration)
- `app/api`: FastAPI Routers (agent, a2a, support)
- `app/application`: Business Logic
    - `execution`: Usecases, Worker, Progress Publishing (AgentChatUseCase, AgentExecutor)
    - `persistence`: Atomic state transitions (AgentPersistence, StateCoordinator)
    - `read`: Read-only facades and queries (AgentReader)
- `app/ports`: Abstract Interface Definitions (interfaces.py)
- `app/domain`: Entities, Value Objects, Enums (models.py, enums.py)
- `app/infrastructure`: Low-level clients (RedisClient, LlmRuntime)
- `app/common`: Shared utilities
- `app/schemas`: Pydantic Request/Response schemas
- `app/services`: Domain services (AgentAuthorizationService)

## Independence & Environment Policy

- **Single Shared Venv**: 루트의 `.venv`를 공유하여 의존성을 효율적으로 관리한다.
- **Independent PYTHONPATH**: 각 에이전트는 기동 시 `PYTHONPATH=.`를 설정하여 독립적 구조를 유지한다.
- **Separate Server Ready**: 루트에 `.venv`만 구성하면 즉시 동작 가능한 독립적 구조를 유지한다.
- **Standard Env Naming**: `load_dotenv()`를 명시적으로 호출하여 시스템 환경 변수로 자동 등록한다.

## Hardcoding Elimination (Enum First)

- **AgentRole**: `user`, `assistant`, `system`, `tool`은 `domain/enums.py`의 `AgentRole` 사용.
- **EventType**: 진행 상태 메시지(`PLANNING`, `CHUNK` 등)는 `EventType` Enum 사용.
- **RedisNamespace**: Redis 키 네임스페이스는 `RedisNamespace` Enum 사용.

## Dependency Direction (Mandatory)

- `api -> application/execution -> ports` (Dependency Inversion)
- `application/execution -> application/read/persistence` (Tiered access)
- `adapters -> ports` (Implementation)
- `application -> domain` (Domain is the core)
- `worker.py` -> `application/execution`

## Centralized Redis Management Policy

- **Global Prefixing**: 모든 Redis 키는 `RedisNamespace.GLOBAL_PREFIX` (`package:`) 사용.
- **Centralized Read (Query)**: 모든 데이터 조회는 `AgentReader`를 통해서만 수행한다.
- **Centralized Write (Command)**: 모든 데이터 변경은 `AgentPersistence`를 통해서만 수행한다.
