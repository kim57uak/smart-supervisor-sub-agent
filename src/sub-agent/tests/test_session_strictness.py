import pytest
from unittest.mock import MagicMock, AsyncMock
from app.api.support.a2a_handler import handle_a2a_request, JsonRpcRequest, JsonRpcResponse

# 세션 ID 필수 검증 테스트
# message/send 요청에 session_id가 누락되면 -32602 에러를 반환해야 한다.
# 이는 A2A 프로토콜의 세션 기반 통신 요구사항을 검증한다.
@pytest.mark.asyncio
async def test_session_id_required():
    request = JsonRpcRequest(
        method="message/send",
        params={
            "message": "hello",
            # session_id 누락됨
        },
        id="test-1"
    )
    
    executor = MagicMock()
    response = await handle_a2a_request("test-agent", request, executor=executor)
    
    assert response.error is not None
    assert response.error["message"] == "session_id is required"
    assert response.error["code"] == -32602

# 세션 ID 전파 검증 테스트
# session_id와 task_id가 올바르게 추출되어 executor.execute()의 인자로 전달되어야 한다.
@pytest.mark.asyncio
async def test_session_id_propagation():
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
    
    # executor.execute() 호출 검증: 첫 번째 인자 = session_id, 두 번째 인자 = task_id
    executor.execute.assert_called_once()
    args, kwargs = executor.execute.call_args
    assert args[0] == "sess-123"   # session_id
    assert args[1] == "task-456"   # task_id
