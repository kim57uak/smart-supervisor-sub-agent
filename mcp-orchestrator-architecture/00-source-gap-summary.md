# 00. Source Gap Summary

Updated: 2026-04-25

이 폴더 문서는 이제 `Python 3.11+ + FastAPI + LangChain + LangGraph + A2A + Redis + MCP adapter runtime` 기준의 구현 설계 문서다.

## Reuse

- `ai_chat_service` 개념
- MCP registry/session/transport 개념
- scope별 기존 request/history normalization 규칙

## Replace

- 기존 비Python package shape
- legacy provider/runtime 용어
- 계층형 CRUD 스타일 설명

## Current Rule

- 문서의 정본 기준은 Python runtime이다.
- 내부 naming은 `snake_case`다.
- 외부 A2A compatibility alias만 PascalCase 또는 legacy field alias 원문을 유지할 수 있다.
