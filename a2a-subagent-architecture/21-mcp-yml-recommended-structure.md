# 21. Sub-Agent Configuration Structure

Updated: 2026-05-01 (Implementation Aligned)
Aligned with: `src/sub-agent/app/core/config.py`

## Configuration Principles

- **Pydantic Settings**: 인프라 및 런타임 수치 제어는 `pydantic-settings`와 환경변수(`SUBAGENT_` prefix)를 우선한다.
- **Resource Separation**: LLM 프롬프트 등 텍스트 리소스는 `app/config/prompts.yml`에서 별도 관리한다.
- **MCP Server Registry**: 연동할 MCP 서버 목록 및 도구 허용 목록을 중앙 설정으로 관리한다.

## Environment Variables (.env)

```bash
SUBAGENT_DEBUG=false
SUBAGENT_REDIS_URL=redis://localhost:6379/0
SUBAGENT_OPENAI_API_KEY=sk-...
SUBAGENT_ORCHESTRATION_ENGINE=langgraph # or burr
```

## Nested Settings Structure (Reference)

Derived from `src/sub-agent/app/core/config.py`:

### Agent Runtime & Graph
```python
agent:
  graph:
    max_tool_iterations: 4
    checkpoint_enabled: true
  runtime:
    request_timeout: "20s"
    max_tool_calls_per_request: 6
  trace:
    enabled: true
    propagate_fields: ["trace_id", "request_id", "session_id"]
```

### MCP Servers Connectivity
```python
mcp_servers:
  weather:
    host: "http://10.225.18.50:8080"
    protocol: "streamable"
    endpoint: "/mcp"
    tools: ["getWeatherForecastByLocation", "getAlerts"]
  reservation:
    host: "http://10.225.18.50:8080"
    tools: ["createReservation"]
```

## Required Policy

1. **Trace Propagation**: `trace_id`, `request_id`, `session_id`는 모든 주요 계층에 전달되어야 하며, Supervisor 전달값을 우선 사용한다.
2. **MCP Registry**: `McpToolRegistry`는 설정된 `mcp_servers` 정보를 기반으로 런타임에 툴 스키마를 동적으로 로드한다.
3. **Idempotency**: 모든 Redis 키는 `subagent:idempotency` 네임스페이스를 사용하여 격리되며, `request_id` 기반 중복 실행을 방지한다.
4. **Prompt Management**: `app/config/prompts.yml`에서 시스템 프롬프트를 중앙 관리하며, `Settings.prompts` 프로퍼티를 통해 접근한다.
5. **Session Lifecycle Policy**: 
    - **Generation**: `session_id`는 오직 **Client UI**에서 생성(localStorage/UUID)되어야 한다.
    - **Propagation**: 모든 A2A 호출(Supervisor -> Sub-agent) 시 최상위 파라미터에 명시적으로 전달되어야 한다.
    - **Resolution**: 서버는 전달된 세션 ID를 절대적으로 신뢰하며, 소멸된 세션을 복구하기 위해 내부 상태(Redis 등)를 기반으로 추론하지 않는다.
