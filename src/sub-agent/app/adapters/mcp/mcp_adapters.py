import structlog
from typing import Dict, Any, Optional
from ...ports.interfaces import ToolExecutor
from ...domain.models import ToolPlan
from .mcp_tool_registry import McpToolRegistry
from .mcp_infrastructure import McpClientSessionManager

logger = structlog.get_logger(__name__)

class McpExecutor(ToolExecutor):
    """
    Executes tools by calling MCP servers via decoupled infrastructure.
    Implements the ToolExecutor port.
    """
    def __init__(self, registry: McpToolRegistry, session_manager: McpClientSessionManager):
        self.registry = registry
        self.session_manager = session_manager

    async def execute(self, plan: ToolPlan) -> Dict[str, Any]:
        session = self.session_manager.get_session(plan.server_name)
        log = logger.bind(tool=plan.tool_name, server=plan.server_name, url=session.url)

        log.info("executing_mcp_tool")

        try:
            # Ensure session is initialized before tool execution
            if not session.session_id:
                log.info("initializing_mcp_session", reason="session_id_missing")
                init_result = await session.call("initialize", {})
                if "error" in init_result:
                    log.error("mcp_session_init_failed", error=init_result["error"])
                    return {"status": "error", "message": f"Session init failed: {init_result['error'].get('message')}"}
                log.info("mcp_session_initialized", session_id=session.session_id)

            import uuid
            guid = f"py-{uuid.uuid4().hex[:12]}"
            arguments = plan.arguments.copy() if plan.arguments else {}
            if "guid" not in arguments:
                arguments["guid"] = guid

            params = {
                "name": plan.tool_name,
                "arguments": arguments
            }

            log.info("mcp_tool_request", params=params)

            result = await session.call("tools/call", params)

            log.info("mcp_tool_response", result=result)

            if "error" in result:
                log.error("mcp_tool_execution_error", error=result["error"])
                return {"status": "error", "message": result["error"].get("message")}

            log.info("mcp_tool_execution_success")
            return {
                "status": "success",
                "output": result.get("result", {}).get("content", "Success")
            }

        except Exception as e:
            log.error("mcp_transport_error", error=str(e))
            return {"status": "error", "message": f"Transport error: {str(e)}"}
