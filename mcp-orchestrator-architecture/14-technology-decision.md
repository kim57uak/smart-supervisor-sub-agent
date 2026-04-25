# 14. Technology Decision

Updated: 2026-04-25

## Final Stack

- `Python 3.11+`
- `FastAPI + Pydantic`
- `LangChain + LangGraph`
- `A2A Protocol v1.0.0`
- `Redis`
- existing MCP runtime concepts reimplemented behind Python adapters

## Why This Stack

- `Python 3.11+`
  - LangChain/LangGraph 최신 안정 버전과 호환되는 기준선이다.
  - 비동기 I/O, typing, testing 생태계가 agent runtime 설계와 잘 맞는다.
- `FastAPI + Pydantic`
  - HTTP/A2A entrypoint, validation, SSE, typed contract를 단순하게 구현할 수 있다.
- `LangChain + LangGraph`
  - planning, execute, compose, checkpoint를 Python runtime에서 자연스럽게 분리한다.
  - `plan -> execute -> finalize -> compose` 흐름을 명시적 상태 그래프로 유지할 수 있다.
- `A2A Protocol v1.0.0`
  - sub-agent와 supervisor 사이의 안정적인 JSON-RPC/SSE 경계를 유지한다.
  - canonical contract는 current PascalCase method family를 사용하고 legacy slash family는 inbound compatibility alias로만 유지한다.
- `Redis`
  - conversation history, graph checkpoint, A2A task state, idempotency cache 저장에 적합하다.
- existing MCP runtime concepts
  - 기존 문서의 registry/session/transport 개념은 유지하되 Python adapter 계층으로 재구성한다.
  - 구현 기준은 `httpx`, `anyio`, provider SDK, MCP adapter layer다.

## Design Principles

- 추상화 우선
  - endpoint는 use case를 모르고 application service contract만 안다.
  - orchestration은 `planning_service`, `tool_execution_service`, `response_compose_service`, `agent_llm_runtime` 같은 port에 의존한다.
- SOLID
  - SRP: planning, execution, compose, store, lifecycle, auth를 분리한다.
  - OCP: 새로운 scope, model, protocol이 추가되어도 핵심 흐름을 깨지 않고 확장한다.
  - DIP: 상위 계층은 Redis, provider SDK, MCP transport concrete class가 아니라 port에 의존한다.
- 재활용성
  - MCP registry, session, transport 개념은 공용 adapter layer로 재사용한다.
  - prompt는 `settings/system_prompt.yml`과 prompt service로 중앙화한다.
  - Redis key/TTL 정책도 공용 factory/policy로 재사용한다.
- Python 작성 규칙
  - 함수, 변수, 모듈, 필드명은 `snake_case`
  - 클래스명만 `PascalCase`
  - 내부 구현에서는 `session_id`, `request_id`, `trace_id`를 사용하고 외부 A2A compatibility layer에서만 legacy field alias를 매핑한다.
  - public Python API와 핵심 모듈에는 docstring과 타입힌트를 적용한다.

## Mandatory Implementation Scope

현재 즉시 구현 범위는 아래로 고정한다.

- `Work Package A. Runtime Protection`
- `P0. Guardrails And Runtime Limits`
- `Operational Safety And Resilience`
- request correlation: `trace_id + request_id + session_id` 전 구간 전달

추가 규칙

- `session_id`를 Redis key에 포함하는 것만으로 추적/격리 요구를 충족했다고 보지 않는다.
- correlation key는 로그/메트릭/trace까지 동일하게 전달해야 한다.
- supervisor 전달값이 있으면 sub-agent는 그 값을 우선 사용한다.
- supervisor 값이 누락된 경우에만 sub-agent가 해당 값을 신규 생성한다.
- 위 범위를 제외한 나머지 개선 과제는 별도 요청 전까지 구현하지 않는다.

## Python Dependency Baseline

```txt
python = 3.11+
fastapi
pydantic
langchain
langgraph
httpx
redis
python-dotenv
pytest
pytest-asyncio
```

## Reuse/Replace Policy

- 재사용
  - 기존 MCP runtime의 개념적 경계
  - scope별 request DTO / history normalization 규칙
  - MCP server allowlist 정책
- 신규 추가
  - `app/api/*`
  - `app/application/*`
  - `app/domain/*`
  - `app/infrastructure/*`
  - `app/a2a/*`
- 점진 전환
  - 기존 레거시 계층 설명은 Python `endpoint -> application -> domain -> infrastructure` 기준으로 재해석한다.
  - 기존 모델/그래프 런타임 용어는 `LangChain`, `LangGraph` 기준으로 정리한다.
