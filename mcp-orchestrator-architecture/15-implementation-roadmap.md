# 15. Implementation Roadmap

Updated: 2026-04-25

## Phase 1. Runtime Baseline

- Python 3.11+ 기준 환경 정리
- FastAPI/Pydantic entrypoint 구성
- settings 분리(`agent.yml`, `mcp.yml`, `a2a.yml`)

## Phase 2. Agent Core

- `planning_service`, `tool_execution_service`, `response_compose_service`, `agent_llm_runtime` 생성
- `agent_chat_request`, `planning_context`, `tool_plan`, `agent_execution_result` 정리

## Phase 3. LangGraph Integration

- graph factory
- node definitions
- loop guard
- checkpoint integration

## Phase 4. Redis

- conversation store
- checkpoint store
- task store
- idempotency policy

## Phase 5. A2A

- canonical A2A endpoint 추가
- method alias compatibility
- response mapper / channel assembler

## Phase 6. Endpoint Refactoring

- 기존 `/api/*` 계약 유지
- endpoint는 facade 호출만 담당
- prompt/history 조립은 application layer로 이동

## Current Priority

- request correlation: `trace_id + request_id + session_id`
- Redis key의 `session_id` 포함 정책은 유지하되, correlation 전달은 별도 구현한다.
- `trace_id`, `request_id`, `session_id`는 supervisor 전달값을 우선 사용한다.
