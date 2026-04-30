# 23. ai_chat_service Improvement Plan

Updated: 2026-04-25

## Future Role

`ai_chat_service`는 더 이상 단순 endpoint helper가 아니라, 외부 계약을 유지하는 facade 역할을 담당한다.

## Responsibilities

- endpoint request를 `agent_chat_request`로 전달
- `agent_orchestrator` 실행 위임
- text/plain, ndjson, A2A stream contract에 맞는 결과 변환
- error fallback 유지
- `SendStreamingMessage` / `SubscribeToTask`용 SSE 응답 변환 지원

## Internal Refactoring

- `chat(prompt)` 중심 구조에서 `stream_agent_chat(request)` 중심 구조로 확장
- 기존 도메인 서비스는 `scope`와 `tool properties`만 제공
- 공통 history handling은 support 계층이 아니라 application service와 request factory로 이동
- orchestrator 내부는 `prepare_execution -> stream_compose` 2단계로 분리해 streaming path에서 전체 chunk buffering을 피한다

## Compatibility Strategy

- 기존 public HTTP API 경로는 유지
- 기존 text streaming 반환 형태는 유지 가능하되 내부 표준 결과는 `AsyncIterator[AiChatChunk]`로 통일한다
- A2A canonical JSON-RPC entrypoint는 `POST /a2a/{scope}` 하나로 유지하고, streaming 여부는 method와 response content type으로 구분한다
