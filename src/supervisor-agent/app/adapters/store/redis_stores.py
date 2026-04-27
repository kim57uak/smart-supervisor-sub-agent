import json
from typing import Dict, Any, Optional
from redis.asyncio import Redis
from ...ports.store_ports import (
    ConversationStore,
    GraphCheckpointStore,
    SupervisorReviewStore,
    A2ATaskStore,
    ReviewedExecutionSnapshotStore
)
from ...domain.models import ReviewedExecutionSnapshot
from ...infrastructure.redis.redis_client import RedisClient


class BaseRedisStore:
    async def get_redis(self) -> Redis:
        return await RedisClient.get_client()


class RedisA2ATaskStore(BaseRedisStore, A2ATaskStore):
    def _key(self, task_id: str) -> str:
        return f"supervisor:task:{task_id}"

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        redis = await self.get_redis()
        data = await redis.hgetall(self._key(task_id))
        return data if data else None

    async def save_task(self, task_id: str, task_data: Dict[str, Any]):
        redis = await self.get_redis()
        serialized_data = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in task_data.items()}
        await redis.hset(self._key(task_id), mapping=serialized_data)


class RedisReviewedExecutionSnapshotStore(BaseRedisStore, ReviewedExecutionSnapshotStore):
    def _key(self, task_id: str) -> str:
        return f"supervisor:snapshot:{task_id}"

    async def save_snapshot(self, task_id: str, snapshot: ReviewedExecutionSnapshot, ttl: int):
        redis = await self.get_redis()
        await redis.setex(
            self._key(task_id), 
            ttl, 
            snapshot.model_dump_json()
        )

    async def get_snapshot(self, task_id: str) -> Optional[ReviewedExecutionSnapshot]:
        redis = await self.get_redis()
        data = await redis.get(self._key(task_id))
        if not data:
            return None
        return ReviewedExecutionSnapshot.model_validate_json(data)


class RedisSupervisorReviewStore(BaseRedisStore, SupervisorReviewStore):
    async def save_review(self, task_id: str, review_data: Dict[str, Any]):
        redis = await self.get_redis()
        await redis.hset(f"supervisor:review:{task_id}", mapping=review_data)


class RedisGraphCheckpointStore(BaseRedisStore, GraphCheckpointStore):
    async def save_checkpoint(self, task_id: str, checkpoint_data: Dict[str, Any]):
        redis = await self.get_redis()
        await redis.set(f"supervisor:checkpoint:{task_id}", json.dumps(checkpoint_data))


class RedisConversationStore(BaseRedisStore, ConversationStore):
    async def save_message(self, session_id: str, message: Dict[str, Any]):
        redis = await self.get_redis()
        await redis.rpush(f"supervisor:conversation:{session_id}", json.dumps(message))
