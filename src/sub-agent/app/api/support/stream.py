"""
[Sub-Agent] SSE(Server-Sent Events) 스트리밍 엔드포인트
=========================================================
책임: Redis Stream에 발행된 태스크 이벤트를 SSE로 실시간 스트리밍
아키텍처 위치: API Layer — Streaming (Inbound Adapter)

동작 방식:
  1. 클라이언트가 GET /api/v1/stream/{task_id} 연결
  2. XREAD blocking으로 Redis Stream 폴링 (5초 타임아웃)
  3. 새 이벤트 발생 시 SSE data: 포맷으로 전달
  4. DONE/ERROR 이벤트 수신 시 스트림 종료

SSE 이벤트 흐름:
  : heartbeat (keepalive, 5초 간격)
  data: {"event_type": "PROGRESS", "payload": {...}}
  data: {"event_type": "PLANNING", ...}
  data: {"event_type": "CHUNK", "payload": {"answer": "..."}}
  data: {"event_type": "DONE", ...}  → 스트림 종료

주의:
  - 긴 연결 유지를 위한 heartbeat 필수
  - 클라이언트 연결 종료 시 asyncio task 정리 필요 (FastAPI 자동 처리)
"""

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
    태스크 실행 이벤트를 SSE로 실시간 스트리밍.
    XREAD blocking poll + heartbeat 패턴 사용.
    """
    stream_key = f"{redis_adapter.event_stream_prefix}{task_id}"
    
    async def event_generator() -> AsyncIterator[str]:
        last_id = "0"
        logger.info("sse_stream_started", task_id=task_id)
        
        try:
            while True:
                events = await redis_adapter.client.xread({stream_key: last_id}, count=10, block=5000)
                
                if not events:
                    yield ": heartbeat\n\n"
                    continue

                for _, stream_events in events:
                    for event_id, event_data in stream_events:
                        last_id = event_id
                        yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                        
                        if event_data.get("event_type") in [EventType.DONE.value, EventType.ERROR.value]:
                            logger.info("sse_stream_completed", task_id=task_id, type=event_data.get("event_type"))
                            return

                await asyncio.sleep(0.1)
                
        except Exception as e:
            logger.error("sse_stream_error", task_id=task_id, error=str(e))
            yield f"data: {json.dumps({'event_type': 'error', 'payload': {'error': str(e)}})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
