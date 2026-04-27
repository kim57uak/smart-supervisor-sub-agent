# 31. FrozenExecutionPlan Schema

Updated: 2026-04-25

## Purpose

본 문서는 review-required 요청에서 승인 대상 실행계획을 어떻게 고정(freeze)하는지 정의한다.

핵심 원칙:

- `FrozenExecutionPlan`은 별도 지능 단계가 아니라 `plan` 결과의 고정 스냅샷이다.
- review 승인 후 실행은 raw request 재해석이 아니라 이 frozen plan 재개다.
- approved resume는 `ROUTING_SELECTED`부터 시작하며 planner를 다시 호출하지 않는다.

## When It Is Created

- 일반 실행:
- planner가 `review_required=false`를 반환하면 `FrozenExecutionPlan`을 만들지 않고 `routing_selected -> execute -> compose`로 진행한다.
- planner가 `review_required`를 누락하거나 schema/parse/runtime 오류가 나면 fail-closed로 review 경로 또는 명시적 오류로 처리한다.
- review-required 실행:
  1. 입력 sanitize / normalize
  2. `plan`
  3. `FrozenExecutionPlan` 생성
  4. `ReviewedExecutionSnapshot`에 포함해 저장
  5. `WAITING_REVIEW`

즉 review 경로의 의미는 `plan + freeze -> approve -> execute frozen plan`이다.

## Required Fields

```python
from datetime import datetime
from pydantic import BaseModel


class FrozenRoutingStep(BaseModel):
    order: int
    agent_key: str
    method: str
    source_type: str  # PLANNER | HANDOFF_SEEDED
    reason: str
    arguments: dict
    handoff_depth: int
    parent_agent_key: str | None = None


class FrozenExecutionPlan(BaseModel):
    task_id: str
    session_id: str
    request_id: str
    trace_id: str
    state_version: int
    schema_version: int
    canonicalization_version: int
    execution_mode: str  # SEND | STREAM
    resume_state: str  # ROUTING_SELECTED
    request_hash: str
    frozen_plan_hash: str
    created_at: datetime
    expires_at: datetime
    routing_queue: list[FrozenRoutingStep]
    planner_metadata: dict
    execution_constraints: dict
```
```

## Field Rules

- `task_id`, `session_id`, `request_id`, `trace_id`
  - 승인 전후 실행 상관관계를 고정하는 식별자다.
- `state_version`
  - subordinate record 정렬 기준이다.
- `schema_version`
  - frozen plan payload schema 버전이다.
- `canonicalization_version`
  - hash 계산 규칙 버전이다.
- `execution_mode`
  - `SEND`, `STREAM` 중 하나다.
- `resume_state`
  - 현재 설계에서는 항상 `ROUTING_SELECTED`다.
- `request_hash`
  - sanitize + normalize 이후 요청 기준 hash다.
- `frozen_plan_hash`
  - `schema_version + canonicalization_version + routing_queue + execution_constraints + planner_metadata`의 canonical hash다.
- `routing_queue`
  - 승인 대상 실행 순서의 정본이다.
- `planner_metadata`
  - explain/debug/audit 목적 메타데이터다.
  - 실행 의미를 바꾸는 정보는 넣지 않는다.
- `execution_constraints`
  - max concurrency, stream mode, timeout class 등 실행 제약이다.
  - 환경 의존 세부값 전체를 복사하지는 않는다.

## What Must Not Be Frozen

- downstream endpoint raw URL
- circuit breaker live state
- cooldown live state
- current allowlist verdict
- current downstream capability verdict
- compose output

이 값들은 승인 대상 실행계획이 아니라 “실행 시점의 환경 상태”이므로 snapshot에 고정하지 않는다.

## Canonical Hash Rule

- `frozen_plan_hash`와 `request_hash`는 모두 canonical serialization 규칙 위에서 계산한다.
- hash 대상 payload는 key ordering이 고정된 canonical JSON 또는 그에 준하는 deterministic binary encoding을 사용한다.
- `dict[str, Any]`를 그대로 serializer 기본 동작에 맡겨 hash하면 안 된다.
- null field 포함 여부, 숫자 표현, boolean 표현, time format, UTF-8 encoding 규칙을 canonicalization version으로 고정한다.
- `planner_metadata`는 hash 대상에 포함되더라도 자유형 debug blob이 아니라 허용 필드만 가진 안정 메타데이터여야 한다.
- `arguments`도 schema-free raw object가 아니라 canonicalizable structured value여야 한다.
- 운영 중 규칙이 바뀌면 `canonicalization_version`을 올리고 이전 버전 검증 경로를 유지해야 한다.

권장 기준:

- object key는 사전순 정렬
- 배열은 원래 순서 유지
- 시간은 UTC ISO-8601 문자열로 고정
- decimal/long/string 혼용을 금지하고 sanitize 단계에서 타입을 확정
- hash 알고리즘은 `SHA-256`

request hash payload 기준:

- `request_hash = SHA-256(canonicalize(sanitized_input_envelope))`
- `sanitized_input_envelope`는 최소 `session_id`, `request_id`, `execution_mode`, `normalized_user_input`, `normalized_business_params`를 포함한다.
- tracing/debug/audit 보조 필드는 `request_hash` 대상에서 제외한다.

frozen plan hash payload 기준:

- `frozen_plan_hash = SHA-256(canonicalize(frozen_plan_envelope))`
- `frozen_plan_envelope`는 최소 `schema_version`, `canonicalization_version`, `routing_queue`, `execution_constraints`, `planner_metadata`를 포함한다.
- `planner_metadata`는 허용 필드 집합만 포함한다.
  - `planner_version`
  - `policy_version`
  - `plan_reason_codes`
  - `selected_domain`
- 자유형 prompt trace, token usage, debug blob은 `frozen_plan_hash` 대상에서 제외한다.

숫자/문자열 정규화 규칙:

- 숫자형 문자열 `"1"`과 숫자 `1`은 동일 취급하지 않는다.
- 금액, 수량, 인원수 등 business numeric field는 sanitize 단계에서 최종 타입을 확정한다.
- trim, Unicode normalization, locale-specific formatting 제거는 sanitize 단계에서 끝내고 hash 단계에서는 재가공하지 않는다.

시간 정규화 규칙:

- time field는 UTC ISO-8601 instant 문자열로 통일한다.
- local datetime과 zoned datetime 혼용을 금지한다.
- 같은 의미의 시각이 다른 timezone string으로 들어오면 sanitize 단계에서 하나의 UTC instant로 수렴시킨다.

## Verification On Approve

approve 시 아래 조건이 모두 참이어야 resume 가능하다.

1. `session_id` 일치
2. `task_id` 일치
3. `resume_token` 일치
4. `state_version` 일치
5. `request_hash` 일치
6. `frozen_plan_hash` 일치
7. snapshot TTL 미만

검증 실패 시:

- 기본 동작은 `resume reject`
- 필요 시 review를 다시 열 수 있다
- planner 재호출로 대체하지 않는다

검증 source of truth 규칙:

- client는 approve 의사결정만 전달하고, `resume_token`, `state_version`, `request_hash`, `frozen_plan_hash`의 최종 검증 기준은 server가 보관한 snapshot이다.
- client가 추가 검증 필드를 보내더라도 server snapshot 검증을 대체할 수 없다.
- approve 계약이 최소 필드만 받더라도 server는 snapshot과 현재 task truth를 함께 검증해야 한다.
- 검증 실패는 내부 예외 메시지가 아니라 표준 reason code로 수렴해야 한다.

## Execution Semantics

- direct execution:
  - `ROUTING_SELECTED -> invoke -> handoff_evaluate -> handoff_apply|skip -> merge -> select|compose`
- approved resume:
  - `ROUTING_SELECTED -> invoke -> handoff_evaluate -> handoff_apply|skip -> merge -> select|compose`

direct execution과 approved resume 모두 planner가 만든 routing queue를 사용하며 planner는 graph 밖에서만 호출된다.

## Drift Policy

기준은 `snapshot 우선, 현재 안전 가드 재검증`이다.

- 유지하는 것:
  - frozen `routing_queue`
  - frozen `method`
  - frozen `arguments`
  - frozen execution order
- 현재 시점에 다시 검증하는 것:
  - route allowlist
  - method allowlist
  - downstream stream capability
  - hard security block
  - terminally invalid endpoint / agent disabled 상태

drift 처리 규칙:

1. 안전 가드 위반
   - 실행 거부
   - review 재오픈 또는 명시적 오류
2. 성능/운영 상태 변화
   - circuit open, cooldown 등은 실행 시점 정책으로 처리
   - plan 자체는 바꾸지 않는다
3. planner 결과 변경 가능성
   - 무시한다
   - 이미 승인된 frozen plan이 우선한다

## Persistence Boundary

- `ReviewedExecutionSnapshot`은 아래를 포함한다.
  - sanitized input
  - request hash
  - resume token
  - state version
  - `FrozenExecutionPlan`
- `FrozenExecutionPlan`은
  - snapshot payload 내부 embedded object
  - 또는 별도 key 참조
  둘 중 하나로 저장할 수 있다.

권장 key:

- snapshot: `PACKAGE:supervisor:snapshot:{session_id}:{task_id}:{state_version}`
- snapshot-plan: `PACKAGE:supervisor:snapshot-plan:{session_id}:{task_id}:{state_version}`

## Write Order

- review open:
  - `snapshot(plan 포함) -> review -> task(WAITING_REVIEW)`
- approve resume:
  - `snapshot verify -> task(RUNNING CAS) -> durable event stream 기준 initial_cursor 확정 -> approve ack -> runtime event append/publish -> checkpoint/swarm init`
- completion:
  - `final result persist -> checkpoint finalize -> swarm finalize -> task terminal`

## STREAM Resume Contract

- `execution_mode=STREAM` snapshot approve는 runtime stream 자체를 approve 응답에 싣지 않는다.
- approve 성공 시 ack에 `stream_resume_required=true`, `stream_method`, `stream_endpoint`, `initial_cursor`를 포함한다.
- client는 ack를 받은 뒤 `tasks/events`로 재구독해야 한다.
- `initial_cursor`는 "client가 이 cursor 다음부터 재구독하면 승인 이후 발생한 replay 대상 event를 놓치지 않는다"는 의미의 durable cursor여야 한다.
- `initial_cursor`는 in-memory live emitter 기준값이 아니라 task-scoped durable event log 기준값이어야 한다.
- approve 처리에서 `task RUNNING CAS`와 replay 가능한 첫 event 기준점 확보는 논리적으로 하나의 resume transaction처럼 동작해야 한다.
- client 재구독 전에 발생한 `progress`, `chunk`, `a2ui`, `done`, `error` 중 replay 대상 event는 cursor 기반으로 다시 전달 가능해야 한다.
- `done` 또는 `error` terminal event는 cursor replay 대상이어야 한다.

## Minimal Example

```json
{
  "task_id": "task-123",
  "session_id": "s-1",
  "request_id": "rpc-9",
  "trace_id": "tr-77",
  "state_version": 4,
  "schema_version": 1,
  "canonicalization_version": 1,
  "execution_mode": "SEND",
  "resume_state": "ROUTING_SELECTED",
  "request_hash": "req_sha256_x",
  "frozen_plan_hash": "plan_sha256_y",
  "routing_queue": [
    {
      "order": 0,
      "agent_key": "product",
      "method": "message/send",
      "source_type": "PLANNER",
      "reason": "product lookup",
      "arguments": {
        "query": "파리 패키지"
      },
      "handoff_depth": 0,
      "parent_agent_key": null
    }
  ]
}
```

## Non-Goals

- 승인 후 planner 재실행 허용
- frozen plan을 runtime 환경 상태까지 완전 고정하는 것
- compose 결과를 review 승인 대상으로 취급하는 것

## Related Documents

- [11-supervisor-state-machine.puml](/Users/kim/hanatour/workspace/package/smart-supervisor/document/a2a-host_agent-architecture/11-supervisor-state-machine.puml)
- [17-supervisor-package-class-spec.md](/Users/kim/hanatour/workspace/package/smart-supervisor/document/a2a-host_agent-architecture/17-supervisor-package-class-spec.md)
- [20-supervisor-routing-package-class-spec.md](/Users/kim/hanatour/workspace/package/smart-supervisor/document/a2a-host_agent-architecture/20-supervisor-routing-package-class-spec.md)
- [21-a2a-supervisor-yml-recommended-structure.md](/Users/kim/hanatour/workspace/package/smart-supervisor/document/a2a-host_agent-architecture/21-a2a-supervisor-yml-recommended-structure.md)
- [32-frozen-execution-plan-implementation-draft.md](/Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/a2a-host_agent-architecture/32-frozen-execution-plan-implementation-draft.md)
