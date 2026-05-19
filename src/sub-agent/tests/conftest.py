import pytest
import asyncio
from fakeredis.aioredis import FakeRedis

import pytest_asyncio

# 세션 레벨 이벤트 루프 픽스처
# pytest-asyncio가 테스트 함수용 이벤트 루프를 생성할 수 있도록 보장한다.
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

# 모든 테스트에 자동 적용되는 Redis 모킹 픽스처
# FakeRedis로 redis.asyncio.from_url()을 전역 모킹하여
# 실제 Redis 서버 없이도 통합 테스트가 동작하도록 한다.
# 중요: 이 모킹은 main.create_app()이 호출되기 전에 적용되어야 한다.
@pytest_asyncio.fixture(autouse=True)
async def mock_redis(monkeypatch):
    fake_redis = FakeRedis(decode_responses=True)
    
    import redis.asyncio as aioredis
    monkeypatch.setattr(aioredis, "from_url", lambda *args, **kwargs: fake_redis)
    
    yield fake_redis
    await fake_redis.flushall()
    await fake_redis.close()

# FastAPI 테스트 클라이언트용 앱 픽스처
# 각 테스트마다 create_app()을 새로 호출하여 의존성 주입이 모킹된 Redis를 사용하도록 보장한다.
@pytest.fixture
def app(mock_redis):
    from main import create_app
    return create_app()
