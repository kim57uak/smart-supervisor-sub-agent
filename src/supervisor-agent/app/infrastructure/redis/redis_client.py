from typing import Optional
import redis.asyncio as redis
from ...core.config import settings

class RedisClient:
    _instance: Optional[redis.Redis] = None

    @classmethod
    async def get_client(cls) -> redis.Redis:
        if cls._instance is None:
            # Rationale (Why): Explicitly managing connection pool prevents exhaustion in high-traffic scenarios.
            cls._instance = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20, # Managed pool size
                socket_timeout=20.0, # Rationale (Why): Must be greater than blocking command timeouts (e.g. 10s in dequeue)
                socket_connect_timeout=10.0,
                health_check_interval=30 # Keep-alive check
            )
        return cls._instance

    @classmethod
    async def close(cls):
        if cls._instance:
            await cls._instance.close()
            cls._instance = None


async def get_redis() -> redis.Redis:
    return await RedisClient.get_client()
