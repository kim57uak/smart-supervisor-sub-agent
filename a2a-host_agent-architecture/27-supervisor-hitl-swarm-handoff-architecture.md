# 27. Supervisor HITL Swarm Handoff Architecture

Updated: 2026-04-25
Current baseline: `src/app`

## Purpose

본 문서는 supervisor의 핵심 실행 구조인 HITL, graph, swarm state, handoff를 Python runtime 기준으로 통합 설명하는 정본이다.

## Core Principle

최고 품질의 supervisor는 많은 기능을 직접 수행하는 agent가 아니라, 위험한 요청은 멈추고, 적절한 downstream에게 맡기고, 실패를 빨리 격리하고, 결과를 안정적으로 조합하는 orchestration layer여야 한다.

이를 위해 아래 원칙을 고정한다.

- HITL은 service 레벨에서 먼저 판단한다.
- `review_required` 판단은 planner output에 포함하고 graph 진입 전에 해석한다.
- graph는 실행 순서와 분기 제어만 담당한다.
- swarm state는 shared facts와 event log를 담당한다.
- handoff는 제한적 최적화이며 기본 흐름이 아니다.
- task lifecycle이 source of truth다.

## Canonical Execution Shape

### Pre-Execution

1. request 정규화
2. pre-HITL A2UI 평가
3. planner 호출로 routing + `review_required` + review metadata 생성
4. review 필요 시 planner 결과를 `plan + freeze`로 확정하고 snapshot 저장, waiting review task 생성
5. review 불필요 시 execution 시작

### In-Execution

graph는 아래 순서를 따른다.

1. `ROUTING_SELECTED`
2. `INVOKE`
3. `HANDOFF_EVALUATE`
4. `HANDOFF_APPLY`
5. `MERGE`
6. `SELECT` 반복
7. `COMPOSE`

## HITL Architecture

- 현재 review decision은 `APPROVE`, `CANCEL`로 고정한다.
- planner는 create/update/delete/reserve/order/payment/refund 계열을 risk score와 무관하게 review 강제 대상으로 해석해야 한다.
- review open 전에 immutable reviewed execution snapshot 저장 완료
- review approve는 raw request 재실행 금지
- approve 이후 planner 재호출 금지

## Swarm State Architecture

`swarm_state` 역할:

- shared facts 저장
- 운영 event log 저장

## Handoff Architecture

handoff는 다음 조건을 모두 만족할 때만 적용한다.

- feature flag enabled
- route allowlist 통과
- method allowlist 통과
- stream capability 충족
- max hops 미초과
- recent path 중복 제한 통과

handoff 실패 시 기존 계획으로 안전하게 복귀해야 하며, 차단 이유를 event log에 남긴다.

## Fallback Policy

fallback은 세 종류로 분리한다.

- routing fallback
- compose fallback
- ui fallback

fallback은 원인을 추적 가능한 degraded completion이어야 한다.
