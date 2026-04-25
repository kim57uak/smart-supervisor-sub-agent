# 03. Current Architecture Gap Checklist And Improvement Proposal

Updated: 2026-04-25
Reference:
- `a2a-host_agent-architecture`
- `mcp-orchestrator-architecture`

## Status Summary

- 현재 문서는 application-level concurrency, idempotency, trace propagation 방향은 정의하고 있다.
- 하지만 platform-level 운영 스펙은 아직 부분적으로만 정의돼 있다.
- 따라서 현재 상태는 `소규모 multi-worker 준비 단계`로 보고, `enterprise-ready` 판정은 보류가 적절하다.
- 이 문서는 단순 gap 나열이 아니라, 각 gap에 대해 `무엇을 어떻게 바꿔야 하는지`를 제안하는 개선안 문서로 사용한다.

## Already Defined

- timeout / retry / circuit breaker
- idempotency key policy
- `trace_id + request_id + session_id` propagation
- external state store usage
- SSE replay/resume 방향
- per-scope concurrency / queue size 설정 항목

## Recommended Improvements

### A. ASGI Worker Runtime

- 기본 실행 모델을 `FastAPI + ASGI + multi-worker process`로 고정한다.
- 운영 기본값은 `stateless worker`다.
- worker count는 고정 상수가 아니라 `CPU core 수, downstream latency, SSE connection 수`를 기준으로 load test로 산정한다.
- graceful shutdown 시에는 신규 request 수락을 중단하고, in-flight SSE와 long-running request를 drain한 뒤 종료한다.

### B. Redis Consistency Model

- 외부 상태 저장소는 Redis로 고정하고, task/review/checkpoint/event cursor를 모두 Redis 기준 source of truth로 둔다.
- 동일 request 중복 실행은 `idempotency key + distributed lock + CAS` 조합으로 막는다.
- state transition은 `versioned record + compare-and-set` 규칙으로 구현한다.
- shared limiter, circuit breaker state, replay cursor는 worker local memory가 아니라 Redis에 둔다.
- 복합적인 상태 전이(State Transition)와 CAS 로직은 원자성(Atomicity) 보장을 위해 Redis Lua Script 사용을 표준으로 권고한다.


### C. Background Worker Split

- HTTP worker는 admission, validation, immediate orchestration, stream bridge 역할만 맡긴다.
- resume, reconciliation, orphan cleanup, replay rebuild, retry/backoff 같은 장시간 작업은 별도 background worker로 분리한다.
- background worker는 queue-based execution을 전제로 하고, HTTP worker와 동일한 Redis state model을 공유한다.

### D. SSE And Recovery

- SSE는 transport로만 취급하고, 실제 상태는 task event stream에 저장한다.
- client reconnect는 `task_id + cursor` 기준으로 재구독 가능해야 한다.
- rolling deploy 또는 restart 중에는 active stream drain timeout을 두고, drain 실패 시 reconnect-safe 종료 정책을 적용한다.
- Redis에 저장되는 이벤트 스트림은 메모리 압박 방지를 위해 30분의 보관 기간(Retention) 또는 적정 Maxlen 정책을 적용한다.


### E. Platform Operations

- observability는 `trace_id`, `request_id`, `session_id`를 전 구간에 전파하는 것을 기본으로 한다.
- 최소 지표는 in-flight requests, queue depth, active SSE connections, downstream latency/error rate, idempotency hit ratio, replay failure count다.
- Redis failover, worker crash, rolling restart, queue saturation을 운영 검증 항목으로 고정한다.

## Missing Or Weak

### A. Worker Runtime

- 표준 ASGI worker 구성은 `FastAPI + ASGI multi-worker`로 freeze 필요
- worker count 산정은 load test 기반으로 freeze 필요
- graceful shutdown/drain 세부 정책은 다음 순서로 정의 필요:
  - 신규 request 차단
  - in-flight request 추적
  - SSE drain timeout 적용
  - background task checkpoint 저장
  - 안전 종료

### B. Distributed State Consistency

- Redis lock/CAS 구체 명세를 `SET NX EX + versioned CAS`로 고정하고, 원자적 처리를 위한 Lua Script 표준 라이브러리 정의 필요

- multi-worker race condition test matrix를 `approve/cancel/complete/fail/retry` 조합으로 정의 필요
- shared limiter/circuit state 저장 규칙은 Redis key namespace 기준으로 문서화 필요
- Redis key space, TTL, failover, eviction policy를 운영 기준으로 고정 필요

### C. Background Execution

- resume/reconciliation/orphan cleanup를 HTTP worker에서 분리하는 것을 권장
- queue technology와 retry semantics는 `at-least-once + idempotent handler` 기준으로 고정 필요
- 재시도성 작업은 dead-letter 혹은 quarantine path를 가져야 함

### D. Streaming Operations

- SSE reconnect/replay retention은 `task_id + cursor` 기반으로 고정하고, 30분 TTL 또는 Maxlen 기준 확정 필요

- active stream drain during rollout 정책은 `graceful drain timeout`과 `force close`를 모두 정의해야 함
- ingress/proxy timeout은 SSE 및 long-running request에 대해 별도 기준이 필요함

### E. Platform Operations

- graceful restart/drain 표준은 운영 runbook으로 문서화 필요
- Redis HA/failover/eviction 정책은 source of truth 기준으로 반드시 명시 필요
- SLO/SLI/alerting 기준은 `queue depth`, `replay latency`, `error rate`, `drain timeout breach` 중심으로 정의 필요

## Decision Proposal

1. ASGI multi-worker 운영 모델을 `FastAPI + ASGI multi-worker + stateless worker`로 확정한다.
2. Redis lock/CAS/state transition을 운영 표준으로 확정한다.
3. background worker 분리를 전제로 queue-based 작업 경계를 확정한다.
4. SSE reconnect/drain 정책을 `task_id + cursor + drain timeout`으로 확정한다.
5. graceful restart, load shedding, failover, alerting runbook을 작성한다.

## Implementation Order

1. `Redis state model`과 `idempotency/CAS`부터 먼저 고정한다.
2. 다음으로 `ASGI worker runtime`과 `graceful shutdown`을 정의한다.
3. 이후 `background worker`와 `queue semantics`를 분리한다.
4. 마지막으로 `SSE reconnect/drain`과 `observability/alerting`을 연결한다.

## Exit Criteria

아래가 충족되면 enterprise-ready 재평가가 가능하다.

- multi-worker load test 통과
- duplicate execution 방지 검증 통과
- crash recovery 검증 통과
- rolling update 중 SSE reconnect 검증 통과
- Redis failover 검증 통과
- observability dashboard + alert 기준 수립 완료
- duplicate execution, orphan task, replay loss, drain timeout breach에 대한 대응 절차 수립 완료
