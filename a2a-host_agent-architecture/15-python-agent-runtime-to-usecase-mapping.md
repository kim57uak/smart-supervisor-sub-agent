# 15. Python Agent Runtime To Supervisor Usecase Mapping

Updated: 2026-04-28 (Implementation Refined)

## Supervisor Runtime Mapping

- **`supervisor_a2a_endpoint`**: FastAPI 기반 단일 진입점. JSON-RPC (Unary) 및 SSE (Subscription)를 모두 처리한다.
- **`supervisor_a2a_request_validator`**: Pydantic 모델을 활용한 요청 스키마 및 메서드 허용 목록 검증.
- **`supervisor_agent_service`**: API 요청의 최상위 오케스트레이터. 멱등성 체크, HITL 평가, 작업 큐잉을 담당한다.
- **`worker.py (EnterpriseWorker)`**: 분리된 백그라운드 실행기. Redis Queue에서 작업을 꺼내 실제 그래프 로직을 수행한다.
- **`supervisor_graph_execution_service`**: LangGraph 기반 상태 전이 제어 및 진행 상태 이벤트 발행.
- **`task_event_stream_service`**: Redis Stream을 이용한 이벤트 영속화 및 실시간 구독(SSE) 지원.
- **`hitl_gate_service`**: 플래너 결과를 기반으로 리뷰 필요 여부 판단 및 스냅샷 동결(Freeze).
- **`supervisor_read_facade`**: CQRS 패턴에 따른 상태 조회 및 강력한 무결성 검증(Audit) 수행.
- **`execution_consistency_coordinator`**: Redis `WATCH/MULTI/EXEC`을 이용한 원자적 상태 전이 및 멱등성 분산 락 관리.
- **`default_a2a_invocation_service`**: 서킷 브레이커, 지수 백오프 재시도 로직이 포함된 표준 A2A 통신 어댑터.
- **`llm_supervisor_response_compose_service`**: 실행 결과를 최종 사용자 언어로 합성하며, 필요 시 A2UI 렌더링 힌트 삽입.
- **`prompt_injection_guard`**: LLM 입력 텍스트의 유해 패턴 탐지 및 필터링.

## Python Stack Mapping

- **API Layer**: `FastAPI` + `Pydantic`
- **Execution Layer**: `Async Worker` + `LangGraph`
- **Message Broker**: `Redis (Queue/Stream)`
- **Persistence Layer**: `Redis (Hash/Store)`
- **LLM Integration**: `LangChain` (LLM Abstraction)

## Decoupled Worker Flow

1. **Submission**: API가 요청 수신 -> 멱등성 선점 -> 큐 적재 -> 즉시 응답.
2. **Execution**: 워커가 큐 폴링 -> 그래프 실행 -> 결과 합성 -> 이벤트 발행.
3. **Observation**: 클라이언트가 SSE 구독 -> Redis Stream 실시간 수신.

## Key Usecases

- **`hitl-gated-mutation`**: 데이터 변경 작업 전 승인 절차 강제.
- **`review-approve-resume`**: 동결된 스냅샷 기반의 안전한 실행 재개.
- **`direct-answer-shortcut`**: 하위 에이전트 미필요 시 즉시 응답 최적화.
- **`plan-drift-protection`**: 승인 시점 대비 에이전트 상태 변화 시 실행 차단.
- **`idempotent-retry`**: 동일 요청 중복 수신 시 실행 보장 및 결과 재조회.

## Security Constraints

- **Snapshot Ownership**: 타 사용자의 태스크 스냅샷 접근 및 조작 엄격히 금지.
- **Plan Hash Integrity**: 위변조된 실행 계획은 해시 불일치로 자동 거부.
- **Prompt Sanitization**: 인젝션 시도 시 경고 로그 및 필터링 적용.
