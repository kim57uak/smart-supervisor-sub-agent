import asyncio
import structlog
from typing import Dict, Any
from .executor import AgentExecutor
from ...ports.interfaces import ProgressPublisher, TaskQueue

logger = structlog.get_logger(__name__)

class WorkerExecutionService:
    """
    Background worker for sub-agent.
    """
    def __init__(
        self,
        task_queue: TaskQueue,
        executor: AgentExecutor,
        publisher: ProgressPublisher
    ):
        self.task_queue = task_queue
        self.executor = executor
        self.publisher = publisher

    async def run_forever(self):
        logger.info("subagent_worker_started")
        while True:
            task_msg = None
            try:
                # Rationale (Why): Reliable dequeue ensures task is moved to a 'processing' list (Doc 01).
                task_msg = await self.task_queue.dequeue(timeout=5)
                if not task_msg:
                    continue

                await self._process_task(task_msg)
                
                # Rationale (Why): Confirm task completion to remove from Redis.
                await self.task_queue.ack(task_msg)
                
            except Exception as e:
                logger.error("worker_loop_error", error=str(e))
                if task_msg:
                    # Rationale (Why): NACK ensures task is requeued for retry (At-Least-Once).
                    await self.task_queue.nack(task_msg)
                await asyncio.sleep(1)

    async def _process_task(self, task_msg: Dict[str, Any]):
        """
        Internal processing logic. Exceptions here trigger NACK in the main loop.
        """
        session_id = task_msg.get("session_id")
        task_id = task_msg.get("task_id")
        message = task_msg.get("message")
        trace_id = task_msg.get("trace_id", "unknown")
        
        logger.info("processing_task", task_id=task_id, session_id=session_id, trace_id=trace_id)
        
        # Rationale (Why): Directly execute the agent workflow. 
        # Any failure here is handled by the outer loop's NACK logic.
        await self.executor.execute(session_id, task_id, message, trace_id=trace_id)
