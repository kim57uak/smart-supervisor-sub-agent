# 28. A2A Core Integration Plan

Updated: 2026-04-25

## Baseline

- 기존 `/api/*` 경로 및 외부 계약은 유지
- 내부 호출 체인은 Python `endpoint -> application -> domain -> infrastructure`로 정리
- canonical A2A entrypoint는 `POST /a2a/{scope}`다

## Core Rules

- 내부에서는 `a2a_method` enum 같은 공통 식별자로 정규화한다.
- `ai_chat_service -> agent_orchestrator` 실행 경로를 재사용한다.
- endpoint는 `AgentExecutionResult`를 받아 `raw-data`와 `compose-result` 채널을 조립한다.
- key는 반드시 `session_id + scope + task_id` 복합키를 사용한다.
- key는 `session_id + scope + method + request_id + normalized params hash`를 사용한다.
- 공개 path의 scope 값은 `sale-product`처럼 hyphenated slug를 사용하고, 내부 설정 키는 `sale_product` 같은 `snake_case`를 사용한다.

## Naming Rule

- 외부 계약 호환 계층만 PascalCase / legacy slash method를 유지한다.
- 내부 구현은 `session_id`, `request_id`, `trace_id`를 사용한다.
