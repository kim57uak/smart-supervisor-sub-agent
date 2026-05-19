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

    async def mark_resume_token_used(self, session_id: str, task_id: str, resume_token: str) -> bool:
        """Mark a resume token as used to prevent replay attacks."""
        redis = await self.get_redis()
        token_key = self._get_base_key(f"supervisor:session:{session_id}:resume_token:{resume_token}")
        # Use SETNX to atomically check-and-set
        is_new = await redis.setnx(token_key, "used")
        if is_new:
            await redis.expire(token_key, 86400)  # Expire after 24 hours
            return False  # Token was not previously used
        return True  # Token was already used


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
        await redis.expire(key, settings.redis_ttl_seconds)

    async def get_checkpoint(self, session_id: str, task_id: str) -> Optional[Dict[str, Any]]:
        redis = await self.get_redis()
        key = self._get_base_key(f"supervisor:session:{session_id}:checkpoint:{task_id}")
        data = await redis.get(key)
        return json.loads(data) if data else None


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
    Persists SwarmState (agent shared memory) to Redis with CAS (Doc 03, 29).
    Uses versioned writes to prevent lost-update race conditions.
    """
    def _key(self, session_id: str) -> str:
        return self._get_base_key(f"supervisor:session:{session_id}:swarm_state")

    def _ver_key(self, session_id: str) -> str:
        return self._get_base_key(f"supervisor:session:{session_id}:swarm_state:ver")

    async def save_swarm_state(self, session_id: str, swarm_state: Dict[str, Any], expected_version: Optional[int] = None):
        redis = await self.get_redis()
        data_key = self._key(session_id)
        ver_key = self._ver_key(session_id)

        if expected_version is not None:
            async with redis.pipeline(transaction=True) as pipe:
                while True:
                    await pipe.watch(ver_key)
                    current_ver = await pipe.get(ver_key)
                    current_ver = int(current_ver) if current_ver is not None else 0
                    if current_ver != expected_version:
                        raise ValueError(
                            f"SwarmState version mismatch: expected {expected_version}, got {current_ver}"
                        )
                    pipe.multi()
                    pipe.set(data_key, json.dumps(swarm_state))
                    pipe.expire(data_key, settings.redis_ttl_seconds)
                    pipe.set(ver_key, current_ver + 1)
                    pipe.expire(ver_key, settings.redis_ttl_seconds)
                    await pipe.execute()
                    return
        else:
            await redis.set(data_key, json.dumps(swarm_state))
            await redis.expire(data_key, settings.redis_ttl_seconds)
            await redis.set(ver_key, 1)
            await redis.expire(ver_key, settings.redis_ttl_seconds)

    async def get_swarm_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        redis = await self.get_redis()
        data = await redis.get(self._key(session_id))
        return json.loads(data) if data else None

    async def get_swarm_state_with_version(self, session_id: str):
        redis = await self.get_redis()
        async with redis.pipeline(transaction=True) as pipe:
            pipe.get(self._key(session_id))
            pipe.get(self._ver_key(session_id))
            data, ver = await pipe.execute()
        state = json.loads(data) if data else {}
        version = int(ver) if ver is not None else 0
        return state, version

    async def delete_swarm_state(self, session_id: str):
        redis = await self.get_redis()
        await redis.delete(self._key(session_id), self._ver_key(session_id))
