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
            try:
                task_msg = await self.task_queue.dequeue()
                if not task_msg:
                    await asyncio.sleep(1)
                    continue

                await self._process_task(task_msg)
            except Exception as e:
                logger.error("worker_loop_error", error=str(e))
                await asyncio.sleep(1)

    async def _process_task(self, task_msg: Dict[str, Any]):
        session_id = task_msg.get("session_id")
        task_id = task_msg.get("task_id")
        message = task_msg.get("message")
        trace_id = task_msg.get("trace_id", "unknown")
        
        logger.info("processing_task", task_id=task_id, session_id=session_id, trace_id=trace_id)
        
        try:
            await self.executor.execute(session_id, task_id, message, trace_id=trace_id)
        except Exception as e:
            logger.error("task_execution_failed", task_id=task_id, error=str(e))
            await self.publisher.publish(session_id, task_id, {
                "event_type": "error",
                "payload": {"error": str(e)}
            }, trace_id=trace_id)
