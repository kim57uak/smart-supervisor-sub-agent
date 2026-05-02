# 21. A2A Supervisor Settings Structure

Updated: 2026-05-01 (Implementation Aligned)
Aligned with: `src/app/core/config.py` and `src/app/config/*.yml`

## Application Configuration Rules

- **Resource Separation**: `config.py` (Core Pydantic settings), `prompts.yml` (LLM instructions), `hitl_messages.yml` (User-facing review reasons).
- **Environment Isolation**: Uses `pydantic-settings` with `SUPERVISOR_` prefix for infrastructure (Redis URL, API Keys).
- **Hardcoding Elimination**: Core contracts like method names and routing defaults are defined in `DefaultConfig` but overridable via env/YAML.

## Actual Structure Reference (Method Allowlist)

Derived from `src/app/core/config.py`:

```python
# Standardized API methods supported by the Supervisor
ALLOWLIST = [
    "message/send", "SendMessage",
    "message/stream", "SendStreamingMessage",
    "tasks/get", "GetTask",
    "tasks/list", "ListTasks",
    "tasks/cancel", "CancelTask",
    "tasks/events", "TaskEvents",
    "tasks/review/get", 
    "tasks/review/decide",
    "agent/card", 
    "session/clear", "ClearSession"
]
```

## Routing Table (Default)

```yaml
routing:
  product:
    endpoint: http://127.0.0.1:8082/a2a/product
  reservation:
    endpoint: http://127.0.0.1:8082/a2a/reservation
  supply-cost:
    endpoint: http://127.0.0.1:8082/a2a/supply-cost
  weather:
    endpoint: http://127.0.0.1:8082/a2a/weather
```

## Policy Rules

1. **Downstream Onboarding**: 신규 에이전트 추가 시 `A2aSettings.routing` 딕셔너리에 추가하거나 `SUPERVISOR_A2A__ROUTING__<AGENT>__ENDPOINT` 환경변수를 통해 동적 추가 가능.
2. **Circuit Breaker**: `DefaultA2AInvocationService`에서 관리하며, 실패 임계치 초과 시 즉시 차단됨.
3. **Idempotency Key**: 모든 Redis 키는 `package:` 접두사와 `supervisor:idempotency` 네임스페이스를 사용하여 격리됨.
4. **Prompt Management**: `app/config/prompts.yml`에서 시스템 프롬프트를 중앙 관리하며, 런타임에 리로드 없이 프로퍼티로 접근 가능.
5. **HITL Messages**: `app/config/hitl_messages.yml`에서 리뷰 사유별 한국어 메시지를 관리하여 UI 응답 품질을 유지함.
