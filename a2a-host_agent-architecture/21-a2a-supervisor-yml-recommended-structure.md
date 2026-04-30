# 21. A2A Supervisor Settings Structure

Updated: 2026-04-28 (Implementation Aligned)
Aligned with: `src/app/config/supervisor.yml`

## Application Configuration Rules

- **Resource Separation**: `app.yml` (공통 인프라), `supervisor.yml` (런타임 정책), `prompts.yml` (프롬프트 리소스)로 역할을 분리한다.
- **Environment Isolation**: 하드코딩된 endpoint나 API key를 지양하고 설정 파일 또는 환경변수를 사용한다.

## Actual Structure Reference

```yaml
host:
  a2a:
    # API 진입점 허용 메서드 목록
    method-allowlist:
      - message/send
      - SendMessage
      - message/stream
      - SendStreamingMessage
      - tasks/get
      - GetTask
      - tasks/list
      - ListTasks
      - tasks/cancel
      - CancelTask
      - tasks/events
      - TaskEvents
      - tasks/review/get
      - tasks/review/decide
      - agent/card

    # Downstream 에이전트 라우팅 테이블
    routing:
      product:
        endpoint: http://localhost:8082/a2a/product
        method: message/send
        timeout-ms: 120000
      reservation:
        endpoint: http://localhost:8082/a2a/reservation
        method: message/send
        timeout-ms: 120000

    # 재시도 및 탄력성 정책
    retry:
      max-retries: 0
      initial-backoff-ms: 500
      max-backoff-ms: 3000
    circuit-breaker:
      enabled: true
      failure-threshold: 2
      open-duration-ms: 3000

    # 오케스트레이션 제약 조건
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
    
    # 스트리밍 및 이벤트 유지 정책
    stream:
      timeout-ms: 120000
```

## Policy Rules

1. **Downstream Onboarding**: 신규 에이전트 추가 시 `host.a2a.routing.{agent_key}` 섹션을 추가하는 것만으로 런타임에 즉시 반영된다.
2. **Circuit Breaker**: 에이전트별 연속 실패가 `failure-threshold`를 초과하면 자동으로 차단(Open)되며, `open-duration-ms` 이후 다시 시도한다.
3. **Idempotency Key**: 모든 Redis 키는 `supervisor:session:{id}` 접두사를 사용하여 멀티 테넌시 및 데이터 격리를 보장한다.
4. **Handoff Guard**: `allow-methods`에 명시되지 않은 메서드로의 핸드오프 요청은 보안 정책상 거부된다.
5. **Stream Integrity**: `stream.timeout-ms`는 클라이언트 구독 유지 시간의 상한을 정의한다.
