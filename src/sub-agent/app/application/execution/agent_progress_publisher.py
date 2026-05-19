"""
[Sub-Agent] 진행 이벤트 발행기 — Redis Stream 기반 SSE
=======================================================
책임: 에이전트 실행 상태/진행률을 Redis Stream에 발행하여 Supervisor/UI에 전달
아키텍처 위치: Application Layer — Execution (ProgressPublisher Port 구현)

이벤트 흐름:
  AgentExecutor.execute() → Publisher.publish() → Redis Stream
  → SSE endpoint(stream.py) → Supervisor SSE 연결 → UI 업데이트

이벤트 타입 (EventType):
  PROGRESS → PLANNING → EXECUTING_TOOL → TOOL_RESULT → COMPOSING → CHUNK → DONE/ERROR

참고: RedisAdapter(redis_store.py)에도 publish()가 동일한 역할로 구현되어 있음.
      이 구현은 독립적인 publish 전용 클래스로, 공통화 검토 필요.
"""

import json
import structlog
from typing import Dict, Any, Optional
from ...ports.interfaces import ProgressPublisher
from ...adapters.store.redis_store import RedisAdapter

logger = structlog.get_logger(__name__)

class AgentProgressPublisher(ProgressPublisher):
    """
    Redis Stream을 통한 진행 이벤트 발행.
    SSE 호환 구조로 payload를 JSON 직렬화하여 저장.
    TTL 1800초(30분) 자동 설정.
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
        """이벤트를 Redis Stream에 발행 (SSE 호환)"""
        payload = {
            "session_id": session_id,
            "task_id": task_id,
            "trace_id": trace_id or event_data.get("trace_id", "unknown"),
            "event_type": event_data.get("event_type", "progress"),
            "payload": event_data.get("payload", {}),
            "is_replayable": event_data.get("is_replayable", True)
        }
        
        stream_key = f"package:subagent:session:{session_id}:task:events:{task_id}"
        await self.redis.redis.xadd(stream_key, {"data": json.dumps(payload)})
        await self.redis.redis.expire(stream_key, 1800)
        
        logger.debug("event_published", task_id=task_id, event_type=payload["event_type"], trace_id=payload["trace_id"])
