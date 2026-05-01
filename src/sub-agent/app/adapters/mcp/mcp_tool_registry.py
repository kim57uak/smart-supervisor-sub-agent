import httpx
import structlog
from typing import List, Dict, Any, TYPE_CHECKING
from ...core.config import settings

if TYPE_CHECKING:
    from .mcp_infrastructure import McpTransportFactory

logger = structlog.get_logger(__name__)

class McpToolRegistry:
    """
    Handles real-time MCP tool discovery with mandatory handshakes.
    """
    def __init__(self, transport_factory: "McpTransportFactory"):
        self.factory = transport_factory
        self._tools = []

    async def refresh_tools(self) -> List[Dict[str, Any]]:
        """
        Performs 100% real-time discovery of tools from configured MCP servers.
        Sequence: initialize -> notifications/initialized -> ping -> tools/list
        """
        all_discovered_tools = []
        
        # Iterate through all configured MCP servers
        for server_name, config in settings.mcp_servers.items():
            logger.info("mcp_discovery_start", server=server_name, url=config.host)
            
            try:
                # 1. Create a dedicated transport for discovery session via factory
                transport = self.factory.create_transport(server_name)
                
                # 2. Handshake: initialize
                # Rationale: Handshake parameters are handled internally by the transport strategy (e.g. SpringAiMcpTransport)
                init_result = await transport.call("initialize", {})
                
                if "error" in init_result:
                    logger.error("mcp_init_failed", server=server_name, error=init_result["error"])
                    continue

                # 3. Handshake: notifications/initialized
                await transport.notify("notifications/initialized", {})

                # 4. Get Tools: tools/list
                tools_result = await transport.call("tools/list", {})
                
                if "result" in tools_result and "tools" in tools_result["result"]:
                    discovered = tools_result["result"]["tools"]
                    logger.info("mcp_discovery_success", server=server_name, count=len(discovered))
                    
                    for tool in discovered:
                        tool_name = tool.get("name")
                        # Add server context to the tool info for later routing
                        tool["server_id"] = server_name
                        all_discovered_tools.append(tool)
                        logger.info("mcp_tool_registered", server=server_name, tool=tool_name)
                else:
                    logger.warn("mcp_no_tools_found", server=server_name, result=tools_result)

            except Exception as e:
                logger.error("mcp_discovery_exception", server=server_name, error=str(e))
        
        self._tools = all_discovered_tools
        return self._tools

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Returns the discovered tool schemas for LLM context."""
        return self._tools

    def get_tool_server(self, tool_name: str) -> str:
        """Finds which server hosts the given tool."""
        for tool in self._tools:
            if tool.get("name") == tool_name:
                return tool.get("server_id", "unknown")
        return "unknown"

    def get_tool_schema(self, tool_name: str, server_name: str | None = None) -> Dict[str, Any]:
        """
        Returns the discovered MCP tool metadata (including inputSchema).
        If server_name is provided, it must match.
        """
        for tool in self._tools:
            if tool.get("name") != tool_name:
                continue
            if server_name and tool.get("server_id") != server_name:
                continue
            return tool
        return {}
