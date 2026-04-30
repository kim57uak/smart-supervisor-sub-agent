# 28. Supervisor A2UI Architecture & Operating Model

Updated: 2026-04-28 (Refined implementation sync)

## A2UI Design Principles

A2UI(Agent-to-UI)는 Supervisor 응답의 풍부함을 더하는 선택적 계층이다. 모든 A2UI는 기본 텍스트 응답을 동반해야 하며, UI 로딩 실패가 응답 전체의 실패로 이어지지 않아야 한다.

## Lifecycle Integration

### 1. Pre-HITL A2UI (Interactive Input)
- **Phase**: 플래닝 직후, 워커 실행 전.
- **Goal**: 하위 에이전트 실행에 필요한 추가 정보를 사용자로부터 구조화된 폼(Form)을 통해 수집한다.
- **Behavior**: `PreHitlA2uiService`가 플랜의 힌트를 해석하여 적절한 `surfaceId`를 클라이언트에 전달한다.

### 2. Post-Invoke Compose A2UI (Result Rendering)
- **Phase**: 모든 하위 에이전트 실행 완료 후 합성(Compose) 단계.
- **Goal**: 실행 결과를 단순 텍스트 이상으로 표현(예: 일정표, 상품 카드)한다.
- **Behavior**: `LlmSupervisorResponseComposeService`가 결과 데이터를 기반으로 `a2ui` 이벤트를 발행한다.

## Security & Reliability

- **Data Sanitization**: A2UI 페이로드에 포함되는 모든 데이터는 `PromptInjectionGuard` 및 도메인 정규화기를 거쳐 안전하게 전달된다.
- **Graceful Fallback**: 클라이언트가 특정 A2UI 스펙을 지원하지 않거나 렌더링에 실패하더라도, 텍스트 응답 채널을 통해 핵심 정보 전달이 보장된다.
- **Separation of Concerns**: 비즈니스 로직(Worker)은 데이터만 생성하고, UI 구조화는 전용 서비스와 어댑터가 담당한다.
