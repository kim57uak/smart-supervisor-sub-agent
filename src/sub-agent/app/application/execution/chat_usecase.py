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
    Main Application Use Case for Sub-agent chat.
    Orchestrates the lifecycle of task execution using Decoupled Worker pattern.
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
        request_id = request_id or str(uuid.uuid4())
        # Rationale (Why): Trace ID must be propagated (Doc 02).
        trace_id = trace_id or f"tr-{uuid.uuid4().hex[:12]}"
        task_id = str(uuid.uuid4())

        log = logger.bind(trace_id=trace_id, session_id=session_id, request_id=request_id)

        # 1. Idempotency Check & Reserve (Command via Persistence)
        is_new = await self.persistence.store.check_and_reserve_idempotency(request_id, task_id)
        if not is_new:
            log.info("duplicate_request_detected")
            return {"status": "ALREADY_PROCESSED", "request_id": request_id, "trace_id": trace_id}

        # 2. Create Initial Task State
        task = AgentTask(
            task_id=task_id,
            session_id=session_id,
            request_id=request_id,
            status=ProcessStatus.ACCEPTED
        )
        await self.persistence.store.save_task(task)

        # 3. Enqueue for Worker with full context
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
