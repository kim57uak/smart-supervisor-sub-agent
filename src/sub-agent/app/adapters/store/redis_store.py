import json
import redis.asyncio as redis
from typing import Optional, Dict, Any
from ...ports.interfaces import Store, TaskQueue, ProgressPublisher
from ...domain.models import AgentTask
from ...domain.enums import ProcessStatus
from ...core.config import settings
import structlog

logger = structlog.get_logger(__name__)

class RedisAdapter(Store, TaskQueue, ProgressPublisher):
    """
    Unified Redis Adapter for storage, queuing, and event streaming.
    Implements Document 01 (System Context) and Document 12/16/20 (Centralized Redis Management).
    """
    def __init__(self, redis_url: str):
        self.client = redis.from_url(redis_url, decode_responses=True)
        
        # Get config from centralized settings
        agent_settings = settings.agent
        prefixes = agent_settings.redis_prefixes
        
        # Add global prefix (package)
        self.base_prefix = f"{prefixes.global_prefix}:"
        
        # Rationale (Why): Queue key must match exactly with Document 12 for multi-node compatibility.
        self.queue_key = f"{self.base_prefix}subagent:task_queue"
        self.task_prefix = f"{self.base_prefix}{prefixes.task}:"
        self.idempotency_prefix = f"{self.base_prefix}{prefixes.idempotency}:"
        self.event_stream_prefix = f"{self.base_prefix}{prefixes.events}:"
        self.ttl = agent_settings.redis_ttl

    # --- Store Implementation ---

    async def check_and_reserve_idempotency(self, request_id: str, task_id: str) -> bool:
        key = f"{self.idempotency_prefix}{request_id}"
        # Rationale (Why): SET NX ensures that only the first request is processed (Idempotency).
        result = await self.client.set(key, task_id, nx=True, ex=self.ttl)
        return bool(result)

    async def save_task(self, task: AgentTask) -> None:
        """
        Saves task state with optimistic locking (Document 20).
        """
        key = f"{self.task_prefix}{task.task_id}"
        
        async with self.client.pipeline() as pipe:
            try:
                # Rationale (Why): WATCH ensures that we don't overwrite if another worker updated it.
                await pipe.watch(key)
                
                # Check current version if exists
                current_data = await self.client.get(key)
                if current_data:
                    current_task = AgentTask.model_validate_json(current_data)
                    if task.state_version <= current_task.state_version:
                        # Version conflict
                        logger.warning("optimistic_locking_conflict", task_id=task.task_id)
                        raise ValueError("State version conflict")

                pipe.multi()
                pipe.set(key, task.model_dump_json(), ex=self.ttl)
                await pipe.execute()
                
            except redis.WatchError:
                logger.error("redis_watch_error", task_id=task.task_id)
                raise

    async def load_task(self, task_id: str) -> Optional[AgentTask]:
        key = f"{self.task_prefix}{task_id}"
        data = await self.client.get(key)
        if data:
            try:
                return AgentTask.model_validate_json(data)
            except Exception as e:
                # Rationale (Why): Debugging data migration or model mismatch issues.
                logger.error("task_validation_failed", task_id=task_id, error=str(e), data=data)
                raise
        return None

    async def update_task_status(self, task_id: str, status: ProcessStatus) -> None:
        task = await self.load_task(task_id)
        if task:
            task.status = status
            # Version is incremented in Persistence Service or Coordinator
            await self.save_task(task)

    async def save_swarm_state(self, session_id: str, state: Dict[str, Any]) -> None:
        key = f"{self.base_prefix}subagent:swarm_state:{session_id}"
        await self.client.set(key, json.dumps(state), ex=self.ttl)

    async def load_swarm_state(self, session_id: str) -> Dict[str, Any]:
        key = f"{self.base_prefix}subagent:swarm_state:{session_id}"
        data = await self.client.get(key)
        return json.loads(data) if data else {}

    async def save_message(self, session_id: str, message: Dict[str, Any]) -> None:
        key = f"{self.base_prefix}subagent:conversation:{session_id}"
        await self.client.rpush(key, json.dumps(message))
        await self.client.expire(key, self.ttl)

    async def get_messages(self, session_id: str, limit: int = 20) -> list[Dict[str, Any]]:
        key = f"{self.base_prefix}subagent:conversation:{session_id}"
        data = await self.client.lrange(key, -limit, -1)
        return [json.loads(m) for m in data]

    # --- TaskQueue Implementation ---

    async def enqueue(self, task_data: Dict[str, Any]) -> None:
        # Rationale (Why): LPUSH for FIFO processing in Worker.
        await self.client.lpush(self.queue_key, json.dumps(task_data))

    async def dequeue(self) -> Optional[Dict[str, Any]]:
        # Rationale (Why): BRPOP provides efficient blocking wait for tasks (Document 12).
        result = await self.client.brpop(self.queue_key, timeout=1)
        if result:
            _, data = result
            return json.loads(data)
        return None

    # --- ProgressPublisher Implementation ---

    async def publish(
        self, 
        session_id: str, 
        task_id: str, 
        event_data: Dict[str, Any],
        trace_id: Optional[str] = None
    ) -> None:
        # Rationale (Why): Trace ID propagation is mandatory for end-to-end auditing (Doc 02/14).
        stream_key = f"{self.event_stream_prefix}{task_id}"
        
        payload = {
            "session_id": session_id,
            "task_id": task_id,
            "trace_id": trace_id or event_data.get("trace_id", "unknown"),
            "event_type": event_data.get("event_type", "progress"),
            "payload": json.dumps(event_data.get("payload", {})),
            "is_replayable": "1" if event_data.get("is_replayable", True) else "0"
        }
                
        await self.client.xadd(stream_key, payload, maxlen=1000, approximate=True)
        # Set TTL for the event stream
        await self.client.expire(stream_key, self.ttl)
