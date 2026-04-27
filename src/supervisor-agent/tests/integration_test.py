import pytest
import asyncio
import uuid
import json
from httpx import AsyncClient
from ..app.main import app
from ..app.core.config import settings

@pytest.mark.asyncio
async def test_full_supervisor_flow():
    """
    Simulates a full cycle: Send -> Review -> Approve -> Events
    """
    async with AsyncClient(app=app, base_url="http://test") as ac:
        session_id = f"test-session-{uuid.uuid4()}"
        
        # 1. Send Message (Should trigger WAITING_REVIEW)
        send_request = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "session_id": session_id,
                "message": "Hello, sub-agent!"
            },
            "id": 1
        }
        
        response = await ac.post(settings.api_prefix, json=send_request)
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        task_id = data["result"]["task_id"]
        assert data["result"]["state"] == "WAITING_REVIEW"
        
        # 2. Approve Review
        approve_request = {
            "jsonrpc": "2.0",
            "method": "tasks/review/decide",
            "params": {
                "task_id": task_id,
                "decision": "APPROVE"
            },
            "id": 2
        }
        
        response = await ac.post(settings.api_prefix, json=approve_request)
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["resume_accepted"] is True
        assert data["result"]["stream_resume_required"] is True
        initial_cursor = data["result"]["initial_cursor"]
        
        # 3. Connect to Event Stream (SSE)
        stream_request = {
            "jsonrpc": "2.0",
            "method": "tasks/events",
            "params": {
                "task_id": task_id,
                "cursor": initial_cursor
            },
            "id": 3
        }
        
        # In a real test, we would use a streaming client, 
        # but for this integration test, we verify the endpoint exists and responds
        response = await ac.post(f"{settings.api_prefix}/stream", json=stream_request)
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        
        # Verify first few lines of the stream if possible
        # (This depends on how fast the background task starts)
        print("\nFlow test completed successfully!")
