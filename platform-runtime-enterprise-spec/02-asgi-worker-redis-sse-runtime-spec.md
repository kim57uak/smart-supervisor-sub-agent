# 02. ASGI Worker, Redis, SSE, Background Worker Specification

Updated: 2026-04-25

## 1. ASGI Worker Model

- 권장 런타임:
  - `gunicorn + uvicorn workers`
  - 또는 플랫폼 표준이 있으면 동등한 ASGI multi-worker runtime
- 기본 원칙:
  - worker는 stateless
  - sticky session 비의존
  - graceful shutdown 지원
- worker 수 산정 기준:
  - CPU bound가 아니라 I/O bound 기준으로 잡는다.
  - provider latency, downstream A2A latency, SSE connection 수를 반영해 load test로 최종 조정한다.

## 2. Redis Locking And State Transition

- idempotency lock:
  - `SET key value NX EX ttl`
  - completed response cache와 in-flight lock을 분리한다.
- task state transition:
  - state version 필드를 두고 CAS 또는 optimistic lock으로 갱신한다.
- review approve/resume:
  - `snapshot verify -> task running CAS -> initial cursor reserve -> runtime append` 순서를 논리적 단일 트랜잭션처럼 보장해야 한다.
- 본 문서 기준 외부 상태 저장소는 Redis로 고정한다.
- audit, ledger, replay cursor, idempotency, checkpoint도 Redis 운영 기준으로 설계한다.

## 3. SSE And Event Stream

- HTTP SSE는 transport layer일 뿐 source of truth가 아니다.
- replay 가능한 task event stream을 별도로 유지한다.
- 최소 event type:
  - `progress`
  - `chunk`
  - `a2ui`
  - `done`
  - `error`
- SSE reconnect:
  - `task_id + cursor` 기준으로 재구독 가능해야 한다.
- deploy/shutdown:
  - active stream drain timeout을 둔다.
  - drain 실패 시 reconnect-safe 종료 이벤트 또는 client retry 계약을 둔다.

## 4. Background Worker Model

- 다음 작업은 background worker로 분리 가능한 구조를 권장한다.
  - review approve resume
  - reconciliation
  - orphan cleanup
  - retry/backoff execution
  - materialized read model rebuild
- 후보 기술:
  - Celery/RQ/Dramatiq/Arq 같은 queue worker
  - 또는 사내 표준 batch/worker 플랫폼
- HTTP worker는 queue enqueue와 immediate ack에 집중할 수 있어야 한다.

## 5. Enterprise Hardening Checklist

- distributed lock collision test
- concurrent approve/cancel/complete/fail race test
- Redis failover test
- worker crash recovery test
- rolling deploy 또는 graceful restart SSE reconnect test
- downstream timeout/circuit breaker test
- queue saturation and load shedding test
