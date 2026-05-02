# 20. Sub-Agent Package / Class Specification

Updated: 2026-05-01 (Implementation sync)
Source baseline: `src/sub-agent/app`

## Core Modules / Components

### API Tier
- **`a2a/discovery.py`**: A2A(JSON-RPC) 요청 처리 및 에이전트 발견 엔드포인트.
- **`agent/chat.py`**: 사용자 직접 채팅 및 스트리밍 응답 엔드포인트.
- **`support/stream.py`**: Redis Stream 기반 SSE 구독 처리.

### Application Tier (Execution)
- **`AgentChatUseCase`**: API 진입점 로직. 멱등성 체크, 초기 상태 저장 및 워커 큐 적재 담당.
- **`AgentExecutor`**: 워커 내부의 실행 오케스트레이터. 엔진 호출 및 최종 상태 전이 관리.
- **`WorkerExecutionService`**: Redis Queue 기반의 백그라운드 워커 루프.
- **`AgentProgressPublisher`**: 실행 단계별 진행 이벤트를 Redis Stream으로 발행.

### Application Tier (Persistence & Read)
- **`AgentPersistence`**: 상태 변경 시나리오별 영속성 전략 Facade.
- **`AgentReadFacade`**: 태스크 상태 및 히스토리 조회 진입점.
- **`ExecutionConsistencyCoordinator`**: 원자적 상태 변경 및 무결성 제어 (준비 중).

### Adapters (Orchestration & Tools)
- **`LangGraphStateGraphFactory`**: LangGraph 기반 노드 및 엣지 정의.
- **`LangGraphAdapter`**: `OrchestrationEngine` 인터페이스의 LangGraph 구현체.
- **`McpToolRegistry`**: 로컬 설정 및 MCP 서버로부터 사용 가능한 도구 목록 관리.
- **`McpToolExecutor`**: MCP 서버와 통신하여 실제 도구 실행 수행.

### Adapters (LLM & Stores)
- **`LlmPlanningService`**: LLM을 이용한 도구 실행 계획 수립.
- **`LlmResponseComposeService`**: LLM을 이용한 최종 응답 합성 및 스트리밍.
- **`RedisStores`**: Redis 기반의 Task, Message, Session 저장소 구현체.

## Key Models (domain/models.py)

- **`AgentTask`**: 전체 태스크 실행 컨텍스트 및 상태 정보.
- **`ToolPlan`**: LLM이 결정한 도구 실행 상세 계획.
- **`AgentExecutionResult`**: 실행 완료 후의 최종 답변 및 메타데이터.
- **`PlanningContext`**: 플래닝 및 합성에 필요한 런타임 문맥.

## Dependency Policy (Actual)

- `api -> application/execution -> ports` (Inversion)
- `application/execution -> application/persistence/read facades`
- `adapters -> ports` (Implementation)
- `worker.py -> application/execution`
- 모든 레이어는 `domain` 및 `schemas`를 공유함.
