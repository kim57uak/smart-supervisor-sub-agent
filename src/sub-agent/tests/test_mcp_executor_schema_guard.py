import pytest

from app.adapters.mcp.mcp_adapters import McpExecutor
from app.domain.models import ToolPlan


# ──────────────────────────────────────────────
# Fake MCP 세션 — 실제 MCP 서버 없이 테스트용
# ──────────────────────────────────────────────
class _FakeSession:
    def __init__(self):
        self.url = "http://fake-mcp"
        self.session_id = "sid-1"
        self.calls = []

    async def call(self, method, params):
        self.calls.append((method, params))
        if method == "tools/call":
            return {"result": {"content": [{"type": "text", "text": "ok"}]}}
        return {"result": {}}


class _FakeSessionManager:
    def __init__(self, session):
        self._session = session

    def get_session(self, _server_name):
        return self._session


class _FakeRegistry:
    def __init__(self, schema):
        self._schema = schema

    def get_tool_schema(self, tool_name, server_name=None):
        return {"name": tool_name, "server_id": server_name, "inputSchema": self._schema}


# Schema Guard — 누락 필드 차단 검증
# 필수 필드(request.saleProductCode)가 없으면 MISSING_REQUIRED_PARAMS 에러를 반환하고
# tools/call이 실행되지 않아야 한다.
@pytest.mark.asyncio
async def test_executor_blocks_missing_required_nested_fields():
    schema = {
        "type": "object",
        "properties": {
            "request": {
                "type": "object",
                "properties": {
                    "bookerKoreanName": {"type": "string"},
                    "guid": {"type": "string"},
                    "saleProductCode": {"type": "string"},
                },
                "required": ["bookerKoreanName", "guid", "saleProductCode"],
            }
        },
        "required": ["request"],
    }
    session = _FakeSession()
    executor = McpExecutor(_FakeRegistry(schema), _FakeSessionManager(session))
    plan = ToolPlan(
        tool_name="reservation/createReservation",
        server_name="reservation",
        arguments={"request": {"bookerKoreanName": "김병두"}},
        reasoning="test",
    )

    result = await executor.execute(plan)
    assert result["status"] == "error"
    assert "[MISSING_REQUIRED_PARAMS]" in result["message"]
    assert "request.saleProductCode" in result["message"]
    assert not any(method == "tools/call" for method, _ in session.calls)


# Schema Guard — 알 수 없는 필드 차단 검증
# 스키마에 정의되지 않은 필드(unexpectedKey)가 전달되면
# SCHEMA_MISMATCH_UNKNOWN_PARAMS 에러를 반환하고 tools/call이 차단되어야 한다.
@pytest.mark.asyncio
async def test_executor_blocks_unknown_fields():
    schema = {
        "type": "object",
        "properties": {"request": {"type": "object", "properties": {}, "required": []}},
        "required": ["request"],
    }
    session = _FakeSession()
    executor = McpExecutor(_FakeRegistry(schema), _FakeSessionManager(session))
    plan = ToolPlan(
        tool_name="reservation/createReservation",
        server_name="reservation",
        arguments={"request": {"unexpectedKey": "x"}},
        reasoning="test",
    )

    result = await executor.execute(plan)
    assert result["status"] == "error"
    assert "[SCHEMA_MISMATCH_UNKNOWN_PARAMS]" in result["message"]
    assert "request.unexpectedKey" in result["message"]
    assert not any(method == "tools/call" for method, _ in session.calls)


# Schema Guard — GUID 필드 자동 주입 검증
# guid 필드가 inputSchema에 정의되어 있으면 런타임 GUID(py-...)로 자동 치환된다.
# 이는 하나투어 MCP 표준 GUID 요구사항을 충족한다.
@pytest.mark.asyncio
async def test_executor_injects_runtime_guid_for_nested_guid_fields():
    schema = {
        "type": "object",
        "properties": {
            "request": {
                "type": "object",
                "properties": {
                    "bookerKoreanName": {"type": "string"},
                    "guid": {"type": "string"},
                    "saleProductCode": {"type": "string"},
                },
                "required": ["bookerKoreanName", "guid", "saleProductCode"],
            }
        },
        "required": ["request"],
    }
    session = _FakeSession()
    executor = McpExecutor(_FakeRegistry(schema), _FakeSessionManager(session))
    plan = ToolPlan(
        tool_name="reservation/createReservation",
        server_name="reservation",
        arguments={
            "request": {
                "bookerKoreanName": "김병두",
                "guid": "unique-guid-placeholder",
                "saleProductCode": "AAX20126043000P",
            }
        },
        reasoning="test",
    )

    result = await executor.execute(plan)
    assert result["status"] == "success"
    tools_call = [c for c in session.calls if c[0] == "tools/call"]
    assert tools_call
    sent_arguments = tools_call[0][1]["arguments"]
    assert sent_arguments["request"]["guid"].startswith("py-")
    assert sent_arguments["request"]["guid"] != "unique-guid-placeholder"


# Schema Guard — runtime_fields session_id 주입 검증
# runtime_fields에 session_id가 제공되면, 스키마에 session_id 필드가 정의된 경우
# 해당 값이 인자에 자동 주입되어 MCP 호출에 포함되어야 한다.
@pytest.mark.asyncio
async def test_executor_injects_runtime_session_id_by_schema_name():
    schema = {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "saleProductCode": {"type": "string"},
        },
        "required": ["session_id", "saleProductCode"],
    }
    session = _FakeSession()
    executor = McpExecutor(_FakeRegistry(schema), _FakeSessionManager(session))
    plan = ToolPlan(
        tool_name="product/getSaleProduct",
        server_name="product",
        arguments={"saleProductCode": "AAX20126043000P"},
        reasoning="test",
    )

    result = await executor.execute(plan, runtime_fields={"session_id": "sess-from-runtime"})
    assert result["status"] == "success"
    tools_call = [c for c in session.calls if c[0] == "tools/call"]
    assert tools_call
    sent_arguments = tools_call[0][1]["arguments"]
    assert sent_arguments["session_id"] == "sess-from-runtime"
