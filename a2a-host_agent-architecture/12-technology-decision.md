# 12. Supervisor Agent Technology Decision

Updated: 2026-04-25

## 2026-04-25 현재 아키텍처 반영 결정

- 오케스트레이션 방식은 `LangGraph + Swarm State Store` 하이브리드로 확정한다.
- 구현 언어 기준선은 `Python 3.11+`로 둔다. 현재 권장 실행 버전은 `Python 3.11` 또는 `3.12`다.
- HTTP 진입 계층은 `FastAPI + Pydantic` 조합을 사용한다.
- downstream A2A 호출은 `httpx` 기반 비동기 JSON-RPC/SSE 경계로 구현한다.
- HITL은 현재 단계에서 `APPROVE/CANCEL`만 지원한다.
- review required 판단은 별도 HITL LLM 호출이 아니라 planner output에 통합한다.
- 데이터 생성/변경(create/update/delete) 요청은 점수 기반과 무관하게 HITL 강제 정책을 적용한다.
- A2A 메서드 호환은 `legacy + v1.0` 동시 지원을 기본 정책으로 한다.
- handoff는 기능 플래그(`handoff.enabled`) 기반으로 점진 적용한다.
- handoff method는 기존 허용 enum만 허용하고 stream 미지원 agent 대상 stream handoff는 금지한다.
- 생각과정/진행상태 표시는 `supervisor_progress_publisher` 공통 모듈로 통일한다.

## Final Choice

- `Python 3.11+ + FastAPI + LangChain + LangGraph + Redis + A2A(JSON-RPC/SSE)`

## Why

- `Python 3.11+`: LangChain/LangGraph 최신 안정 버전을 쓰기 쉬운 실행 기준이다.
- `FastAPI`: JSON-RPC 요청 검증, SSE 응답, 문서화, 비동기 처리에 적합하다.
- `LangChain`: planner/compose/model abstraction과 tool-safe I/O 경계를 단순화한다.
- `LangGraph`: 라우팅/호출/병합 흐름을 상태그래프로 강제한다.
- `Redis`: supervisor 세션 히스토리, 체크포인트, review snapshot, task read model을 외부화한다.
- `A2A`: 하위 에이전트 내부 구현과 분리된 안정 경계를 제공한다.

## Scope

- Supervisor agent는 하위 에이전트를 A2A로만 호출한다.
- 하위 에이전트 내부 로직, 툴, MCP는 설계 범위에서 제외한다.
- 기존 문서의 진입 계층, 애플리케이션 계층, 오케스트레이션 계층 책임은 Python 모듈 경계로 재해석한다.
- 현재 문서 세트의 구현 정본은 아래 대응 관계를 따른다.
  - HTTP entry -> FastAPI router/endpoint
  - application logic -> application service
  - typed data model -> Pydantic model / dataclass
  - async outbound client -> `httpx.AsyncClient`
  - runtime settings -> `settings/*.yml` 또는 `.env + YAML`

Python 명명 규칙 메모:

- 함수, 변수, 모듈, 필드명은 `snake_case`
- 클래스명만 `PascalCase`
- 외부 A2A 프로토콜 alias는 compatibility layer에서만 유지

## Python Implementation Baseline

- request/response schema: `pydantic`
- runtime configuration: `pydantic-settings` 또는 `yaml + loader`
- async HTTP client: `httpx`
- SSE delivery: FastAPI `StreamingResponse`
- Redis adapter: `redis.asyncio`
- logging/audit: structured JSON logging
- test baseline: `pytest`, `pytest-asyncio`

## 2026-04-25 정합성 메모

- 본 문서는 `25`~`30` 문서 기준으로 현재 supervisor architecture 원칙을 상위 기준으로 따른다.
- 이번 차례 구현 스코프는 `APPROVE`, `CANCEL`만 포함하며 `REVISE`는 다음 단계로 이관한다.
- 상품/예약/주문 등 데이터 생성·변경(create/update/delete) 요청은 리스크 점수와 무관하게 HITL 강제 정책을 적용한다.
- A2A 계약은 `legacy + v1.0`을 모두 충족하는 호환 모드로 유지한다.
- 사용자 추가정보 수집은 향후 계획으로 분리하며, 입력 UX는 자연어/콤마 텍스트 수용 후 내부 구조화 원칙을 따른다.

## 2026-04-25 handoff 반영 메모

- Supervisor 오케스트레이션에 handoff 분기(`invoke -> handoff evaluate/apply`)를 도입한다.
- 리팩토링 기준은 SOLID, 추상화, 가독성, 유지보수성 우선 원칙을 따른다.
- 신규/수정 public API와 핵심 Python 모듈에는 docstring과 타입힌트를 필수 적용한다.
