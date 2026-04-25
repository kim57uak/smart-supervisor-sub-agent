# 22. Architecture Document Index

Updated: 2026-04-25

## Purpose

본 문서는 `a2a-host_agent-architecture` 문서 세트의 읽기 순서와 역할을 안내하는 인덱스다.
현재 기준선은 Java/Spring이 아니라 Python supervisor runtime이다.

## Recommended Reading Order

1. 시스템과 패키지 기준
- `01` system context
- `02` package policy
- `03` component architecture
- `04` domain class model

2. 실행 흐름과 상태
- `05` langgraph orchestration
- `06` supervisor A2A sequence
- `07` streaming response sequence
- `11` supervisor state machine

3. 결정과 정책
- `12` technology decision
- `14` package and dependency policy
- `17` supervisor package / class spec
- `21` settings recommended structure
- `31` FrozenExecutionPlan schema
- `32` FrozenExecutionPlan implementation draft

4. 현재형 정본 세트
- `25` delivery priority and status
- `26` entry contract and runtime flow
- `27` HITL / swarm / handoff architecture
- `28` A2UI architecture and operating model
- `29` security and reliability model
- `30` responsibility separation guide

## Document Roles

- `16`: 외부/내부 reference 링크 정본
- `22`: 문서 세트 인덱스와 읽기 순서 정본
- `25`~`32`: 현재 supervisor architecture 운영 기준 정본

## Maintenance Rule

- 링크 추가/삭제는 16번 문서에서 관리한다.
- 문서 역할 변경과 읽기 순서 변경은 22번 문서에서 관리한다.
- 새 architecture 문서를 추가할 때는 Python runtime 기준 용어와 책임 경계를 먼저 맞춘다.
