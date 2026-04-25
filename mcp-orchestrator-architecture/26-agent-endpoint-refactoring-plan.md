# 26. Agent Endpoint Refactoring Plan

Updated: 2026-04-25

## Current Direction

기존 도메인 endpoint는 reference source로만 보고, 현재 단계에서는 직접 복제하지 않는다.
레거시 `/api/*` 경로는 요청 계약과 응답 계약을 유지하되, 새 구조 설명의 기준은 Python endpoint 계층이다.

## New Support Modules

- `api/support/base_prompt_endpoint_support.py`
- `api/support/base_agent_endpoint_support.py`
- `api/support/base_a2a_endpoint_support.py`
- `api/support/base_a2a_streaming_endpoint_support.py`

## Refactoring Rules

- endpoint는 request parsing + validation + endpoint mapping만 담당한다.
- prompt builder는 endpoint 밖 `settings/system_prompt.yml` 기반 prompt service로 이동한다.
- `ai_chat_service`에 직접 prompt를 넘기던 구조를 `agent_chat_request` 전달 구조로 전환한다.
- 권한 체크는 endpoint에 하드코딩하지 않고 공통 authorization service로 위임한다.
- A2A endpoint는 legacy/current JSON-RPC method family를 모두 허용하고 내부 enum으로 정규화한다.
- 기존 `/api/*` 레거시 경로는 계약 보존이 우선이며, 내부 구현 설명은 Python 기준으로 재해석한다.
- 신규 A2A 구현이 레거시 로직을 재사용해야 할 때는 adapter, facade, strategy, anti-corruption layer 같은 패턴으로 연결한다.
- LLM model은 요청마다 직접 입력받기보다 서버 설정(`agent.default_model`, `agent.scopes.*.default_model`)으로 결정한다.

## Endpoint Target Shape

- 기존 `/api/*` 경로는 유지
- `/a2a/weather`
- `/a2a/supply-cost`
- `/a2a/reservation`
- `/a2a/sale-product`

## Authorization Baseline

- HTTP endpoint와 A2A endpoint는 동일한 authorization service를 사용한다.
- `session_id`가 없으면 요청을 거절한다.
- `session_id`는 로그인 세션 lookup key다.
- 권한은 최소 `scope` 단위로 검사한다.
- endpoint는 `session_id + scope_name`만 전달하고 판단은 application service가 담당한다.

## Python Pseudocode

```python
class AgentAuthorizationService(Protocol):
    async def assert_authorized(self, session_id: str, scope_name: str) -> None: ...


class BaseAgentEndpointSupport:
    async def stream_chat(self, request: BaseAgentRequest, scope_name: str):
        await self.authorization_service.assert_authorized(request.session_id, scope_name)
        agent_request = self.request_factory.from_http(request, scope_name)
        return self.ai_chat_service.stream_agent_chat(agent_request)
```
