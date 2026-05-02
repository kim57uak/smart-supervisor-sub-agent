import pytest
import asyncio
from fakeredis.aioredis import FakeRedis
from app.infrastructure.redis.redis_client import RedisClient
from app.core.dependencies import get_redis

import pytest_asyncio

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(autouse=True)
async def mock_redis(monkeypatch):
    fake_redis = FakeRedis(decode_responses=True)
    
    # Mock RedisClient._instance
    RedisClient._instance = fake_redis
    
    # Override FastAPI dependency
    from app.main import app
    app.dependency_overrides[get_redis] = lambda: fake_redis
    
    # Mock Active Agents for Drift Policy
    from app.adapters.llm.llm_planning_service import LlmPlanningService
    monkeypatch.setattr(
        LlmPlanningService, 
        "get_active_agent_keys", 
        lambda self: ["sub-agent", "other-agent"]
    )
    
    yield fake_redis
    await fake_redis.flushall()
    await fake_redis.close()
