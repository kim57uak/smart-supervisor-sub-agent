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

    async def _resolve_session_id(self, session_id: Optional[str], task_id: str) -> str:
        """
        If session_id is missing or 'unknown', tries to find it using task_id index.
        """
        if session_id and session_id != "unknown":
            return session_id
            
        redis = await self._get_redis()
        # Try to find session_id from task-to-session index
        idx_key = f"{settings.redis_prefix}:supervisor:index:task_session:{task_id}"
        resolved = await redis.get(idx_key)
        if resolved:
            return resolved.decode() if isinstance(resolved, bytes) else resolved
            
        return "unknown"

    def _get_stream_key(self, session_id: str, task_id: str) -> str:
        return f"{settings.redis_prefix}:supervisor:session:{session_id}:task:events:{task_id}"

    async def append_event(
        self, 
        session_id: str,
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
        stream_key = self._get_stream_key(session_id, task_id)
        
        event_data = {
            "task_id": task_id,
            "session_id": session_id,
            "event_type": event_type.value,
            "payload": json.dumps(payload),
            "created_at": datetime.utcnow().isoformat(),
            "is_replayable": "1" if is_replayable else "0"
        }
        
        # XADD returns the message ID which serves as our cursor
        cursor = await redis.xadd(stream_key, event_data)
        
        # Save task-to-session index for backward compatibility and easier lookup
        idx_key = f"{settings.redis_prefix}:supervisor:index:task_session:{task_id}"
        await redis.set(idx_key, session_id, ex=settings.redis_ttl_seconds)
        
        # Ensure the stream has a TTL
        await redis.expire(stream_key, settings.redis_ttl_seconds)
        
        return cursor

    async def get_initial_cursor(self, session_id: str, task_id: str) -> str:
        """
        Returns the current tail of the stream to be used as initial_cursor.
        """
        redis = await self._get_redis()
        session_id = await self._resolve_session_id(session_id, task_id)
        stream_key = self._get_stream_key(session_id, task_id)
        
        last_events = await redis.xrevrange(stream_key, count=1)
        if last_events:
            return last_events[0][0]
        return "0-0"

    async def subscribe(
        self, 
        session_id: str,
        task_id: str, 
        last_cursor: Optional[str] = None,
        replay: bool = True
    ) -> AsyncIterator[SupervisorTaskEvent]:
        """
        Subscribes to the event stream from a given cursor.
        If replay=False, ignores last_cursor and starts from current tail (live only).
        """
        redis = await self._get_redis()
        session_id = await self._resolve_session_id(session_id, task_id)
        stream_key = self._get_stream_key(session_id, task_id)
        
        # If not replaying, we start from the current end of the stream
        if not replay:
            cursor = "$" # Redis special ID for "new messages only"
        else:
            # Check if cursor is expired
            if last_cursor and last_cursor not in ("0", "0-0"):
                oldest_events = await redis.xrange(stream_key, min="-", max="+", count=1)
                if oldest_events:
                    oldest_cursor = oldest_events[0][0]
                    
                    def parse_cursor(c: str) -> tuple:
                        parts = c.split('-')
                        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
                    
                    if parse_cursor(last_cursor) < parse_cursor(oldest_cursor):
                        raise ValueError("CURSOR_EXPIRED")
            
            cursor = last_cursor or "0-0"
        
        while True:
            streams = await redis.xread({stream_key: cursor}, count=10, block=5000)
            if not streams:
                continue
            
            for stream_name, events in streams:
                for event_id, event_dict in events:
                    cursor = event_id
                    
                    # Even in replay mode, we can skip non-replayable events if defined in payload
                    # But per doc 31, core events (chunk, a2ui, done, error) must be replayed
                    yield SupervisorTaskEvent(
                        task_id=task_id,
                        event_id=event_id,
                        cursor=event_id,
                        event_type=event_dict["event_type"],
                        created_at=datetime.fromisoformat(event_dict["created_at"]),
                        payload=json.loads(event_dict["payload"]),
                        is_replayable=event_dict["is_replayable"] == "1"
                    )
                    
                    if event_dict["event_type"] in [EventType.DONE.value, EventType.ERROR.value]:
                        return
