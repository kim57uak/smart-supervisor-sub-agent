import uuid
import httpx
import structlog
import json
from typing import Dict, Any, Optional
from ...core.config import settings
from abc import ABC, abstractmethod

logger = structlog.get_logger(__name__)

class McpTransport(ABC):
    """
    Abstract base class for MCP transport strategies.
    Defines the contract for communicating with various MCP server specifications.
    """
    def __init__(self, host: str, endpoint: str, server_id: str, client: httpx.AsyncClient):
        self.url = f"{host}{endpoint}"
        self.server_id = server_id
        self.client = client
        self.guid = str(uuid.uuid4()).lower()

    @abstractmethod
    async def call(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def notify(self, method: str, params: Dict[str, Any]) -> None:
        pass

class SpringAiMcpTransport(McpTransport):
    """
    Strategy for Spring AI MCP Server (Streamable HTTP).
    Handles session-based handshake and SSE response parsing.
    """
    def __init__(self, host: str, endpoint: str, server_id: str, client: httpx.AsyncClient):
        super().__init__(host, endpoint, server_id, client)
        self.session_id = None

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

            if not self.session_id:
                self.session_id = response.headers.get("Mcp-Session-Id")
                if self.session_id:
                    logger.info("mcp_session_established", session_id=self.session_id, server_id=self.server_id)
            
            text = response.text.strip()
            if not text:
                return {"result": {}}
                
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

    async def notify(self, method: str, params: Dict[str, Any]) -> None:
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        try:
            payload_str = json.dumps(payload) + "\n"
            await self.client.post(self.url, content=payload_str, headers=self._get_headers())
        except Exception as e:
            logger.warn("mcp_notification_failed", error=str(e), url=self.url, guid=self.guid)

class McpTransportFactory:
    """
    Factory for creating McpTransport instances based on server configuration.
    """
    def __init__(self):
        self._shared_client = httpx.AsyncClient(timeout=60.0, follow_redirects=True, http2=False)

    def create_transport(self, server_name: str) -> McpTransport:
        config = settings.mcp_servers.get(server_name)
        if not config:
            raise ValueError(f"MCP Server configuration not found: {server_name}")
            
        # Rationale: Default to SpringAiMcpTransport but allow future expansion.
        # Check config for protocol/transport type.
        protocol = getattr(config, "protocol", "STREAMABLE").upper()
        
        if protocol == "STREAMABLE":
            return SpringAiMcpTransport(config.host, config.endpoint, server_name, self._shared_client)
        else:
            # Placeholder for other strategies
            logger.warn("unknown_mcp_protocol_falling_back", protocol=protocol, server_name=server_name)
            return SpringAiMcpTransport(config.host, config.endpoint, server_name, self._shared_client)

class McpClientSessionManager:
    """
    Manages session state and lifecycle for MCP clients.
    """
    def __init__(self, transport_factory: McpTransportFactory):
        self.factory = transport_factory
        self._sessions: Dict[str, McpTransport] = {}

    def get_session(self, server_name: str) -> McpTransport:
        if server_name not in self._sessions:
            self._sessions[server_name] = self.factory.create_transport(server_name)
        return self._sessions[server_name]
