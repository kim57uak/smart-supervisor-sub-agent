# 25. Supervisor Delivery Priority And Status

Updated: 2026-04-25
Current baseline: `src/app`

## Document Role

본 문서는 25번 이후 문서의 운영 우선순위를 Python supervisor 기준으로 통합한 요약이다.

- 26번 문서: entry contract와 runtime flow 정본
- 27번 문서: HITL, swarm, handoff 실행 구조 정본
- 28번 문서: A2UI 구조와 운영 모델 정본
- 29번 문서: security, reliability, recovery 기준
- 30번 문서: 책임 분리와 모듈 경계 기준

## Current Assessment

현재 supervisor는 아래 구조를 기준선으로 본다.

- 단일 진입점: `supervisor_a2a_endpoint`
- use case 조립: `supervisor_agent_service`
- pre-HITL UI shortcut: `supervisor_pre_hitl_a2ui_service`
- HITL gate / review open / approve / cancel: `hitl_gate_service`
- 실행 위임: `supervisor_execution_service`
- graph + invoke + compose 조정: `supervisor_agent_orchestrator`
- persistence 단일 진입점: `supervisor_execution_persistence_service`
- 다중 저장소 순서화: `execution_consistency_coordinator`
- shared facts / event log / handoff state: `supervisor_swarm_coordinator`

현재 방향은 다음 원칙으로 고정한다.

- HITL은 application service 레벨 사전 게이트로 처리한다.
- graph는 실행 순서와 handoff 분기만 담당한다.
- Redis write는 facade에서 command로 표준화한다.
- task lifecycle을 source of truth로 두고 subordinate record를 정렬한다.
- pre-HITL A2UI와 post-invoke compose A2UI를 분리한다.
- supervisor는 하위 agent를 직접 대체하지 않고 orchestration 품질로 승부한다.

## Delivery Priority

### P0. Architecture Coherence

- 26~30 문서를 현재 Python 구조 기준으로 단일 정본 체계로 유지
- historical Java/Spring 설명 제거
- 모든 문서에서 `service-level HITL gate`, `task lifecycle source of truth`, `legacy + v1.0 compatibility`를 공통 기준으로 고정

### P1. Runtime Correctness

- `message/send`, `message/stream`, `tasks/review/decide` 흐름을 동일한 상태 규칙으로 유지
- review open 전에 immutable snapshot 저장 완료
- approve 시 `session_id + task_id + resume_token + state_version + request_hash + frozen_plan_hash` 검증 후 재개
- progress, task status, persistence 결과가 서로 다른 사실을 말하지 않게 정렬
- `STREAM` approve는 approve ack와 runtime stream을 분리하고 `tasks/events` 재구독 규약으로 고정

### P2. Agent Orchestration Quality

- planner 결과와 실제 invoke 시점 모두에서 allowlist/method 규칙 재검증
- handoff를 route quality 향상 수단으로 사용하되 loop와 무의미한 재이관을 엄격히 차단
- circuit breaker, cooldown, timeout, retry를 조합해 실패 agent를 빠르게 격리
- compose 단계의 downstream 재호출 금지

### P3. Operator Experience

- 사용자 progress와 운영 event log의 의미를 맞춘다.
- handoff, hitl, invoke failure, fallback 이유를 운영 로그에서 바로 추적 가능하게 한다.
- 로그는 식별자 중심으로 남기고 민감 데이터는 마스킹한다.

### P4. Productized UX

- 상품 상세 A2UI를 기준선으로 안정화
- A2UI 실패가 전체 응답 품질을 떨어뜨리지 않도록 text fallback 유지
- review waiting, review approve 후 resume, compose A2UI 결과를 동일한 UX 철학으로 맞춘다.
