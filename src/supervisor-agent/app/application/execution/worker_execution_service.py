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
            try:
                task_msg = await self.task_queue.dequeue_task(timeout=5)
                if not task_msg:
                    continue

                await self._process_task(task_msg)
            except asyncio.CancelledError:
                logger.info("worker_loop_cancelled")
                break
            except Exception as e:
                logger.error("worker_loop_error", error=str(e))
                await asyncio.sleep(1)

    async def _process_task(self, task_msg: Dict[str, Any]):
        session_id = task_msg["session_id"]
        task_id = task_msg["task_id"]
        plan_raw = task_msg["plan_data"]

        logger.info("worker_processing_task", task_id=task_id, session_id=session_id)

        try:
            # Rationale (Why): To minimize latency, we bypass the complex LangGraph execution engine 
            # if the planner determines that a direct answer from the LLM is sufficient (no sub-agents needed).
            is_direct = plan_raw.get("planner_metadata", {}).get("direct_answer", False) or plan_raw.get("is_direct", False)
            if is_direct:
                await self.graph_execution.execute_direct_answer(session_id, task_id, plan_raw)
            else:
                # Rationale (Why): For standard multi-agent workflows, we must restore the frozen plan 
                # into a domain object before passing it to the state graph to ensure type safety.
                plan = FrozenExecutionPlan(**plan_raw) if isinstance(plan_raw, dict) and "routing_queue" in plan_raw else plan_raw
                await self.graph_execution.execute_plan(session_id, task_id, plan)
        except Exception as e:
            logger.error("task_processing_failed", task_id=task_id, error=str(e))
            await self.publisher.publish_error(session_id, task_id, {"error": str(e)})
