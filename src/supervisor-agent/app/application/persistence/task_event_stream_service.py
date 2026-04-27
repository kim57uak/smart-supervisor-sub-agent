import json
from datetime import datetime
from typing import List, Optional, Dict, Any, AsyncIterator
from redis.asyncio import Redis
from ...domain.models import SupervisorTaskEvent
from ...domain.enums import EventType
from ...infrastructure.redis.redis_client import get_redis
from ...core.config import settings


class TaskEventStreamService:
    def __init__(self, redis: Optional[Redis] = None):
        self.redis = redis

    async def _get_redis(self) -> Redis:
        if self.redis:
            return self.redis
        return await get_redis()

    def _get_stream_key(self, task_id: str) -> str:
        return f"supervisor:task:events:{task_id}"

    async def append_event(
        self, 
        task_id: str, 
        event_type: EventType, 
        payload: Dict[str, Any],
        is_replayable: bool = True
    ) -> str:
        """
        Appends an event to the task's durable event log (Redis Stream).
        Returns the cursor (Redis Stream ID).
        """
        redis = await self._get_redis()
        stream_key = self._get_stream_key(task_id)
        
        event_data = {
            "task_id": task_id,
            "event_type": event_type.value,
            "payload": json.dumps(payload),
            "created_at": datetime.utcnow().isoformat(),
            "is_replayable": "1" if is_replayable else "0"
        }
        
        # XADD returns the message ID which serves as our cursor
        cursor = await redis.xadd(stream_key, event_data)
        
        # Ensure the stream has a TTL (though Redis Streams don't have direct TTL per key easily with XADD, 
        # we can set it on the key if it's the first time or every time)
        await redis.expire(stream_key, settings.redis_ttl_seconds)
        
        return cursor

    async def get_initial_cursor(self, task_id: str) -> str:
        """
        Returns the current tail of the stream to be used as initial_cursor.
        """
        redis = await self._get_redis()
        stream_key = self._get_stream_key(task_id)
        
        # XINFO or just XREVRANGE to get the last ID
        last_events = await redis.xrevrange(stream_key, count=1)
        if last_events:
            return last_events[0][0]
        return "0-0" # Beginning of time if no events yet

    async def subscribe(
        self, 
        task_id: str, 
        last_cursor: Optional[str] = None
    ) -> AsyncIterator[SupervisorTaskEvent]:
        """
        Subscribes to the event stream from a given cursor.
        """
        redis = await self._get_redis()
        stream_key = self._get_stream_key(task_id)
        
        # If no cursor provided, start from the beginning or live?
        # Usually for replay we start from last_cursor or '0'
        cursor = last_cursor or "0-0"
        
        while True:
            # XREAD with blocking
            streams = await redis.xread({stream_key: cursor}, count=10, block=5000)
            if not streams:
                # We can yield a heartbeat or just continue
                continue
            
            for stream_name, events in streams:
                for event_id, event_dict in events:
                    cursor = event_id
                    yield SupervisorTaskEvent(
                        task_id=task_id,
                        event_id=event_id,
                        cursor=event_id,
                        event_type=event_dict["event_type"],
                        created_at=datetime.fromisoformat(event_dict["created_at"]),
                        payload=json.loads(event_dict["payload"]),
                        is_replayable=event_dict["is_replayable"] == "1"
                    )
                    
                    # If it's a terminal event, stop the subscription
                    if event_dict["event_type"] in [EventType.DONE.value, EventType.ERROR.value]:
                        return
