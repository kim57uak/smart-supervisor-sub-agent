import asyncio
import structlog
from typing import Dict, Any, Optional
from .task_queue_service import TaskQueueService
from .supervisor_graph_execution_service import SupervisorGraphExecutionService
from .supervisor_progress_publisher import SupervisorProgressPublisher
from ...domain.models import FrozenExecutionPlan

logger = structlog.get_logger()

class WorkerExecutionService:
    """
    Background worker that dequeues tasks from Redis and executes them.
    Single Responsibility: Task dispatching and loop management.
    """
    def __init__(
        self,
        task_queue: TaskQueueService,
        graph_execution: SupervisorGraphExecutionService,
        publisher: SupervisorProgressPublisher
    ):
        self.task_queue = task_queue
        self.graph_execution = graph_execution
        self.publisher = publisher

    async def run_forever(self):
        logger.info("worker_loop_started", queue=self.task_queue.queue_key)
        while True:
            task_msg = None
            try:
                # Rationale (Why): Reliable dequeue moves task to a 'processing' list atomically.
                task_msg = await self.task_queue.dequeue_task(timeout=5)
                if not task_msg:
                    continue

                await self._process_task(task_msg)
                
                # Rationale (Why): Explicit ACK removes the task from the 'processing' queue after success.
                await self.task_queue.ack_task(task_msg)
                
            except asyncio.CancelledError:
                logger.info("worker_loop_cancelled")
                break
            except Exception as e:
                logger.error("worker_loop_error", error=str(e))
                if task_msg:
                    # Rationale (Why): NACK moves the task back to the main queue for retry (At-Least-Once guarantee).
                    await self.task_queue.nack_task(task_msg)
                await asyncio.sleep(1)

    async def _process_task(self, task_msg: Dict[str, Any]):
        """
        Internal processing logic. Exceptions here trigger NACK in the main loop.
        """
        session_id = task_msg["session_id"]
        task_id = task_msg["task_id"]
        plan_raw = task_msg["plan_data"]

        logger.info("worker_processing_task", task_id=task_id, session_id=session_id)

        # Rationale (Why): Minimalist check to branch between direct LLM response and full agentic workflow.
        is_direct = plan_raw.get("planner_metadata", {}).get("direct_answer", False) or plan_raw.get("is_direct", False)
        
        if is_direct:
            await self.graph_execution.execute_direct_answer(session_id, task_id, plan_raw)
        else:
            # Rationale (Why): Reconstruct domain object to ensure type safety during Burr/LangGraph execution.
            plan = FrozenExecutionPlan(**plan_raw) if isinstance(plan_raw, dict) and "routing_queue" in plan_raw else plan_raw
            await self.graph_execution.execute_plan(session_id, task_id, plan)
