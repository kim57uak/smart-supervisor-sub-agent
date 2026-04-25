# 30. Supervisor Responsibility Separation Guide

Updated: 2026-04-25
Current baseline: `src/app`

## Purpose

본 문서는 supervisor의 책임 분리 기준을 확정한다. 목표는 Python 모듈이 많아지는 것이 아니라, 실행 책임이 어디서 시작하고 어디서 끝나는지 문서만 읽어도 헷갈리지 않게 만드는 것이다.

## Top-Level Rule

좋은 supervisor는 아래 여섯 가지가 섞이지 않아야 한다.

- entry/use case orchestration
- runtime control
- read scenario selection
- persistence scenario selection
- state consistency
- presentation assembly

추가 고정 원칙:

- 신규 downstream agent 온보딩의 기본 경로는 `yml + agent card`다.
- routing/invocation core는 신규 agent 추가 때문에 수정되지 않아야 한다.
- raw payload normalization과 A2UI mapping만 예외적으로 domain adapter를 허용한다.

## Ownership Map

### `supervisor_a2a_endpoint`

소유 책임:

- protocol entry
- request/response envelope handling
- SSE serialization

비소유 책임:

- routing
- planner prompt 규칙 상세
- task state transition
- compose decision

### `supervisor_agent_service`

소유 책임:

- use case branching
- pre-HITL A2UI shortcut 연결
- HITL gate 진입
- execution service 호출
- review read/decide flow 조립

비소유 책임:

- graph 노드 실행
- persistence 세부 구현
- progress string 직접 생성

### `hitl_gate_service`

소유 책임:

- planner의 `review_required` 결과 해석
- review 필요 시 planner 결과를 `plan + freeze`
- review open
- approve/cancel 처리
- snapshot 검증

비소유 책임:

- downstream invoke
- compose
- task list/get presentation

### `supervisor_execution_service`

소유 책임:

- sync, stream, approved resume 실행 모드 통합
- orchestrator 호출 전후의 실행 모드 차이 흡수
- cancellation and terminal handoff 조정

### `supervisor_agent_orchestrator`

소유 책임:

- execution pipeline 조정
- graph execution과 compose execution 연결
- 예외 경계 관리

### `supervisor_read_facade`

소유 책임:

- Redis read 단일 진입점 제공
- read query 수신
- query factory 선택 위임

### `supervisor_execution_persistence_service`

소유 책임:

- Redis write 단일 진입점 제공
- persistence command 수신
- strategy 선택 위임

### `execution_consistency_coordinator`

소유 책임:

- task/review/checkpoint/swarm/snapshot write ordering
- partial write recovery marker
- subordinate record reconciliation

### `supervisor_response_compose_service`

소유 책임:

- final answer assembly
- summary fallback
- A2UI payload 연결

### `supervisor_a2ui_service`

소유 책임:

- A2UI 후보 판정
- normalized view payload 생성
- 템플릿/메시지 조립

## Separation Rules

### Rule 1. HITL And Graph Separation

- HITL은 graph 바깥에서 처리한다.
- graph는 review를 기다리지 않는다.
- review 경로는 `plan` 결과를 freeze한 뒤 승인하고, 승인 후 graph는 `ROUTING_SELECTED`부터 재개한다.

### Rule 2. Execution And Persistence Separation

- execution이 끝난 사실과 저장하는 방법을 같은 클래스가 모두 소유하지 않는다.
- 서비스/오케스트레이터는 persistence facade만 호출하고 coordinator/store를 직접 호출하지 않는다.
- 서비스/오케스트레이터는 read facade만 호출하고 store를 직접 조회하지 않는다.

### Rule 3. Progress And Domain Result Separation

- progress는 사용자와 운영자에게 실행 상태를 알리는 transport 이벤트다.
- domain result는 최종 task payload와 A2A response의 source of truth다.
- progress 이벤트를 final payload persistence와 섞지 않는다.
