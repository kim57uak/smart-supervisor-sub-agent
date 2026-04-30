import json
from typing import Dict, Any, Optional
from redis.asyncio import Redis
from ...ports.store_ports import (
    ConversationStore,
    GraphCheckpointStore,
    ReviewStore,
    TaskStore,
    ExecutionSnapshotStore,
    SwarmStateStore
)
from ...domain.models import ReviewedExecutionSnapshot
from ...infrastructure.redis.redis_client import RedisClient
from ...core.config import settings


class BaseRedisStore:
    async def get_redis(self) -> Redis:
        return await RedisClient.get_client()

    def _get_base_key(self, suffix: str) -> str:
        # Rationale (Why): Consistent use of global prefix 'package' from settings.
        return f"{settings.redis.prefix}:{suffix}"


class RedisTaskStore(BaseRedisStore, TaskStore):
    def _key(self, session_id: str, task_id: str) -> str:
        return self._get_base_key(f"supervisor:session:{session_id}:task:{task_id}")

    async def get_task(self, session_id: str, task_id: str) -> Optional[Dict[str, Any]]:
        redis = await self.get_redis()
        data = await redis.hgetall(self._key(session_id, task_id))
        return data if data else None

    async def save_task(self, session_id: str, task_id: str, task_data: Dict[str, Any]):
        redis = await self.get_redis()
        serialized_data = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in task_data.items()}
        await redis.hset(self._key(session_id, task_id), mapping=serialized_data)


class RedisExecutionSnapshotStore(BaseRedisStore, ExecutionSnapshotStore):
    def _key(self, session_id: str, task_id: str) -> str:
        return self._get_base_key(f"supervisor:session:{session_id}:snapshot:{task_id}")

    async def save_snapshot(self, session_id: str, task_id: str, snapshot: ReviewedExecutionSnapshot, ttl: int):
        redis = await self.get_redis()
        await redis.setex(
            self._key(session_id, task_id), 
            ttl, 
            snapshot.model_dump_json()
        )

    async def get_snapshot(self, session_id: str, task_id: str) -> Optional[ReviewedExecutionSnapshot]:
        redis = await self.get_redis()
        data = await redis.get(self._key(session_id, task_id))
        if not data:
            return None
        return ReviewedExecutionSnapshot.model_validate_json(data)


class RedisReviewStore(BaseRedisStore, ReviewStore):
    async def save_review(self, session_id: str, task_id: str, review_data: Dict[str, Any]):
        redis = await self.get_redis()
        key = self._get_base_key(f"supervisor:session:{session_id}:review:{task_id}")
        await redis.hset(key, mapping=review_data)


class RedisGraphCheckpointStore(BaseRedisStore, GraphCheckpointStore):
    async def save_checkpoint(self, session_id: str, task_id: str, checkpoint_data: Dict[str, Any]):
        redis = await self.get_redis()
        key = self._get_base_key(f"supervisor:session:{session_id}:checkpoint:{task_id}")
        await redis.set(key, json.dumps(checkpoint_data))


class RedisConversationStore(BaseRedisStore, ConversationStore):
    async def save_message(self, session_id: str, message: Dict[str, Any]):
        redis = await self.get_redis()
        key = self._get_base_key(f"supervisor:conversation:{session_id}")
        await redis.rpush(key, json.dumps(message))

    async def get_messages(self, session_id: str, limit: int = 20) -> list[Dict[str, Any]]:
        redis = await self.get_redis()
        key = self._get_base_key(f"supervisor:conversation:{session_id}")
        data = await redis.lrange(key, -limit, -1)
        return [json.loads(m) for m in data]

    async def delete_messages(self, session_id: str):
        redis = await self.get_redis()
        key = self._get_base_key(f"supervisor:conversation:{session_id}")
        await redis.delete(key)


class RedisSwarmStateStore(BaseRedisStore, SwarmStateStore):
    """
    Persists SwarmState (agent shared memory) to Redis (Doc 03).
    """
    def _key(self, session_id: str) -> str:
        return self._get_base_key(f"supervisor:session:{session_id}:swarm_state")

    async def save_swarm_state(self, session_id: str, swarm_state: Dict[str, Any]):
        redis = await self.get_redis()
        await redis.set(self._key(session_id), json.dumps(swarm_state))
        await redis.expire(self._key(session_id), settings.redis_ttl_seconds)

    async def get_swarm_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        redis = await self.get_redis()
        data = await redis.get(self._key(session_id))
        return json.loads(data) if data else None

    async def delete_swarm_state(self, session_id: str):
        redis = await self.get_redis()
        await redis.delete(self._key(session_id))
