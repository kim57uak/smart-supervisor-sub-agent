from typing import Optional
import redis.asyncio as redis
from ..core.config import settings

class RedisClient:
    """
    Independent Redis Client for Sub-agent infrastructure.
    Implements Document 03 (Component Architecture).
    """
    _instance: Optional[redis.Redis] = None

    @classmethod
    async def get_client(cls) -> redis.Redis:
        if cls._instance is None:
            cls._instance = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
        return cls._instance

    @classmethod
    async def close(cls):
        if cls._instance:
            await cls._instance.close()
            cls._instance = None


async def get_redis() -> redis.Redis:
    return await RedisClient.get_client()
