"""
[Sub-Agent] 채팅 요청 Use Case — Decoupled Worker 패턴
=======================================================
책임: 채팅 요청을 수신하여 Idempotency 검증 → Task 생성 → Worker 큐잉
아키텍처 위치: Application Layer — Use Case (Inbound Port 구현)

처리 흐름 (202 Accepted):
  1. Idempotency Check (SET NX) — 중복 요청이면 즉시 ALREADY_PROCESSED 반환
  2. AgentTask 생성 (status=ACCEPTED) → Redis 저장
  3. TaskQueue enqueue → Worker가 비동기 처리
  4. 202 Accepted 응답 + task_id 반환

Trace ID 전파:
  - request_id: Idempotency 키로 사용
  - trace_id: OpenTelemetry 추적용, UI/요청에서 제공받거나 자동 생성
  - 모든 로그에 trace_id/session_id/request_id 바인딩
"""

import uuid
import structlog
from typing import Dict, Any, Optional
from app.domain.enums import ProcessStatus
from app.domain.models import AgentTask
from app.ports.interfaces import TaskQueue
from app.application.persistence.agent_persistence import AgentPersistence

logger = structlog.get_logger(__name__)

class AgentChatUseCase:
    """
    서브에이전트 채팅의 메인 Use Case.
    외부 요청 → Idempotency → Task 생성 → Worker Queue → 202 Accepted.
    """
    def __init__(self, persistence: AgentPersistence, queue: TaskQueue):
        self.persistence = persistence
        self.queue = queue

    async def handle_chat_request(
        self, 
        session_id: str, 
        message: str, 
        request_id: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """채팅 요청 처리: Idempotency → Task 생성 → Queue → 202"""
        request_id = request_id or str(uuid.uuid4())
        trace_id = trace_id or f"tr-{uuid.uuid4().hex[:12]}"
        task_id = str(uuid.uuid4())

        log = logger.bind(trace_id=trace_id, session_id=session_id, request_id=request_id)

        # 1. Idempotency (중복 요청 차단)
        is_new = await self.persistence.store.check_and_reserve_idempotency(request_id, task_id)
        if not is_new:
            log.info("duplicate_request_detected")
            return {"status": "ALREADY_PROCESSED", "request_id": request_id, "trace_id": trace_id}

        # 2. 초기 태스크 상태 생성 (ACCEPTED)
        task = AgentTask(
            task_id=task_id,
            session_id=session_id,
            request_id=request_id,
            status=ProcessStatus.ACCEPTED
        )
        await self.persistence.store.save_task(task)

        # 3. Worker Queue에 등록
        await self.queue.enqueue({
            "task_id": task_id,
            "session_id": session_id,
            "trace_id": trace_id,
            "message": message,
            "request_id": request_id
        })

        log.info("task_accepted", task_id=task_id)

        return {
            "task_id": task_id,
            "status": ProcessStatus.ACCEPTED.value,
            "trace_id": trace_id,
            "stream_url": f"/api/v1/stream/{task_id}"
        }
