# 14. Supervisor Agent Package And Dependency Policy

Updated: 2026-04-25

## Base Package

- `app`

## Dependency Rules

- `api -> application -> orchestration -> ports(plan/invoke/compose/graph)`
- `api -> application -> read facade -> query factory/query -> store`
- `api -> application -> persistence facade -> strategy -> coordinator -> store`
- `api -> application -> orchestration -> persistence facade`
- `api -> application -> orchestration -> read facade`
- `invoke -> a2a client/registry` only
- `plan/compose -> llm runtime` only
- 상위 계층은 구현체가 아니라 protocol/interface에 의존한다.
- 제거된 `mcp` 및 direct `reservation` 경로는 supervisor 기준선으로 삼지 않는다.

## Python Layering Rule

- Python 문서와 구현에서는 과거 계층형 CRUD 구조를 그대로 복제하는 것은 권장하지 않는다.
- 권장 기본 경계는 `api -> application -> domain -> infrastructure`다.
- `repository`라는 용어보다 `store`, `gateway`, `client`, `adapter` 같은 역할 중심 명칭을 우선한다.
- FastAPI endpoint는 transport adapter이고, business orchestration은 application service가 맡는다.
- Redis, HTTP, agent card 조회, settings 로딩은 infrastructure adapter로 분리한다.

## Folder Rules

- `app/api`와 `app/application`은 최상위 애플리케이션 폴더다.
- `app/application` 아래에 역할별 하위 패키지를 둔다.
  - `app/application/agent/*`
  - `app/application/prompt/*`
  - `app/application/a2ui/*`
- A2A DTO/mapper/task/lifecycle은 `app/a2a/*` 아래에 둔다.
- supervisor 전용 모델은 `app/domain/supervisor/*`로 묶는다.
- 인프라 구현은 `app/infrastructure/*` 아래에 모은다.
  - `redis`
  - `http`
  - `settings`
  - `logging`

## Design Rules

- Host는 하위 agent 내부 계약에 직접 의존하지 않는다.
- 하위 agent 호출은 반드시 A2A endpoint allowlist를 통과해야 한다.
- 실패 응답은 supervisor 표준 메시지로 정규화한다.
- supervisor 진입점은 `/a2a/supervisor`와 stream 경로만 사용한다.
- HITL 결정은 `approve/cancel` 인터페이스로 분리하고 application service에서만 조합한다.
- Swarm shared state는 `supervisor_swarm_state_store` 포트를 통해서만 접근한다.
- Redis read 시나리오는 `supervisor_read_facade` 단일 진입점으로만 들어간다.
- Redis write 시나리오는 `supervisor_execution_persistence_service` 단일 진입점으로만 들어간다.
- 어떤 서비스도 Redis store를 직접 read/write 하지 않는다.
- read facade는 `Facade + Query Factory + Query Handler` 조합으로 구현한다.
- persistence facade는 `Factory + Strategy + Template Method` 조합으로 구현한다.
- read query는 read intent별 정책을 캡슐화한다.
- `execution_consistency_coordinator`는 facade 내부 persistence 전략에서만 사용한다.
- handoff 검증/적용은 `handoff_policy_service`로 분리한다.
- 진행상태 출력은 `supervisor_progress_publisher` 공통 모듈을 사용한다.
- reasoning stream은 일반 text chunk와 분리된 이벤트 타입으로 노출한다.
- HITL 정책 파싱/런타임 실패는 `auto-approve` 또는 `notRequired()`로 폴백하지 않는다.
- review open 전에 immutable `reviewed_execution_snapshot` 저장을 완료해야 한다.
- review approve는 `resume_token + state_version + request_hash + frozen_plan_hash` 검증 후 snapshot 기준으로만 재개한다.
- review approve의 기본 HTTP 응답은 runtime stream이 아니라 approve ack다.
- task는 lifecycle source of truth이며 task/review/checkpoint/swarm/snapshot 모든 write는 persistence facade 경유로 실행한다.
- task/review/checkpoint/swarm/snapshot 모든 read도 read facade 경유로 실행한다.
- handoff method는 기존 허용 enum만 허용하고 stream 미지원 agent 대상 stream handoff는 금지한다.
- prompt 문자열은 endpoint/application service에 하드코딩하지 않는다.
- compose 단계에서 downstream 재호출은 금지한다.
- idempotency key는 `session_id + method + request_id + normalized params hash` 복합키를 사용한다.
- correlation key(`trace_id`, `request_id`, `session_id`)는 supervisor 전달값 우선, 누락 시에만 생성한다.
- `request_hash`, `frozen_plan_hash`는 schema/canonicalization version이 포함된 deterministic hash 규칙을 사용한다.
- sync/resume persistence는 final result channel만 저장하고 progress/reasoning/SSE envelope는 저장 금지다.

## Read Query Rules

- restore read는 `execution_restore_read_query`가 담당한다.
- task read model 조회는 `task_read_model_query`가 담당한다.
- review 조회/결정 전 검증 read는 `review_read_query`가 담당한다.
- approved resume snapshot 검증 read는 `snapshot_verification_query`가 담당한다.
- `supervisor_execution_state_loader`는 restore 요청 조립만 담당하고 store 접근은 read facade에 위임한다.
- `supervisor_task_facade`는 task 응답 view 조립만 담당하고 task 조회는 read facade에 위임한다.
- `hitl_gate_service`와 `supervisor_review_application_service`는 review/snapshot read를 직접 수행하지 않고 read facade를 통해 요청한다.

## Security And Guard Rules

- `prompt_injection_guard`는 planner/compose 입력 sanitize를 담당한다.
- method allowlist는 validator와 invoke 계층 양쪽에서 검증한다.
- routing allowlist는 planner 결과와 실제 invoke 시점 양쪽에서 검증한다.
- review approve 경로는 session ownership 외에도 snapshot ownership/version 검증을 강제한다.
- 공개 API와 핵심 Python 함수에는 docstring과 타입힌트를 작성한다.
- 상수 문자열, error code, graph node, progress stage는 enum 또는 constants 모듈로 관리한다.
