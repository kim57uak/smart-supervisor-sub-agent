import pytest
from httpx import AsyncClient, ASGITransport
from app.core.config import settings
import asyncio
import json

@pytest.mark.asyncio
async def test_subagent_chat_flow(app, mock_redis):
    # 'app' here is the fixture from conftest.py
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. API: Send Chat Request
        payload = {
            "session_id": "test-session",
            "message": "What is the weather in Seoul?",
            "request_id": "req-123"
        }
        # Document 06/07: Expects 202 Accepted
        response = await ac.post(f"{settings.api_prefix}/agent/chat", json=payload)
        assert response.status_code == 202
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "ACCEPTED"
        task_id = data["task_id"]

        # 2. Redis: Check if task is enqueued (Key matches Document 12)
        queue_data = await mock_redis.brpop("package:subagent:task_queue", timeout=1)
        assert queue_data is not None
        _, task_payload_str = queue_data
        task_payload = json.loads(task_payload_str)
        assert task_payload["task_id"] == task_id
        assert task_payload["message"] == "What is the weather in Seoul?"

        # 3. Persistence: Check if task state is saved (Key matches Document 12)
        task_key = f"package:subagent:task:{task_id}"
        task_state_str = await mock_redis.get(task_key)
        assert task_state_str is not None
        task_state = json.loads(task_state_str)
        assert task_state["status"] == "ACCEPTED"

@pytest.mark.asyncio
async def test_subagent_worker_execution(mock_redis):
    from app.ports.interfaces import Planner, Composer
    from app.domain.models import PlanningContext, ToolPlan, Message, AiChatChunk
    from app.application.execution.executor import AgentExecutor
    from app.adapters.orchestration.langgraph_factory import WorkflowFactory
    from app.application.persistence.agent_persistence import AgentPersistence
    from app.domain.enums import ProcessStatus
    from typing import List, AsyncIterator
    
    # 1. Setup Dummy Services
    from app.core.config import McpServerSettings
    settings.mcp_servers["test_server"] = McpServerSettings(host="http://test")
    
    class MockPlanning(Planner):
        async def plan(self, context: PlanningContext) -> List[ToolPlan]:
            return [ToolPlan(tool_name="test_tool", server_name="test_server", arguments={}, reasoning="test")]
            
    class MockCompose(Composer):
        async def stream_compose(self, context: PlanningContext) -> AsyncIterator[AiChatChunk]:
            # Rationale (Why): Composition results must be AiChatChunk objects (Doc 18).
            yield AiChatChunk(content="Hello")
            yield AiChatChunk(content=" World")
            
    from app.adapters.mcp.mcp_adapters import McpExecutor
    from app.adapters.mcp.mcp_tool_registry import McpToolRegistry
    from app.adapters.mcp.mcp_infrastructure import McpTransportFactory, McpClientSessionManager
    
    transport_factory = McpTransportFactory()
    registry = McpToolRegistry(transport_factory)
    # Mock refresh_tools to avoid hitting real MCP servers during tests
    async def mock_refresh(): return []
    registry.refresh_tools = mock_refresh
    await registry.refresh_tools()
    
    session_manager = McpClientSessionManager(transport_factory)
    executor = McpExecutor(registry, session_manager)
    
    from app.adapters.store.redis_store import RedisAdapter
    store = RedisAdapter(settings.redis_url)
    persistence = AgentPersistence(store)
    
    # 2. Setup Orchestration Engine (Engine-Agnostic)
    from app.domain.enums import OrchestrationEngineType
    from app.adapters.orchestration.langgraph_factory import WorkflowFactory
    from app.adapters.orchestration.burr_factory import BurrWorkflowFactory
    from app.adapters.orchestration.langgraph_adapter import LangGraphAdapter
    from app.adapters.orchestration.burr_adapter import BurrAdapter
    
    factory_args = {
        "planner": MockPlanning(),
        "executor": executor,
        "composer": MockCompose(),
        "publisher": store,
        "registry": registry
    }
    
    if settings.orchestration_engine == OrchestrationEngineType.BURR:
        factory = BurrWorkflowFactory(**factory_args)
        engine = BurrAdapter(factory)
    else:

        factory = WorkflowFactory(**factory_args)
        engine = LangGraphAdapter(factory)
    
    agent_executor = AgentExecutor(

        engine=engine,
        persistence=persistence,
        publisher=store
    )
    
    # 2. Pre-create task
    task_id = "task-456"
    session_id = "session-456"
    from app.domain.models import AgentTask
    task = AgentTask(task_id=task_id, session_id=session_id, request_id="req-456", status=ProcessStatus.ACCEPTED)
    await store.save_task(task)
    
    # 3. Execute (Using standard LangGraph-based flow)
    await agent_executor.execute(
        session_id=session_id,
        task_id=task_id,
        message="test message",
        trace_id="tr-456"
    )
    
    # 4. Verify completion
    updated_task = await store.load_task(task_id)
    assert updated_task.status == ProcessStatus.COMPLETED
    
    # 5. Verify events in stream (Key matches Document 12)
    events = await mock_redis.xrange(f"package:subagent:events:{task_id}")
    assert len(events) > 0
    # DONE event should contain COMPLETED status
    found_completed = any("COMPLETED" in str(data) for _, data in events)
    assert found_completed
