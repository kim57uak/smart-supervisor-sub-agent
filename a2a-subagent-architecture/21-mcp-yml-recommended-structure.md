# 21. Recommended Configuration Structure

Updated: 2026-04-25

## settings/mcp.yml

```yaml
#=============개발서버 설정===============================
---
spring:
  config:
    activate:
      on-profile: dev

mcp:
  weather:
    host: http://10.225.18.50:8080
    protocol: streamable
    endpoint: /mcp
    reuse-session: true
    cache-tools: true
    allow-legacy-sse-fallback: true
    tools: getWeatherForecastByLocation, getAlerts
  supply-cost:
    host: http://10.225.18.50:8080
    protocol: streamable
    endpoint: /mcp
    reuse-session: true
    cache-tools: true
    allow-legacy-sse-fallback: true
    tools: getSupplyCostInfo
  reservation:
    host: http://10.225.18.50:8080
    protocol: streamable
    endpoint: /mcp
    reuse-session: true
    cache-tools: true
    allow-legacy-sse-fallback: true
    tools: createReservation

  sale-product:
    host: http://10.225.18.50:8080
    protocol: streamable
    endpoint: /mcp
    reuse-session: true
    cache-tools: true
    allow-legacy-sse-fallback: true
    tools: createAutoCopySaleProducts, getSaleProductDetails
```

## settings/agent.yml

```yaml
agent:
  graph:
    max_tool_iterations: 4
    checkpoint_enabled: true
    graph_id: default_graph
  runtime:
    request_timeout: 20s
    provider_timeout: 12s
    tool_timeout: 8s
    max_tool_calls_per_request: 6
    max_prompt_tokens: 8192
    max_completion_tokens: 2048
    provider_fallback_order: [gemini-2.5-flash]
    concurrency:
      per_scope_max_inflight: 32
      per_scope_max_queue_size: 128
    tool_parallel:
      enabled: false
      max_parallel_tool_calls: 1
      max_parallel_tool_calls_cap: 3
      strategy: continue-on-error
  trace:
    enabled: true
    propagate_fields: [trace_id, request_id, session_id]
    use_supervisor_values_first: true
    generate_missing_only: true
    request_id_source: a2a_jsonrpc_id
  redis:
    ttl: 30m
    key_prefix:
      global: PACKAGE
      conversation: PACKAGE:agent:conv
      checkpoint: PACKAGE:agent:ckpt
      a2a_task: PACKAGE:agent:a2a
  default_model: gemini-2.5-flash
  scopes:
    weather:
      allowed_servers: [weather]
      allowed_tools_by_server:
        weather: [get_weather_forecast_by_location, get_alerts]
      default_model: gemini-2.5-flash
    supply_cost:
      allowed_servers: [supply_cost]
      allowed_tools_by_server:
        supply_cost: [get_supply_cost_info]
      default_model: gemini-2.5-flash
    reservation:
      allowed_servers: [reservation]
      allowed_tools_by_server:
        reservation: [create_reservation]
      default_model: gemini-2.5-flash
    sale_product:
      allowed_servers: [sale_product]
      allowed_tools_by_server:
        sale_product: [create_auto_copy_sale_products, get_sale_product_details]
      default_model: gemini-2.5-flash
```

## settings/a2a.yml

```yaml
a2a:
  enabled: true
  public_base_url: http://localhost:8080
  scopes:
    - weather
    - supply_cost
    - reservation
    - sale_product
```

## Required Policy

- runtime guardrail 값은 모두 `settings/agent.yml`에서 관리한다.
- transport retry/fallback도 코드 하드코딩이 아니라 설정 정책으로만 관리한다.
- tool 병렬 호출 기본 정책은 `enabled=false`, `max_parallel_tool_calls=1`이다.
- request correlation(`trace_id + request_id + session_id`)은 모든 주요 계층에 전달되어야 한다.
- correlation key는 supervisor 전달값을 우선 사용하고 누락된 값만 sub-agent가 생성한다.
- 설정 키는 `snake_case`를 사용하고, 공개 URL path는 `sale-product`처럼 hyphenated scope를 사용할 수 있다.
