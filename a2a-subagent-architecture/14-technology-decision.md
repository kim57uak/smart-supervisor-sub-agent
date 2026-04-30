# 14. Technology Decision

Updated: 2026-04-28 (Aligned with Supervisor Enterprise Architecture)

## Final Stack

- `Python 3.11+`
- `FastAPI + Pydantic`
- `LangChain + LangGraph`
- `A2A Protocol v1.0.0`
- `Redis` (Queue, Stream, Store)
- `MCP adapter runtime`

## Why This Stack

- `Python 3.11+`: LangChain/LangGraph 호환성 및 비동기 I/O 최적화.
- `FastAPI + Pydantic`: 고성능 API 및 typed contract 보장.
- `LangGraph`: 복잡한 agentic flow(Planning -> Execution -> Compose)를 명시적 상태 그래프로 관리.
- **Decoupled Worker Pattern**:
    - 엔터프라이즈급 안정성을 위해 API와 실행 워커를 분리한다.
    - LLM 및 MCP 도구 호출과 같은 무거운 작업은 Background Worker에서 처리하여 API 응답성을 확보하고 독립적 확장을 가능하게 한다.
- **Hexagonal Architecture**:
    - 기술적 세부사항(Redis, MCP SDK)과 비즈니스 로직을 분리하여 유지보수성을 극대화한다.
- **Redis**: 
    - `Task Queue`: API와 Worker 간의 통신.
    - `Event Stream`: 실시간 진행 상태(Progress) 전송.
    - `Persistence`: 대화 이력 및 그래프 체크포인트 저장.

## Design Principles

- **Surgical Changes & Minimal Overlap**: Supervisor 아키텍처와 일관성을 유지하되, Sub-agent 고유의 MCP 책임에 집중한다.
- **CQRS**: 명령(상태 변경)과 조회(상태 확인) 경로를 분리한다.
- **Traceability**: `trace_id`, `request_id`, `session_id`를 전 구간에서 전파하여 분산 추적 가능성을 확보한다.
- **Idempotency**: Redis를 이용한 멱등성 설계를 통해 중복 실행을 방지한다.
- **MCP Transport Protocol**:
    - **Streamable HTTP (Spring AI 1.1.4)**: Java 기반 MCP 서버와의 호환성을 위해 Spring AI의 `Streamable HTTP` 전송 규약을 채택한다.
    - **Session-Based Handshake**: Stateless한 HTTP 환경에서 세션을 유지하기 위해 첫 번째 `initialize` 응답에서 `Mcp-Session-Id`를 획득하고, 이후 모든 `tools/list` 및 `tools/call` 요청 헤더에 이를 주입하는 2-단계 핸드셰이크를 강제한다.
    - **SSE (Server-Sent Events) Awareness**: 서버가 스트리밍 모드에서 반환하는 `text/event-stream` 형식의 응답을 파싱할 수 있도록 `data:` 접두사 처리 로직을 어댑터 계층에 구현한다.
