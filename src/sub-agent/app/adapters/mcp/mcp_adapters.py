import structlog
from typing import Dict, Any, Optional, List
from copy import deepcopy
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

    @staticmethod
    def _is_missing(value: Any) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())

    def _collect_missing_required(
        self,
        schema: Dict[str, Any],
        data: Any,
        path: str = ""
    ) -> List[str]:
        missing: List[str] = []
        if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
            return missing

        properties = schema.get("properties", {})
        required = schema.get("required", [])
        data_obj = data if isinstance(data, dict) else {}

        for key in required:
            key_path = f"{path}.{key}" if path else key
            if key not in data_obj or self._is_missing(data_obj.get(key)):
                missing.append(key_path)

        for key, child_schema in properties.items():
            if child_schema.get("type") != "object":
                continue
            if key not in data_obj or not isinstance(data_obj.get(key), dict):
                continue
            key_path = f"{path}.{key}" if path else key
            missing.extend(self._collect_missing_required(child_schema, data_obj.get(key), key_path))

        return missing

    def _collect_unknown_fields(
        self,
        schema: Dict[str, Any],
        data: Any,
        path: str = ""
    ) -> List[str]:
        unknown: List[str] = []
        if not isinstance(data, dict):
            return unknown
        if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
            return unknown

        properties = schema.get("properties", {})
        for key, value in data.items():
            key_path = f"{path}.{key}" if path else key
            child_schema = properties.get(key)
            if child_schema is None:
                unknown.append(key_path)
                continue
            if isinstance(value, dict) and child_schema.get("type") == "object":
                unknown.extend(self._collect_unknown_fields(child_schema, value, key_path))
        return unknown

    def _inject_guid_fields(self, schema: Dict[str, Any], data: Any, runtime_guid: str) -> None:
        if not isinstance(data, dict):
            return
        if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
            return

        properties = schema.get("properties", {})
        for key, child_schema in properties.items():
            if key.lower() == "guid":
                data[key] = runtime_guid
                continue
            if child_schema.get("type") == "object":
                if key not in data or not isinstance(data.get(key), dict):
                    continue
                self._inject_guid_fields(child_schema, data[key], runtime_guid)

    @staticmethod
    def _normalize_field_name(name: str) -> str:
        return "".join(ch for ch in str(name).lower() if ch.isalnum())

    def _schema_contains_runtime_key(self, schema: Dict[str, Any], normalized_runtime_keys: set[str]) -> bool:
        if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
            return False
        for key, child_schema in schema.get("properties", {}).items():
            if self._normalize_field_name(key) in normalized_runtime_keys:
                return True
            if isinstance(child_schema, dict) and self._schema_contains_runtime_key(child_schema, normalized_runtime_keys):
                return True
        return False

    def _inject_runtime_fields(self, schema: Dict[str, Any], data: Any, runtime_fields: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            return
        if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
            return

        normalized_runtime = {
            self._normalize_field_name(k): v
            for k, v in (runtime_fields or {}).items()
            if v is not None and not (isinstance(v, str) and not v.strip())
        }
        properties = schema.get("properties", {})
        runtime_keys = set(normalized_runtime.keys())

        for key, child_schema in properties.items():
            normalized_key = self._normalize_field_name(key)
            if normalized_key in normalized_runtime and self._is_missing(data.get(key)):
                data[key] = normalized_runtime[normalized_key]

            if child_schema.get("type") == "object":
                if key not in data or not isinstance(data.get(key), dict):
                    if self._schema_contains_runtime_key(child_schema, runtime_keys):
                        data[key] = {}
                    else:
                        continue
                self._inject_runtime_fields(child_schema, data[key], runtime_fields)

    async def execute(self, plan: ToolPlan, runtime_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
            arguments = deepcopy(plan.arguments) if plan.arguments else {}

            tool_schema = self.registry.get_tool_schema(plan.tool_name, plan.server_name)
            input_schema = tool_schema.get("inputSchema", {})

            if input_schema:
                self._inject_runtime_fields(input_schema, arguments, runtime_fields or {})
                self._inject_guid_fields(input_schema, arguments, guid)
                missing_required = self._collect_missing_required(input_schema, arguments)
                if missing_required:
                    log.warn("mcp_tool_missing_required_params", missing=missing_required)
                    return {
                        "status": "error",
                        "message": f"[MISSING_REQUIRED_PARAMS] {', '.join(missing_required)}"
                    }

                unknown_fields = self._collect_unknown_fields(input_schema, arguments)
                if unknown_fields:
                    log.warn("mcp_tool_unknown_params", unknown=unknown_fields)
                    return {
                        "status": "error",
                        "message": f"[SCHEMA_MISMATCH_UNKNOWN_PARAMS] {', '.join(unknown_fields)}"
                    }

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
