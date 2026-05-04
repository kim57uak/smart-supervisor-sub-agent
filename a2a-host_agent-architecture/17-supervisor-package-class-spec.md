# 17. Supervisor Package / Class Specification

Updated: 2026-05-04 (Implementation sync)
Source baseline: `src/supervisor-agent/app`

## Target Baseline

이 문서는 `smart-supervisor` 프로젝트의 supervisor 아키텍처를 Python 기준으로 정의한다.
실제 구현은 **CQRS(Command Query Responsibility Segregation)**와 **Hexagonal Architecture(Ports & Adapters)** 패턴을 결합하여 고도화되었다.

- 공통 기반
  - `Python 3.11+ + FastAPI + LangChain + LangGraph/Burr + A2A + Redis`
- 핵심 패턴
  - **Decoupled Worker**: API와 실행 워커 분리 (Redis Queue)
  - **Atomic Persistence**: Redis CAS 기반 상태 전이 일관성 보장
  - **Audit & Integrity**: 해시 기반 실행 계획 위변조 방지

## Current Source Structure

```text
src/supervisor-agent/app
├── adapters/         # Ports 구현체 (Stores, LLM, Invocation)
│   ├── integration/  # A2A 호출 어댑터 (DefaultA2AInvocation)
│   ├── llm/          # LLM 서비스 어댑터 (LlmPlanningService, VoiceAdapterFactory 등)
│   ├── orchestration/ # LangGraph/Burr 팩토리 및 어댑터
│   └── store/        # Redis 기반 저장소 어댑터 (RedisTaskStore 등)
├── api/              # FastAPI Routers (supervisor.py)
├── application/      # 비즈니스 로직 (CQRS)
│   ├── execution/    # 유즈케이스 및 실행 제어 (SupervisorAgentService, WorkerExecutionService 등)
│   ├── persistence/  # 상태 변경 및 일관성 관리 (ExecutionConsistencyCoordinator)
│   └── read/         # 상태 조회 및 검증 (SupervisorReadFacade)
├── common/           # 유틸리티 (Canonical JSON, Hashing)
├── domain/           # 엔티티, VO, Enums (models.py, enums.py)
├── infrastructure/   # 외부 연동 기초 (Redis Client, LLM Runtime)
├── ports/            # 추상 인터페이스 정의 (integration_ports.py, store_ports.py 등)
├── schemas/          # Pydantic 요청/응답 스키마 (supervisor.py, jsonrpc.py)
└── services/         # 도메인 서비스 (FactGovernanceService, PromptInjectionGuard, HandoffPolicyService)
```

## Core Modules / Components

### Execution Tier
- **`SupervisorAgentService`**: API 진입점 오케스트레이터. 멱등성 체크 및 작업 큐잉 담당.
- **`HitlGateService`**: 리뷰 필요성 평가 및 계획 동결(Freeze).
- **`TaskQueueService`**: Redis 기반의 신뢰할 수 있는 작업 큐 관리.
- **`WorkerExecutionService`**: 백그라운드 워커의 메인 루프.
- **`SupervisorGraphExecutionService`**: 오케스트레이션 엔진(LangGraph/Burr) 호출 및 결과 합성 제어.
- **`SupervisorProgressPublisher`**: 진행 상태 이벤트를 Redis Stream으로 발행.

### Persistence & Read Tier
- **`ExecutionConsistencyCoordinator`**: Redis `WATCH/MULTI/EXEC` 기반 원자적 상태 전이.
- **`SupervisorExecutionPersistenceService`**: 상태 변경 시나리오별 영속성 Facade.
- **`SupervisorReadFacade`**: 복합 쿼리 및 검증 로직 진입점.
- **`SnapshotVerificationQuery`** (`read_queries.py`): 승인 전 스냅샷 무결성 및 드리프트 검증.

### Services & Guard Tier
- **`PromptInjectionGuard`**: 시스템 프롬프트 보호 및 인젝션 방지.
- **`FactGovernanceService`**: Swarm 상태(Shared Facts)의 무결성 관리.
- **`HandoffPolicyService`**: 에이전트 간 핸드오프 규칙 검증.
- **`SupervisorA2ARequestValidator`**: 진입하는 A2A 요청의 유효성 검증.

### Orchestration & Integration
- **`WorkflowFactory`** (`langgraph_factory.py`): LangGraph 노드 및 엣지 정의.
- **`LangGraphAdapter`**: LangGraph 기반 실행 어댑터.
- **`BurrWorkflowFactory`**: Burr 기반 워크플로우 정의.
- **`BurrAdapter`**: Burr 기반 실행 어댑터.
- **`DefaultA2AInvocation`**: 서킷 브레이커가 포함된 표준 A2A 통신 어댑터.
- **`LlmPlanningService`**: 2단계 플래닝 (Routing + HITL Policy).
- **`LlmResponseComposeService`**: 지능형 응답 합성 및 A2UI 렌더링 지시.
- **`VoiceAdapter`** (Interface): 실시간 음성 처리를 위한 공통 인터페이스.
- **`OpenAiRealtimeAdapter`**: OpenAI Realtime API 기반 STT 구현체.
- **`VoiceAdapterFactory`**: 설정 기반 음성 어댑터 동적 생성기.

### Store Tier (redis_stores.py)
- **`RedisTaskStore`**: 작업 상태 저장.
- **`RedisExecutionSnapshotStore`**: 승인 대기용 스냅샷 저장.
- **`RedisConversationStore`**: 세션별 메시지 히스토리 저장.
- **`RedisSwarmStateStore`**: 공유 팩트(Swarm State) 저장.

## Key Models (domain/models.py)

- **`FrozenExecutionPlan`**: 동결된 실행 계획 (해시 포함).
- **`ReviewedExecutionSnapshot`**: 승인 대기 중인 실행 상태 스냅샷.
- **`FrozenRoutingStep`**: 순서(`order`)가 포함된 라우팅 단계.
- **`ExecutionConstraintSet`**: 동시성, 타임아웃 등 실행 제약 조건.
- **`SnapshotVerificationResult`**: 무결성 검증 결과 상세.
- **`SupervisorTaskEvent`**: Redis Stream에 저장되는 작업 이벤트.

## Dependency Policy (Actual)

- `api -> application/execution -> ports` (Inversion)
- `application/execution -> application/read/persistence facades`
- `adapters -> ports` (Implementation)
- `worker.py -> application/execution`
- 모든 레이어는 `domain` 및 `schemas`를 공유함.
