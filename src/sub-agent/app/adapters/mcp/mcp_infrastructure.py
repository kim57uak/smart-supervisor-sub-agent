import uuid
import httpx
import structlog
import json
from typing import Dict, Any, Optional
from ...core.config import settings
from abc import ABC, abstractmethod

logger = structlog.get_logger(__name__)

# ──────────────────────────────────────────────
# MCP 전송 추상 기본 클래스
# ──────────────────────────────────────────────
# MCP(Model Context Protocol) 서버와의 통신 전략을 정의하는 추상 기본 클래스.
# call(요청-응답)과 notify(알림) 두 가지 패턴을 지원한다.
# 하위 클래스는 특정 MCP 서버 스펙(Spring AI, 표준 SSE 등)에 맞게 구현한다.
class McpTransport(ABC):
    def __init__(self, host: str, endpoint: str, server_id: str, client: httpx.AsyncClient):
        self.url = f"{host}{endpoint}"                 # MCP 서버 전체 URL
        self.server_id = server_id                     # 설정 파일의 서버 식별자
        self.client = client                           # 공유 httpx 세션
        self.guid = str(uuid.uuid4()).lower()          # 요청 추적용 GUID

    @abstractmethod
    async def call(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """JSON-RPC 2.0 호출 → 응답 반환"""
        pass

    @abstractmethod
    async def notify(self, method: str, params: Dict[str, Any]) -> None:
        """알림 전송 (응답 불필요)"""
        pass

# ──────────────────────────────────────────────
# Spring AI MCP 전송 구현체
# ──────────────────────────────────────────────
# Spring AI MCP 서버(Streamable HTTP)와 통신한다.
# 세션 기반 핸드셰이크(initialize → session-id 획득)와 SSE 응답 파싱을 처리한다.
# 하나투어 상품/예약/고객 MCP 서버 연결에 사용된다.
class SpringAiMcpTransport(McpTransport):
    def __init__(self, host: str, endpoint: str, server_id: str, client: httpx.AsyncClient):
        super().__init__(host, endpoint, server_id, client)
        self.session_id = None                         # 핸드셰이크 후 서버가 발급

    # HTTP 요청 헤더 구성
    # - Content-Type / Accept: JSON + SSE 동시 지원
    # - X-GUID: 서버 측 추적용 고유 식별자
    # - Mcp-Session-Id: 초기화 이후 세션 유지용
    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "X-GUID": self.guid,
            "User-Agent": "Hanatour-SmartMCP/1.0"
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    # JSON-RPC 2.0 요청 전송 → SSE 또는 JSON 응답 파싱
    # initialize 호출 시 자동으로 프로토콜 버전/클라이언트 정보를 주입한다.
    # SSE 응답(data: ...)과 일반 JSON 응답을 모두 처리한다.
    async def call(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        import random
        request_id = random.randint(1, 1000000)
        
        json_params = params if params is not None else {}
        
        if method == "initialize":
             json_params = {
                 "protocolVersion": "2024-11-05",
                 "clientInfo": {"name": "Spring AI MCP Client", "version": "1.1.4"},
                 "capabilities": {}
             }

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": json_params,
            "id": request_id
        }

        try:
            payload_str = json.dumps(payload) + "\n"
            response = await self.client.post(self.url, content=payload_str, headers=self._get_headers())
            response.raise_for_status()

            # 최초 응답에서 Mcp-Session-Id 수집
            if not self.session_id:
                self.session_id = response.headers.get("Mcp-Session-Id")
                if self.session_id:
                    logger.info("mcp_session_established", session_id=self.session_id, server_id=self.server_id)
            
            text = response.text.strip()
            if not text:
                return {"result": {}}
                
            # SSE(data: ...) → JSON 변환
            json_text = text
            if "data:" in text:
                for line in text.split("\n"):
                    if line.startswith("data:"):
                        json_text = line[len("data:"):].strip()
                        break
            elif "\n" in text:
                json_text = text.split("\n")[0]
            
            return json.loads(json_text)
        except Exception as e:
            logger.error("mcp_call_failed", error=str(e), url=self.url, guid=self.guid)
            raise

    # 알림 전송 (응답 불필요한 단방향 메시지)
    # notifications/initialized 같은 핸드셰이크 완료 신호에 사용된다.
    async def notify(self, method: str, params: Dict[str, Any]) -> None:
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        try:
            payload_str = json.dumps(payload) + "\n"
            await self.client.post(self.url, content=payload_str, headers=self._get_headers())
        except Exception as e:
            logger.warn("mcp_notification_failed", error=str(e), url=self.url, guid=self.guid)

# ──────────────────────────────────────────────
# MCP 전송 객체 팩토리
# ──────────────────────────────────────────────
# 설정 파일(mcp_servers)에 정의된 서버별 전송 전략을 생성한다.
# 공유 httpx 클라이언트를 관리하여 연결 풀을 재사용한다.
class McpTransportFactory:
    def __init__(self):
        self._shared_client = httpx.AsyncClient(timeout=60.0, follow_redirects=True, http2=False)

    def create_transport(self, server_name: str) -> McpTransport:
        config = settings.mcp_servers.get(server_name)
        if not config:
            raise ValueError(f"MCP Server configuration not found: {server_name}")
            
        protocol = getattr(config, "protocol", "STREAMABLE").upper()
        
        if protocol == "STREAMABLE":
            return SpringAiMcpTransport(config.host, config.endpoint, server_name, self._shared_client)
        else:
            # 알 수 없는 프로토콜 → SpringAiMcpTransport 폴백
            logger.warn("unknown_mcp_protocol_falling_back", protocol=protocol, server_name=server_name)
            return SpringAiMcpTransport(config.host, config.endpoint, server_name, self._shared_client)

# ──────────────────────────────────────────────
# MCP 클라이언트 세션 관리자
# ──────────────────────────────────────────────
# 서버별 McpTransport 인스턴스를 캐싱하여 세션을 재사용한다.
# 동일 서버에 대한 반복 연결 시 매번 새 연결을 생성하지 않도록 한다.
class McpClientSessionManager:
    def __init__(self, transport_factory: McpTransportFactory):
        self.factory = transport_factory
        self._sessions: Dict[str, McpTransport] = {}

    def get_session(self, server_name: str) -> McpTransport:
        if server_name not in self._sessions:
            self._sessions[server_name] = self.factory.create_transport(server_name)
        return self._sessions[server_name]
