# 13. Supervisor Agent Implementation Roadmap

Updated: 2026-04-25
Source baseline: `smart-supervisor`

## Implementation Baseline

현재 프로젝트는 아래 자산을 이미 가지고 있다고 가정한다.

- provider chat model 계층
- `settings/app.yml`
- supervisor 설정/프롬프트 리소스
  - `settings/supervisor.yml`
  - `settings/supervisor-hitl.yml`
  - `settings/supervisor-system-prompt.yml`
- supervisor static UI 샘플

반면 아래 계층은 아직 Python 소스로 본격 구현되지 않았다.

- supervisor endpoint / application service / graph / routing / hitl / handoff / swarm / a2a task / idempotency

## Phase 0: Documentation Sync

- supervisor 전용 문서에서 과거 Java/Spring 패키지 표기를 제거
- 현재 소스 기준 패키지 루트 `src/app`로 통일
- 실제 존재하는 설정 파일 기준으로 명세를 수정

## Phase 1: Configuration / Contract Foundation

- `pyproject.toml` 기준으로 supervisor 구현 의존성을 정리한다.
- supervisor 설정은 다음 자산을 유지/확장한다.
  - `settings/app.yml`
  - `settings/supervisor.yml`
  - `settings/supervisor-hitl.yml`
  - `settings/supervisor-system-prompt.yml`
- settings object, A2A method alias enum, error code, progress stage, graph node 상수 정의
- Redis key factory, TTL policy 정의

## Phase 2: Domain / Persistence Foundation

- `domain/supervisor/*` 생성
- `a2a/dto/*`, `a2a/mapper/*`, `a2a/task/*`, `a2a/lifecycle/*` 생성
- `conversation_store`, `graph_checkpoint_store`, `supervisor_review_store`, `supervisor_swarm_state_store` 생성
- `reviewed_execution_snapshot_store`, `execution_consistency_coordinator` 생성
- `supervisor_execution_persistence_service`, `supervisor_persistence_strategy_factory`, persistence strategies 생성
- `supervisor_request_idempotency_service` 구현

## Phase 3: Supervisor Entry / Application Layer

- `supervisor_a2a_endpoint` 단일 진입점 구현
- `supervisor_a2a_request_validator` 구현
- `supervisor_agent_service`, `supervisor_execution_service`, `supervisor_review_application_service`, `supervisor_task_facade` 추가
- unary, streaming, review decision, task 조회 API 연결
- pre-HITL A2UI short-circuit 처리 추가

## Phase 4: LangGraph Supervisor Core

- `supervisor_state_graph_factory` 구현
- 기본 graph: `select -> invoke -> merge -> compose`
- checkpoint 저장/복원 적용
- `supervisor_planning_service`, `supervisor_response_compose_service` 분리
- compose는 downstream 실행 완료 후에만 시작하고 재호출은 금지

## Phase 5: Downstream Routing / Handoff

- `A2AClientRegistry` + `A2AJsonRpcClient` 구현
- `a2a_invocation_service` 구현
- downstream allowlist, timeout, retry, circuit-breaker 반영
- handoff graph 분기 반영

## Phase 6: HITL / Swarm / A2UI

- `APPROVE`, `CANCEL` review flow 구현
- data mutation 강제 review 정책 연결
- `supervisor_swarm_coordinator` 구현
- shared state, review state, graph checkpoint 분리 저장
- 도메인별 A2UI 조립기 추가

## Phase 7: Production Hardening

- observability
- partial failure / fallback 정책 강화
- 계약 테스트 / 회귀 테스트 / stream 테스트 자동화
- docstring / 설계 규칙 / 코드리뷰 게이트 적용
