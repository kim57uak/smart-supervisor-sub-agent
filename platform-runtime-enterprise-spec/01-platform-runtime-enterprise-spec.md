# 01. Platform Runtime Enterprise Specification

Updated: 2026-04-25
Scope: `a2a-host_agent-architecture` + `mcp-orchestrator-architecture`

## Goal

본 문서는 Python 기반 agent runtime을 엔터프라이즈 멀티워커 환경에서 운영하기 위한 플랫폼 레벨 요구사항을 정의한다.
핵심 기준은 "멀티스레드" 자체보다 `멀티워커 + 멀티노드 + 외부 상태 저장소 기반 일관성`이다.

## Runtime Model

- HTTP 진입점은 `FastAPI` 기반 ASGI 앱으로 구성한다.
- 운영 기본 모델은 `멀티프로세스 worker`다.
- Python GIL 특성상 CPU 확장보다는 `async I/O + multi-worker` 조합을 기본으로 한다.
- request 처리 상태를 프로세스 메모리에 단독 보관하지 않는다.
- in-memory 자료구조는 cache 또는 transient optimization으로만 사용한다.

## Source Of Truth

- task state, review state, checkpoint, swarm state, idempotency record, event cursor는 외부 저장소를 source of truth로 사용한다.
- 외부 저장소는 `Redis`를 사용한다.
- worker restart, rolling deploy, instance reschedule 이후에도 Redis 기준으로 실행 재개가 가능해야 한다.

## Enterprise Concurrency Rule

- 동일 request의 중복 실행 방지는 `idempotency key + distributed lock/CAS`로 보장한다.
- task 상태 전이는 optimistic lock 또는 compare-and-set 기반으로 수행한다.
- `cancel`, `complete`, `fail`, `approve-resume` 경합에서는 last-write-wins를 금지한다.
- scope별 concurrency limit, downstream agent별 circuit breaker, provider별 rate limit은 프로세스 로컬이 아니라 공유 가능한 상태 모델을 가져야 한다.

## Streaming Rule

- SSE는 worker local memory에만 의존하지 않는다.
- replay 가능한 task event stream을 기준으로 resume/reconnect를 지원한다.
- approve ack와 resumed runtime stream은 분리한다.
- long-lived SSE 연결은 graceful shutdown 시 drain 또는 reconnect-safe 방식으로 종료해야 한다.

## Background Execution Rule (Implemented)

- 승인 후 resume, reconciliation, orphan cleanup, replay rebuild 같은 작업은 HTTP worker에 과도하게 묶지 않는다.
- 장시간 또는 재시도성 작업은 별도 background worker 계층으로 분리하여 운영한다.
- **구현 현황**: `TaskQueueService`를 통해 Redis List 기반의 메시지 큐를 도입하였으며, `worker.py` 독립 프로세스가 실제 실행을 전담함.
- HTTP worker는 request admission, validation, immediate orchestration 시작(enqueue), stream bridge 역할에 집중한다.

## Observability Rule

- 모든 request는 `trace_id`, `request_id`, `session_id`를 전 구간에 전달한다.
- OpenTelemetry trace/span, structured log, metric label 체계를 공통으로 사용한다.
- **참고**: 필수 지표 수집은 외부 관측 시스템에서 대행하므로 런타임 내 지표 노출 인터페이스만 유지한다.

## Platform Acceptance Gate

아래 조건을 만족하여 엔터프라이즈 운영 가능 판정을 획득함.

1. 멀티워커 간 상태 일관성이 외부 저장소(Redis)로 보장됨.
2. 동일 요청 중복 실행을 분산 환경(CAS)에서 차단할 수 있음.
3. rolling deploy 중에도 Redis 큐와 Durable Stream을 통해 안전한 재개가 가능함.
4. worker crash 후에도 Redis에 남은 메시지와 Snapshot 기준으로 복구 가능함.
5. 백그라운드 워커 분리를 통해 API 가용성과 실행 안정성을 물리적으로 격리함.
