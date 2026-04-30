import uuid
import pytest
import pytest_asyncio
import asyncio
from typing import AsyncGenerator, Dict, Any

from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings
from app.domain.enums import ReasonCode, ProcessStatus


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Provides an asynchronous test client for the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def base_plan_data() -> Dict[str, Any]:
    """Provides a baseline mock plan data for tests."""
    return {
        "routing_queue": [
            {
                "order": 0,
                "agent_key": "sub-agent",
                "method": "message/send",
                "source_type": "PLANNER",
                "reason": "test",
                "priority": 0,
                "preHitlA2ui": None,
                "arguments": {"message": "hello"},
                "handoff_depth": 0,
            }
        ],
        "execution_constraints": {
            "max_concurrency": 1,
            "stream_allowed": True,
            "invoke_timeout_ms": 30000,
            "max_handoff_depth": 3,
            "a2ui_allowed": True,
        },
        "planner_metadata": {"reasoning": "test reasoning"},
    }


@pytest.mark.asyncio
async def test_full_supervisor_flow(
    monkeypatch: pytest.MonkeyPatch, async_client: AsyncClient, base_plan_data: Dict[str, Any], mock_redis: Any
) -> None:
    """
    Simulates a full cycle: Send -> Review -> Approve -> Events.
    Forces HitlGate to return review_required=True by mocking the planning service.
    """

    async def mock_plan(*args: Any, **kwargs: Any) -> tuple[bool, Dict[str, Any]]:
        return True, base_plan_data

    monkeypatch.setattr(
        "app.adapters.llm.llm_planning_service.LlmPlanningService.plan",
        mock_plan,
    )

    session_id = f"test-session-{uuid.uuid4()}"
    original_msg = "Hello, sub-agent!"

    # 1. Send Message
    send_request = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {"session_id": session_id, "message": original_msg},
        "id": 1,
    }

    response = await async_client.post(settings.api_prefix, json=send_request)
    assert response.status_code == 200
    data = response.json()
    assert "result" in data, f"Response error: {data.get('error')}"
    
    task_id = data["result"]["task_id"]
    assert data["result"]["status"] == ProcessStatus.WAITING_REVIEW.value

    # 2. Approve Review
    approve_request = {
        "jsonrpc": "2.0",
        "method": "tasks/review/decide",
        "params": {
            "task_id": task_id,
            "decision": "APPROVE",
            "session_id": session_id,
            "request_params": {"message": original_msg, "session_id": session_id},
        },
        "id": 2,
    }

    response = await async_client.post(settings.api_prefix, json=approve_request)
    assert response.status_code == 200
    data = response.json()
    assert "result" in data, f"Approve failed: {data.get('error') or data.get('result')}"
    assert data["result"]["resume_accepted"] is True
    
    initial_cursor = data["result"]["initial_cursor"]

    # 3. Stream Resume (Valid Cursor)
    stream_request = {
        "jsonrpc": "2.0",
        "method": "tasks/events",
        "params": {
            "task_id": task_id,
            "session_id": session_id,
            "cursor": initial_cursor,
            "replay": True,
        },
        "id": 3,
    }

    # Manually append a DONE event so the stream generator in the server can finish
    from app.application.persistence.task_event_stream_service import TaskEventStreamService
    from app.domain.enums import EventType
    event_service = TaskEventStreamService(mock_redis)
    await event_service.append_event(session_id, task_id, EventType.DONE, {"status": "finished"})

    async with async_client.stream("POST", f"{settings.api_prefix}/stream", json=stream_request) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        # Read at least one line to ensure it works
        async for line in response.aiter_lines():
            if line:
                break


@pytest.mark.asyncio
async def test_verification_hash_mismatch(
    monkeypatch: pytest.MonkeyPatch, async_client: AsyncClient, base_plan_data: Dict[str, Any]
) -> None:
    """
    Test Verification: Hash mismatch should be rejected.
    """

    async def mock_plan(*args: Any, **kwargs: Any) -> tuple[bool, Dict[str, Any]]:
        return True, base_plan_data

    monkeypatch.setattr(
        "app.adapters.llm.llm_planning_service.LlmPlanningService.plan",
        mock_plan,
    )

    session_id = "session_h"
    resp1 = await async_client.post(
        settings.api_prefix,
        json={
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {"session_id": session_id, "message": "original"},
        },
    )
    task_id = resp1.json()["result"]["task_id"]

    # Approve with modified request params -> Hash Mismatch
    resp2 = await async_client.post(
        settings.api_prefix,
        json={
            "jsonrpc": "2.0",
            "method": "tasks/review/decide",
            "params": {
                "task_id": task_id,
                "decision": "APPROVE",
                "session_id": session_id,
                "request_params": {"message": "TAMPERED", "session_id": session_id},
            },
        },
    )
    data2 = resp2.json()
    assert data2["result"]["resume_accepted"] is False
    assert data2["result"]["reason_code"] == ReasonCode.REQUEST_HASH_MISMATCH.value


@pytest.mark.asyncio
async def test_verification_drift_blocked(
    monkeypatch: pytest.MonkeyPatch, async_client: AsyncClient, base_plan_data: Dict[str, Any]
) -> None:
    """
    Test Verification: Retired agent in plan should trigger PLAN_DRIFT_BLOCKED.
    """
    import copy
    plan_data = copy.deepcopy(base_plan_data)
    plan_data["routing_queue"][0]["agent_key"] = "retired_agent"

    async def mock_plan(*args: Any, **kwargs: Any) -> tuple[bool, Dict[str, Any]]:
        return True, plan_data

    monkeypatch.setattr(
        "app.adapters.llm.llm_planning_service.LlmPlanningService.plan",
        mock_plan,
    )

    session_id = "session_drift"
    resp1 = await async_client.post(
        settings.api_prefix,
        json={
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {"session_id": session_id, "message": "hello"},
        },
    )
    task_id = resp1.json()["result"]["task_id"]

    resp2 = await async_client.post(
        settings.api_prefix,
        json={
            "jsonrpc": "2.0",
            "method": "tasks/review/decide",
            "params": {
                "task_id": task_id,
                "decision": "APPROVE",
                "session_id": session_id,
                "request_params": {"message": "hello", "session_id": session_id},
            },
        },
    )
    data2 = resp2.json()
    assert data2["result"]["resume_accepted"] is False
    assert data2["result"]["reason_code"] == ReasonCode.PLAN_DRIFT_BLOCKED.value


@pytest.mark.asyncio
async def test_stream_replay_false(async_client: AsyncClient) -> None:
    """
    Test Stream: replay=False should start from tail.
    """
    stream_request = {
        "jsonrpc": "2.0",
        "method": "tasks/events",
        "params": {
            "task_id": str(uuid.uuid4()),
            "session_id": "any",
            "replay": False,
        },
    }
    
    try:
        response = await asyncio.wait_for(
            async_client.post(f"{settings.api_prefix}/stream", json=stream_request),
            timeout=2.0,
        )
        assert response.status_code == 200
    except asyncio.TimeoutError:
        pass  # Timeout is expected if no events arrive


@pytest.mark.asyncio
async def test_contract_validation_missing_fields(async_client: AsyncClient) -> None:
    """
    Test Contract: Missing task_id or invalid decision.
    """
    invalid_request_1 = {
        "jsonrpc": "2.0",
        "method": "tasks/review/decide",
        "params": {"decision": "APPROVE"},
        "id": 1,
    }
    resp1 = await async_client.post(settings.api_prefix, json=invalid_request_1)
    assert resp1.status_code == 200
    assert "error" in resp1.json()
    assert "task_id" in resp1.json()["error"]["message"]


@pytest.mark.asyncio
async def test_state_transition_duplicate_approve(
    monkeypatch: pytest.MonkeyPatch, async_client: AsyncClient, base_plan_data: Dict[str, Any]
) -> None:
    """
    Test State Transition: Duplicate approve should be idempotent.
    """
    import copy
    plan_data = copy.deepcopy(base_plan_data)
    plan_data["routing_queue"] = []

    async def mock_plan(*args: Any, **kwargs: Any) -> tuple[bool, Dict[str, Any]]:
        return True, plan_data

    monkeypatch.setattr(
        "app.adapters.llm.llm_planning_service.LlmPlanningService.plan",
        mock_plan,
    )

    session_id = f"test-session-{uuid.uuid4()}"
    original_msg = "Hello"
    
    resp1 = await async_client.post(
        settings.api_prefix,
        json={
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {"session_id": session_id, "message": original_msg},
        },
    )
    task_id = resp1.json()["result"]["task_id"]

    approve_req = {
        "jsonrpc": "2.0",
        "method": "tasks/review/decide",
        "params": {
            "task_id": task_id,
            "decision": "APPROVE",
            "session_id": session_id,
            "request_params": {"message": original_msg, "session_id": session_id},
        },
    }

    # First approve
    resp2 = await async_client.post(settings.api_prefix, json=approve_req)
    assert resp2.json()["result"]["resume_accepted"] is True

    # Second approve (Duplicate)
    resp3 = await async_client.post(settings.api_prefix, json=approve_req)
    assert resp3.json()["result"]["resume_accepted"] is True
