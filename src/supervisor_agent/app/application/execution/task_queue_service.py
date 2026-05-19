import json
import asyncio
from typing import Dict, Any, Optional
from redis.asyncio import Redis
from ...infrastructure.redis.redis_client import get_redis
import structlog

logger = structlog.get_logger()

from ...core.config import settings

class TaskQueueService:
    """
    Enterprise Task Queue Service with Reliable Queue Pattern (Doc 01).
    Ensures At-Least-Once delivery by moving tasks to a processing queue.
    """
    def __init__(self, redis: Optional[Redis] = None):
        self.redis = redis
        self.queue_key = f"{settings.redis_prefix}:supervisor:task_queue"
        self.processing_key = f"{settings.redis_prefix}:supervisor:task_processing"

    async def _get_redis(self) -> Redis:
        if self.redis:
            return self.redis
        return await get_redis()

    async def enqueue_task(self, session_id: str, task_id: str, plan_data: Dict[str, Any]):
        redis = await self._get_redis()
        payload = {
            "session_id": session_id,
            "task_id": task_id,
            "plan_data": plan_data
        }
        await redis.lpush(self.queue_key, json.dumps(payload))
        logger.info("task_enqueued", task_id=task_id, queue=self.queue_key)

    async def dequeue_task(self, timeout: int = 10) -> Optional[Dict[str, Any]]:
        """
        Pops a task reliably using LMOVE or RPOPLPUSH.
        Moves from main queue to processing queue atomically.
        """
        redis = await self._get_redis()
        
        # Use LMOVE (Redis 6.2+) or RPOPLPUSH (Older) for reliability
        # Here we use BRPOPLPUSH for blocking reliable pop
        result = await redis.brpoplpush(self.queue_key, self.processing_key, timeout=timeout)
        
        if result:
            return json.loads(result)
        return None

    async def ack_task(self, task_msg: Dict[str, Any]):
        """
        Removes task from processing queue after successful execution.
        """
        redis = await self._get_redis()
        # Remove exactly this message from the processing queue
        await redis.lrem(self.processing_key, 1, json.dumps(task_msg))
        logger.debug("task_acknowledged", task_id=task_msg.get("task_id"))

    async def nack_task(self, task_msg: Dict[str, Any]):
        """
        Moves task back to main queue if processing fails (Retry).
        """
        redis = await self._get_redis()
        msg_json = json.dumps(task_msg)
        async with redis.pipeline() as pipe:
            await pipe.lrem(self.processing_key, 1, msg_json)
            await pipe.lpush(self.queue_key, msg_json)
            await pipe.execute()
        logger.warning("task_nack_requeued", task_id=task_msg.get("task_id"))
