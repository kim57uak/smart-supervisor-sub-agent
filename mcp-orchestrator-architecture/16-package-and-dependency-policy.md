# 16. Package And Dependency Policy

Updated: 2026-04-25

## Base Package

- `src/app`

## Reused Areas

- 기존 MCP runtime 개념
- 기존 도메인 request/history normalization 규칙
- 기존 endpoint는 reference source로만 보고 target architecture의 기준 shape로 복제하지 않는다.

## New Packages

- `api.agent`
- `api.a2a`
- `api.support`
- `application.agent`
- `application.agent.plan`
- `application.agent.execute`
- `application.agent.compose`
- `application.agent.runtime`
- `application.agent.auth`
- `application.agent.security`
- `application.prompt`
- `a2a.context`
- `a2a.dto`
- `a2a.mapper`
- `a2a.task`
- `a2a.lifecycle`
- `domain.agent`
- `infrastructure.mcp`
- `infrastructure.redis`
- `infrastructure.settings`

## Dependency Direction

- `api.* -> application.*`
- `application.agent -> application.prompt + infrastructure.* + a2a.*`
- `application.agent.plan -> tool catalog + llm runtime`
- `application.agent.execute -> mcp registry + session manager + transport factory`
- `application.agent.compose -> llm runtime + prompt service`
- `a2a.lifecycle -> a2a.task`
- `infrastructure.redis -> redis client`

## Package Rules

- Python 문서와 구현에서는 과거 계층형 CRUD 구조를 그대로 복제하지 않는다.
- 문서와 구현은 `endpoint -> application -> domain -> infrastructure` 기준으로 설명한다.
- `repository`라는 용어보다 `store`, `client`, `gateway`, `adapter` 같은 역할 중심 명칭을 우선한다.
- endpoint는 orchestration 로직을 가지지 않는다.
- prompt는 `settings/system_prompt.yml` 기반으로 중앙화한다.
- 상수, key prefix, channel name, graph node name, error code는 하드코딩 금지다.
- runtime guardrail 값은 `settings/agent.yml`에서만 관리한다.
