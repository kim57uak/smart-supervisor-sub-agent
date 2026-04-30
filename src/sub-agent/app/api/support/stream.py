import asyncio
import json
import structlog
from typing import AsyncIterator
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from ...core.dependencies import get_redis_adapter
from ...adapters.store.redis_store import RedisAdapter
from ...domain.enums import EventType

router = APIRouter()
logger = structlog.get_logger(__name__)

@router.get("/{task_id}")
async def stream_task_events(
    task_id: str,
    redis_adapter: RedisAdapter = Depends(get_redis_adapter)
):
    """
    SSE endpoint to stream task events from Redis.
    Implements Document 09 (Streaming Response Sequence).
    """
    stream_key = f"{redis_adapter.event_stream_prefix}{task_id}"
    
    async def event_generator() -> AsyncIterator[str]:
        last_id = "0"
        logger.info("sse_stream_started", task_id=task_id)
        
        try:
            while True:
                # Rationale (Why): XREAD with blocking wait allows efficient SSE streaming.
                events = await redis_adapter.client.xread({stream_key: last_id}, count=10, block=5000)
                
                if not events:
                    # Heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
                    continue

                for _, stream_events in events:
                    for event_id, event_data in stream_events:
                        last_id = event_id
                        
                        # Forward the event as SSE
                        # Document 09: SSE event: data: { ... }
                        yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                        
                        # Terminate stream if task is done or failed
                        if event_data.get("event_type") in [EventType.DONE.value, EventType.ERROR.value]:
                            logger.info("sse_stream_completed", task_id=task_id, type=event_data.get("event_type"))
                            return

                await asyncio.sleep(0.1)
                
        except Exception as e:
            logger.error("sse_stream_error", task_id=task_id, error=str(e))
            yield f"data: {json.dumps({'event_type': 'error', 'payload': {'error': str(e)}})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
