# 30. Supervisor Responsibility Separation Guide

Updated: 2026-04-28 (Implementation Refined)

## Core Separation Principle: CQRS & Decoupling

Supervisor는 기능적 복잡도를 해결하기 위해 **CQRS(명령 조회 책임 분리)**와 **실행 환경 분리(Decoupled Worker)** 패턴을 핵심 책임 분리 기준으로 삼는다.

## 1. Execution Tier (Command & Logic)
- **`SupervisorAgentService`**: API 진입점의 유즈케이스 조립. 멱등성 선점 및 작업 큐잉에만 집중한다.
- **`WorkerExecutionService`**: 워커 프로세스의 수명 주기 관리 및 작업 실행 루프 제어.
- **`SupervisorGraphExecutionService`**: 실제 오케스트레이션(LangGraph)의 조정자. 그래프 실행, 진행 이벤트 발행, 최종 결과 합성을 총괄한다.

## 2. Persistence Tier (Write & Consistency)
- **`SupervisorExecutionPersistenceService`**: 상태 변경 시나리오별 전략(Strategy)을 관리하는 외벽(Facade).
- **`ExecutionConsistencyCoordinator`**: 모든 Redis Write의 정렬 및 원자적 상태 전이(CAS)를 책임진다.
- **`TaskEventStreamService`**: 진행 상태 이벤트의 영속화 및 실시간 발행에 특화된 저장소 관리.

## 3. Read Tier (Query & Audit)
- **`SupervisorReadFacade`**: 모든 조회의 단일 진입점. 비즈니스 로직이 Store 구현체에 직접 노출되는 것을 차단한다.
- **`SnapshotVerificationQuery`**: 승인 시점의 무결성 검증 로직을 고도로 응집하여 수행한다.
- **`TaskReadModelQuery`**: 클라이언트에게 보여줄 정규화된 태스크 뷰 조립 담당.

## Separation Guardrails
- **No Direct Store Access**: 어떤 서비스도 Redis Store 클래스에 직접 접근하지 않으며 반드시 Facade를 거친다.
- **No Planning in Worker**: 플래닝(Planning)은 API 계층에서 완료되어 동결되며, 워커는 오직 동결된 계획의 실행에만 집중한다.
- **Progress vs Result**: 진행 상태(Progress/Reasoning)는 오직 전송용(SSE)이며, 최종 결과(Final Answer)만이 태스크 결과 저장소에 영속화된다.
