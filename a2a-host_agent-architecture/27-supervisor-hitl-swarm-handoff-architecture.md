# 27. Supervisor HITL, Swarm & Handoff Architecture

Updated: 2026-04-28 (Refined implementation sync)

## Architecture Overview

Supervisor의 실행 구조는 **"안전한 오케스트레이션"**에 집중한다. 실제 실행은 백그라운드 워커에서 이루어지며, API 계층은 정책 게이트웨이 역할을 수행한다.

## HITL Architecture (Refined)

- **Immutability**: 리뷰 대상 계획은 `FrozenExecutionPlan`으로 동결되며, 승인 시점까지 절대 변하지 않는다.
- **Audit-First**: 승인(Approve) 시 `SnapshotVerificationQuery`가 강제 실행되어 다음 항목을 검증한다.
  - `request_hash`: 원본 요청 메시지 위변조 여부.
  - `frozen_plan_hash`: 생성된 라우팅 계획의 위변조 여부.
  - `drift_policy`: 현재 시점에서 선택된 에이전트의 가용성(은퇴/차단 여부).
- **Atomic Transition**: Redis `WATCH`를 통한 상태 전이로 중복 승인 및 레이스 컨디션을 원천 차단한다.

## Swarm & Shared State

- **Context Restoration**: 워커는 실행 시작 시 `load_swarm_state`를 통해 세션의 공유 지식(Facts)을 복원한다.
- **Fact Propagation**: 실행 완료 시 그래프의 변경된 상태를 다시 스웜 저장소에 영속화하여 다음 실행에 반영한다.

## Handoff Policy

- **Guardrails**: `HandoffPolicyService`가 다음 정책을 강제한다.
  - `Max Hops`: 무한 핸드오프 루프 방지.
  - `Duplicate Block`: 최근 경로에 포함된 에이전트로의 중복 이관 차단.
  - `Method Allowlist`: 허용되지 않은 메서드로의 핸드오프 거부.
