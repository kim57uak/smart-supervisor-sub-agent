# 20. MCP Package / Class Specification

**Updated**: 2026-04-30 (Real-time Discovery & Handshake Refinement)  
**Source baseline**: `src/sub-agent/app/adapters/mcp`

## 1. Target Overview

본 문서는 `sub-agent`의 핵심 MCP(Model Context Protocol) 연동 계층을 정의한다. Java 기반 Spring AI MCP 서버와의 안정적인 연동을 위해 **Real-time Discovery**, **Stateful Session**, 및 **Streamable HTTP** 프로토콜 준수를 핵심으로 한다.

---

## 2. Component Specifications

### 2.1 McpTransport (Strategy Pattern)
- **역할**: 다양한 MCP 서버 기술 스펙에 대응하기 위한 추상 전송 계층 인터페이스.
- **추상 메서드**: `call(method, params)`, `notify(method, params)`.

### 2.2 SpringAiMcpTransport (Concrete Strategy)
- **역할**: Spring AI MCP (Streamable HTTP) 규약을 준수하는 구체적 전략 클래스.
- **특화 로직**: `Mcp-Session-Id` 관리 및 SSE(Server-Sent Events) 응답 파싱.

### 2.3 McpTransportFactory
- **역할**: 설정 기반으로 적절한 `McpTransport` 구현체를 생성하고 `httpx.AsyncClient`를 공유 관리.

### 2.4 McpToolRegistry (Discovery Layer)
- **역할**: 설정된 모든 MCP 서버로부터 실시간 도구 목록을 수집.
- **Discovery Sequence**: `initialize` -> `notifications/initialized` -> `tools/list`.
- **기능**: 도구 스키마 제공 및 도구 이름별 서버 매핑(`get_tool_server`).

### 2.5 McpClientSessionManager
- **역할**: 실행 시점에 필요한 트랜스포트 인스턴스의 라이프사이클 및 세션 캐싱 관리.

### 2.6 McpExecutor (Execution Layer)
- **역할**: LLM의 도구 호출 계획을 실제 MCP 요청으로 변환하여 실행.

---

## 3. Communication Protocol (Contracts)

### 3.1 Handshake Sequence (Strict)
1. **Initialize**: `protocolVersion`, `clientInfo`를 포함하여 `initialize` 메서드 호출.
2. **Session Capture**: 응답 헤더의 `Mcp-Session-Id`를 획득.
3. **Initialized Notification**: `notifications/initialized` 알림을 전송하여 활성화.
4. **Operations**: 이후 모든 요청에 세션 ID 포함.

### 3.2 Error Handling
- **Handshake Failure**: 초기화 실패 시 해당 서버를 제외하고 로깅.
- **SSE Parsing**: `data:` 접두사가 없는 경우에도 유연하게 JSON을 추출하도록 폴백 로직 적용.
