"""
[Sub-Agent] Redis 클라이언트 싱글톤
====================================
책임: 애플리케이션 전역에서 사용할 단일 Redis 연결 관리
아키텍처 위치: Infrastructure Layer — Redis Connection

싱글톤 패턴:
  - get_client() → 최초 호출 시 연결 생성, 이후 재사용
  - close() → 애플리케이션 종료 시 연결 정리 (lifespan에서 호출)

주의:
  - decode_responses=True로 모든 응답 자변 디코딩
  - 연결 실패 시 재시도 로직 없음 → Redis transient failure 대비 필요
  - Uvicorn 멀티워커 환경에서 각 워커가 별도 연결 가짐
"""

from typing import Optional
import redis.asyncio as redis
from ..core.config import settings

class RedisClient:
    """
    Redis 클라이언트 싱글톤.
    애플리케이션 생명주기와 함께 시작/종료.
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
