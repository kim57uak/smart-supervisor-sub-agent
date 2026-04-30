# 15. Implementation Roadmap

Updated: 2026-04-30

## Phase 1. Runtime Baseline [Completed]
- Python 3.11+ 기준 환경 정리
- FastAPI/Pydantic entrypoint 구성
- settings 분리(`agent.yml`, `mcp.yml`, `a2a.yml`)

## Phase 2. Agent Core [Completed]
- `planning_service`, `tool_execution_service`, `response_compose_service`, `agent_llm_runtime` 생성
- `agent_chat_request`, `planning_context`, `tool_plan`, `agent_execution_result` 정리

## Phase 3. LangGraph Integration [Completed]
- graph factory
- node definitions
- loop guard
- checkpoint integration

## Phase 4. Redis [Completed]
- conversation store
- checkpoint store
- task store
- idempotency policy

## Phase 5. A2A [Completed]
- canonical A2A endpoint 추가
- method alias compatibility
- response mapper / channel assembler

## Phase 6. Endpoint Refactoring [Completed]
- 기존 `/api/*` 계약 유지
- endpoint는 facade 호출만 담당
- prompt/history 조립은 application layer로 이동

## Phase 7. MCP Protocol Hardening [Completed]
- Streamable HTTP (Spring AI) 핸드셰이크 정합성 확보
- Mcp-Session-Id 기반 세션 관리 구현
- SSE(text/event-stream) 데이터 파싱 로직 안정화

## Current Status
- 핵심 인프라 및 MCP 연동 규약 정합성 확보 완료 (2026-04-30)
- E2E 연동 테스트 및 성능 최적화 진행 가능 상태
