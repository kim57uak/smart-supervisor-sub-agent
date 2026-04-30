# 20. MCP Package / Class Specification

**Updated**: 2026-04-30 (Session Management & McpTransport Handshake Fix)  
**Source baseline**: `src/sub-agent/app`

## 1. Target Overview

본 문서는 `mcp-orchestrator` (Sub-agent)의 핵심 전송 계층과 세션 관리 로직을 정의한다. 특히 Java 기반 Spring AI MCP 서버와의 안정적인 연동을 위해 **Streamable HTTP** 프로토콜 준수 및 **Stateful Session** 유지 전략을 핵심으로 한다.

### Core Principles
- **Session-Based Handshake**: Stateless HTTP 환경에서 `Mcp-Session-Id`를 이용한 연속적 세션 보장.
- **SSE (Server-Sent Events) Awareness**: 스트리밍 응답 데이터(`data:` prefix)의 실시간 파싱 및 추출.
- **Hexagonal Integrity**: 인프라 종속성(httpx, SSE)을 `Adapters` 계층으로 격리하여 비즈니스 로직 보호.

---

## 2. Component Specifications

### 2.1 McpTransport (Strategy Pattern)
- **역할**: 다양한 MCP 서버 기술 스펙에 대응하기 위한 추상 전송 계층 인터페이스를 정의한다.
- **디자인 패턴**: **Strategy Pattern**을 적용하여 서버 스펙별로 다른 전송 로직을 캡슐화한다.
- **핵심 필드**:
    - `url`: 서버 엔드포인트 주소.
    - `guid`: 모든 요청 헤더(`X-GUID`)에 포함되는 추적용 고유 ID.
- **추상 메서드**:
    - `call(method, params)`: JSON-RPC 요청 전송 및 응답 처리의 공통 규약.
    - `notify(method, params)`: 단방향 알림 전송 규약.

### 2.2 SpringAiMcpTransport (Concrete Strategy)
- **역할**: Spring AI MCP (Streamable HTTP) 규약을 준수하는 구체적 전략 클래스.
- **특화 로직**:
    - **Session-Id Management**: `Mcp-Session-Id`를 추출하여 상태값으로 보관 및 재주입.
    - **SSE Response Parsing**: `data:` 접두사가 포함된 응답에서 JSON 페이로드를 정밀 추출.

### 2.3 McpTransportFactory (Factory Layer)
- **역할**: 설정 파일(`mcp.yml`)의 `protocol` 정보를 기반으로 적절한 `McpTransport` 구현체를 **자동으로 생성**한다.
- **핵심 책임**:
    - **Automatic Strategy Selection**: `protocol: "STREAMABLE"` 설정 시 `SpringAiMcpTransport`를, 미지정 또는 다른 값일 경우 해당 스펙에 맞는 전략을 자동으로 선택 및 반환.
    - **Resource Sharing**: 모든 트랜스포트 인스턴스가 단일 `httpx.AsyncClient`를 공유하도록 제어하여 커넥션 풀 효율성 극대화.

### 2.4 McpClientSessionManager (Adapter Layer)
- **역할**: 다중 MCP 서버 연결에 대한 트랜스포트 인스턴스의 라이프사이클 및 캐싱을 관리한다.
- **자동 전환 지원**: 팩토리가 선택한 구체적인 전략에 상관없이 동일한 인터페이스로 세션을 제공하여 상위 계층(`McpExecutor`)의 코드 수정을 불필요하게 함.

### 2.3 McpExecutor (Execution Layer)
- **역할**: 도구 호출 계획(`ToolPlan`)을 실제 MCP 요청으로 변환하여 실행한다.
- **핸드셰이크 전략**: 
    - 세션 ID가 없는 신규 연결 시, `initialize`를 선제적으로 수행하여 세션 식별자를 확보한 후 본 요청을 수행한다.

---

## 3. Communication Protocol (Contracts)

### 3.1 Handshake Sequence
1. **Initial Call**: `Accept` 헤더와 함께 `initialize` 메서드 호출.
2. **Session Identification**: 응답 헤더의 `Mcp-Session-Id`를 캡처하여 트랜스포트 상태에 저장.
3. **Subsequent Calls**: 모든 후속 요청 헤더에 획득한 세션 ID를 포함하여 전송.

### 3.2 Header Specification
| Header Name | Value | Description |
| :--- | :--- | :--- |
| `Content-Type` | `application/json` | 요청 본문 형식 |
| `Accept` | `application/json, text/event-stream` | 스트리밍 응답 수용 선언 |
| `Mcp-Session-Id` | `<uuid>` | 세션 상태 유지 식별자 (필수) |
| `X-GUID` | `<uuid>` | 분산 추적 및 로깅용 ID |
| `User-Agent` | `Hanatour-SmartMCP/1.0` | 클라이언트 식별 정보 |

---

## 4. Implementation Guidelines

- **Timeout Management**: 네트워크 지연을 고려하여 기본 타임아웃을 60초로 설정하며, 스트리밍 응답 대기를 지원한다.
- **Error Propagation**: 400 Bad Request 또는 5xx 에러 발생 시, 원시 에러 메시지를 `McpCallException`으로 래핑하여 상위 계층에 전달한다.
- **HTTP/1.1 Preference**: Spring AI MCP 서버의 호환성을 위해 HTTP/1.1 커넥션을 우선적으로 활용한다.
