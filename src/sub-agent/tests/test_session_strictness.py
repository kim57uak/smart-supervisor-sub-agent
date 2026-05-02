import pytest
from unittest.mock import MagicMock, AsyncMock
from app.api.support.a2a_handler import handle_a2a_request, JsonRpcRequest, JsonRpcResponse

@pytest.mark.asyncio
async def test_session_id_required():
    """
    Test that SendMessage requires session_id.
    """
    request = JsonRpcRequest(
        method="message/send",
        params={
            "message": "hello",
            # session_id is missing
        },
        id="test-1"
    )
    
    # Rationale (Why): Executor is passed to trigger the execution path where session_id is checked.
    executor = MagicMock()
    response = await handle_a2a_request("test-agent", request, executor=executor)
    
    assert response.error is not None
    assert response.error["message"] == "session_id is required"
    assert response.error["code"] == -32602

@pytest.mark.asyncio
async def test_session_id_propagation():
    """
    Test that session_id is correctly extracted and passed to executor.
    """
    request = JsonRpcRequest(
        method="message/send",
        params={
            "message": "hello",
            "session_id": "sess-123",
            "task_id": "task-456"
        },
        id="test-2"
    )
    
    executor = MagicMock()
    executor.execute = AsyncMock(return_value={"final_answer": "pong", "results": []})
    
    response = await handle_a2a_request("test-agent", request, executor=executor)
    
    assert response.error is None
    assert response.result["payload"]["answer"] == "pong"
    
    # Verify propagation
    executor.execute.assert_called_once()
    args, kwargs = executor.execute.call_args
    assert args[0] == "sess-123" # session_id
    assert args[1] == "task-456" # task_id
