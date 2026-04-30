import pytest
import asyncio
from fakeredis.aioredis import FakeRedis

import pytest_asyncio

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(autouse=True)
async def mock_redis(monkeypatch):
    fake_redis = FakeRedis(decode_responses=True)
    
    # Mock redis.asyncio.from_url globally
    import redis.asyncio as aioredis
    monkeypatch.setattr(aioredis, "from_url", lambda *args, **kwargs: fake_redis)
    
    # We must ensure this mock is applied BEFORE main.create_app is called
    # But main is usually imported at module level in tests
    
    yield fake_redis
    await fake_redis.flushall()
    await fake_redis.close()

@pytest.fixture
def app(mock_redis):
    # Re-create app for each test to ensure dependencies use mocked redis
    from main import create_app
    return create_app()
