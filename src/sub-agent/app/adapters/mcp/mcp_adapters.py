"""
[Sub-Agent] MCP 도구 실행 어댑터
==================================
책임: MCP 서버에 도구 실행을 요청하고 결과 반환 (ToolExecutor Port 구현)
아키텍처 위치: Adapter Layer — MCP Integration (Outbound)

실행 전 검증 (Schema Guard):
  1. Runtime 필드 주입 (session_id, trace_id, task_id 등)
  2. GUID 필드 자동 생성 (중복 방지 식별자)
  3. 필수 파라미터 누락 검사 → [MISSING_REQUIRED_PARAMS]
  4. 알 수 없는 필드 검사 → [SCHEMA_MISMATCH_UNKNOWN_PARAMS]
  5. inputSchema 엄격 준수

핵심 보안 규칙:
  - LLM이 생성한 도구 호출을 inputSchema 기준으로 검증
  - schema에 없는 파라미터 차단 (환각 방지)
  - 필수 파라미터 누락 시 차단 (불완전한 실행 방지)
"""

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
    MCP 도구 실행기.
    Registry(도구 메타정보) + SessionManager(전송 계층) 조합으로 도구 실행.
    """
    def __init__(self, registry: McpToolRegistry, session_manager: McpClientSessionManager):
        self.registry = registry
        self.session_manager = session_manager

    @staticmethod
    def _is_missing(value: Any) -> bool:
        """값이 없거나 빈 문자열인지 확인"""
        return value is None or (isinstance(value, str) and not value.strip())

    def _collect_missing_required(
        self,
        schema: Dict[str, Any],
        data: Any,
        path: str = ""
    ) -> List[str]:
        """inputSchema의 required 필드 중 누락된 항목 재귀 수집 (중첩 객체 지원)"""
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
            missing.extend(self._collect_missing_required(child_schema, data_obj.get(key), f"{path}.{key}" if path else key))

        return missing

    def _collect_unknown_fields(
        self,
        schema: Dict[str, Any],
        data: Any,
        path: str = ""
    ) -> List[str]:
        """inputSchema에 없는 필드 수집 (LLM 환각 방지)"""
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
        """
        inputSchema의 guid 필드에 런타임 GUID 자동 주입.
        LLM이 생성하지 못하는 식별자를 시스템이 보완.
        """
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
        """필드명 정규화 (대소문자+특수문자 무시한 비교용)"""
        return "".join(ch for ch in str(name).lower() if ch.isalnum())

    def _schema_contains_runtime_key(self, schema: Dict[str, Any], normalized_runtime_keys: set[str]) -> bool:
        """스키마에 특정 런타임 키가 존재하는지 재귀 검사"""
        if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
            return False
        for key, child_schema in schema.get("properties", {}).items():
            if self._normalize_field_name(key) in normalized_runtime_keys:
                return True
            if isinstance(child_schema, dict) and self._schema_contains_runtime_key(child_schema, normalized_runtime_keys):
                return True
        return False

    def _inject_runtime_fields(self, schema: Dict[str, Any], data: Any, runtime_fields: Dict[str, Any]) -> None:
        """
        런타임 필드 자동 주입 (session_id, trace_id, task_id 등).
        LLM이 제공하지 않아도 시스템이 채워주는 필드.
        """
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
        """
        MCP 도구 실행 (Schema Guard 포함).
        1. 세션 초기화 확인
        2. 런타임/GUID 필드 주입
        3. inputSchema 검증 (missing/unknown)
        4. tools/call 호출
        """
        session = self.session_manager.get_session(plan.server_name)
        log = logger.bind(tool=plan.tool_name, server=plan.server_name, url=session.url)

        log.info("executing_mcp_tool")

        try:
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
                    return {"status": "error", "message": f"[MISSING_REQUIRED_PARAMS] {', '.join(missing_required)}"}

                unknown_fields = self._collect_unknown_fields(input_schema, arguments)
                if unknown_fields:
                    log.warn("mcp_tool_unknown_params", unknown=unknown_fields)
                    return {"status": "error", "message": f"[SCHEMA_MISMATCH_UNKNOWN_PARAMS] {', '.join(unknown_fields)}"}

            params = {"name": plan.tool_name, "arguments": arguments}
            log.info("mcp_tool_request", params=params)

            result = await session.call("tools/call", params)
            log.info("mcp_tool_response", result=result)

            if "error" in result:
                log.error("mcp_tool_execution_error", error=result["error"])
                return {"status": "error", "message": result["error"].get("message")}

            log.info("mcp_tool_execution_success")
            return {"status": "success", "output": result.get("result", {}).get("content", "Success")}

        except Exception as e:
            log.error("mcp_transport_error", error=str(e))
            return {"status": "error", "message": f"Transport error: {str(e)}"}
