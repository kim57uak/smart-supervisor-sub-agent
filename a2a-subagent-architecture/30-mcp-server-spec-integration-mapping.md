# 30. MCP Server Spec & Integration Mapping

**Updated**: 2026-04-30  
**Context**: MCP Server 기술 스펙에 따른 Sub-Agent 대응 전략

본 문서는 연동 대상 MCP 서버의 기술적 특성(Implementation Stack)에 따라 Sub-Agent의 `McpTransport` 및 핸드셰이크 로직이 어떻게 적응해야 하는지를 정의한다.

---

## 1. Spec Mapping Table

| 서버 기술 스펙 (Server Spec) | 주요 특성 (Characteristics) | Sub-Agent 대응 전략 (Integration Strategy) |
| :--- | :--- | :--- |
| **Spring AI (Streamable HTTP)** | Stateless POST 기반, 세션 식별자 필요 | 2단계 핸드셰이크 (`initialize` -> `Mcp-Session-Id` 획득 -> 재주입) |
| **Standard SSE (text/event-stream)** | 응답 데이터가 `data:` 접두사와 함께 스트리밍됨 | `Accept` 헤더에 `text/event-stream` 포함 및 전용 SSE 파서 가동 |
| **Strict JSON-RPC 2.0** | `jsonrpc`, `id`, `method` 필드 필수 | 모든 요청 페이로드에 표준 규격 강제 및 Random ID 생성기 사용 |
| **HanaTour Internal Proxy** | 상위 프록시에서 `X-GUID` 기반 로깅 수행 | 모든 요청에 `X-GUID` 및 `User-Agent` 헤더 필수 포함 |

---

## 2. Implementation Strategy: Strategy Pattern

다양한 MCP 서버 스펙에 효과적으로 대응하기 위해 **전략 패턴(Strategy Pattern)**을 기반으로 전송 계층을 설계하였다.

- **McpTransport (Base Strategy)**: 추상 인터페이스 정의.
- **SpringAiMcpTransport (Concrete Strategy)**: Spring AI 특화 로직(세션, SSE 파싱) 구현.
- **StandardSseMcpTransport (Concrete Strategy)**: 표준 SSE 통신 규약 구현 (예정).
- **McpTransportFactory (Automatic Selector)**: 
    - `mcp.yml`의 `protocol` 설정을 읽어 런타임에 적절한 전략 객체를 **자동으로 주입(Automatic Switching)**한다.
    - 상위 레이어는 구체적인 전송 방식을 알 필요 없이 동일한 `McpTransport` 인터페이스만 사용한다.

---

## 3. Detailed Strategy by Spec

### 2.1 Spring AI Streamable HTTP 대응
Spring AI MCP 서버는 표준 웹 전송 환경에서도 세션을 유지하기 위해 자체적인 세션 ID 관리 방식을 사용한다.
- **적용 로직**: `McpTransport` 내부에 `session_id` 상태를 유지한다.
- **위험 요소**: 세션 ID 없이 요청 시 서버는 `400 Bad Request`를 반환하므로, 반드시 `initialize`를 선행하여 세션을 확립해야 한다.

### 2.2 SSE (Server-Sent Events) 처리
전통적인 JSON 응답이 아닌 스트리밍 방식으로 도구 결과가 전달되는 경우에 대응한다.
- **적용 로직**: 응답 바디를 줄 단위로 읽어 `data:`로 시작하는 라인만 추출하여 JSON 디코딩을 수행한다.
- **주의 사항**: 한 번의 응답에 여러 개의 `data:` 라인이 올 수 있으므로, 비즈니스 로직에 맞는 첫 번째 또는 최종 객체 선택 전략이 필요하다.

### 2.3 GUID 및 추적성 (Observability)
엔터프라이즈 환경에서 서비스 간 추적성을 보장하기 위한 규약이다.
- **적용 로직**: UUID를 생성하여 `X-GUID` 헤더에 주입하며, 이는 서버 로그와 서브에이전트 로그를 매핑하는 유일한 키가 된다.
- **User-Agent**: 서버 측 프록시(WAF 등)에서 클라이언트를 식별할 수 있도록 `Hanatour-SmartMCP/1.0`과 같은 명시적 식별자를 사용한다.

---

## 3. Configuration Mapping (mcp.yml)

서버 스펙에 따른 설정을 `mcp.yml`에서 제어할 수 있도록 권장한다.
```yaml
mcp-servers:
  package-smart-mcp:
    host: "http://10.225.18.50:8080"
    endpoint: "/mcp"
    protocol: "STREAMABLE"  # 스펙 명시
    transport: "HTTP_SSE"   # 전송 방식 명시
```

이 매핑 가이드를 통해 신규 MCP 서버 연동 시 발생할 수 있는 시행착오를 최소화한다.
