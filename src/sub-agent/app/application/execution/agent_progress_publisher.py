import json
import structlog
from typing import Dict, Any, Optional
from ...ports.interfaces import ProgressPublisherPort
from ...adapters.store.redis_store import RedisAdapter

logger = structlog.get_logger(__name__)

class AgentProgressPublisher(ProgressPublisherPort):
    """
    Publishes progress events to Redis Stream.
    Follows Document 01 (System Context) and Document 31 (Supervisor Event Schema).
    Ensures mandatory Trace ID propagation (Document 02).
    """
    def __init__(self, redis_adapter: RedisAdapter):
        self.redis = redis_adapter

    async def publish(
        self, 
        session_id: str, 
        task_id: str, 
        event_data: Dict[str, Any],
        trace_id: Optional[str] = None
    ) -> None:
        # Canonical event structure for SSE compatibility
        # Rationale (Why): Trace ID must be propagated to allow end-to-end audit (Doc 02).
        payload = {
            "session_id": session_id,
            "task_id": task_id,
            "trace_id": trace_id or event_data.get("trace_id", "unknown"),
            "event_type": event_data.get("event_type", "progress"),
            "payload": event_data.get("payload", {}),
            "is_replayable": event_data.get("is_replayable", True)
        }
        
        # Publish to Redis Stream (event_stream in Doc 01)
        stream_key = f"package:subagent:session:{session_id}:task:events:{task_id}"
        await self.redis.redis.xadd(stream_key, {"data": json.dumps(payload)})
        
        # Set TTL for the event stream
        await self.redis.redis.expire(stream_key, 1800)
        
        logger.debug("event_published", task_id=task_id, event_type=payload["event_type"], trace_id=payload["trace_id"])
