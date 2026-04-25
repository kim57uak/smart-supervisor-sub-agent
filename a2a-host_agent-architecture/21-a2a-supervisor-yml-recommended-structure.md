# 21. A2A Supervisor Settings Recommended Structure

Updated: 2026-04-25
Aligned with: `settings/supervisor.yml`

## Application Baseline

- `app.yml`에는 provider 연결 정보와 공통 앱 설정만 남긴다.
- supervisor 동작 설정은 `supervisor.yml`, `supervisor-hitl.yml`, `supervisor-system-prompt.yml`로 분리한다.
- 레거시 `mcp.yml`과 tool warmup 설정은 기준선에서 제거한다.
- `FrozenExecutionPlan` 구조 정본은 `31-frozen-execution-plan-schema.md`를 따른다.

## Recommended Shape

```yaml
app:
  llm:
    openai:
      model: gpt-5.4-mini
      timeout-seconds: 30
    google:
      model: gemini-2.5-pro

host:
  a2a:
    routing:
      product:
        endpoint: http://localhost:8082/a2a/product
        method: message/send
        timeout-ms: 120000
      reservation:
        endpoint: http://localhost:8083/a2a/reservation
        method: message/send
        timeout-ms: 120000
    retry:
      max-retries: 0
      initial-backoff-ms: 500
      max-backoff-ms: 3000
    circuit-breaker:
      enabled: true
      failure-threshold: 2
      open-duration-ms: 30000
    execution:
      max-concurrency: 2
    history:
      max-turns: 5
    a2ui:
      enabled: true
    handoff:
      enabled: true
      max-hops: 3
      block-same-agent-within-steps: 2
      allow-methods:
        - message/send
        - SendMessage
        - message/stream
        - SendStreamingMessage
    stream:
      timeout-ms: 120000
      heartbeat-interval-ms: 15000
      retention-minutes: 30

supervisor:
  hitl:
    review-snapshot-required: true
    review-snapshot-ttl-minutes: 30
    approval-verification:
      require-resume-token: true
      require-state-version: true
      require-request-hash: true
      require-frozen-plan-hash: true
  consistency:
    reconciliation:
      enabled: true
      max-retries: 3
      retry-backoff-ms: 25
      orphan-cleanup-delay-ms: 30000
  snapshot:
    schema-version: 1
    canonicalization-version: 1
  prompts:
    planning-system: file:settings/supervisor-system-prompt.yml
    compose-system: file:settings/supervisor-system-prompt.yml
```

## Rules

- 신규 downstream agent 온보딩의 기본 경로는 `host.a2a.routing.{agent_key}` 추가다.
- supervisor는 `yml + agent card`만으로 신규 agent를 인식하고 routing/invocation 대상으로 삼을 수 있어야 한다.
- `routing`은 downstream allowlist다.
- `routing.*.method`는 agent별 기본 JSON-RPC method다.
- `routing.*.timeout-ms`는 agent별 경계 timeout이다.
- `retry`는 supervisor -> downstream A2A 호출 재시도 정책이다.
- `circuit-breaker`는 agent별 연속 실패 보호 정책이다.
- `execution.max-concurrency`는 invoke 배치 동시성 상한이다.
- `history.max-turns`는 planning/compose prompt 주입용 최근 대화 턴 수다.
- `a2ui.enabled=true`일 때만 pre-HITL A2UI 또는 compose A2UI를 생성할 수 있다.
- `handoff.enabled=true`일 때만 downstream handoff directive를 반영한다.
- prompt 리소스는 설정 파일에서 읽고 endpoint/application service 하드코딩을 금지한다.
- planner review 판단 실패는 `require_review` 또는 `reject`로만 처리해야 하며 fail-open을 금지한다.
- approval verification 4종이 모두 맞아야 resume 가능하다.
- 운영값은 환경변수 또는 profile별 설정에서 override 가능해야 한다.

## Compatibility Rules

- method는 `legacy + v1.0` 호환 기준을 유지한다.
- method alias는 validator 또는 mapper에서 내부 enum으로 정규화한다.
- stream method는 downstream agent card가 streaming capability를 가진 경우에만 사용한다.
- review approve 후 `STREAM` 실행은 approve HTTP 응답에서 이어서 전달하지 않고 task 기준 재구독 stream으로만 전달한다.

## Idempotency / Correlation Rules

- Redis key는 반드시 내부 기준 `session_id` 포함 복합키를 사용한다.
- idempotency key는 `session_id + method + request_id + normalized params hash`를 사용한다.
- 내부 correlation key는 `trace_id`, `request_id`, `session_id`를 요청 전 구간에 전달해야 한다.

## Operational Rules

- timeout, retry, circuit-breaker, concurrency, handoff 정책값은 코드 하드코딩 금지다.
- progress 출력은 `supervisor_progress_publisher` 공통 포맷을 사용한다.
- task payload persistence는 final result 채널 전용이며 stream transport 이벤트는 저장 경계 밖에 둔다.
- approve ack와 runtime stream payload는 같은 HTTP 응답으로 섞지 않는다.
