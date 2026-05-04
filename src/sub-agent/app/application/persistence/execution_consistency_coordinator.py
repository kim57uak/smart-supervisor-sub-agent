import asyncio
import structlog
from typing import Optional, Dict, Any, Callable, Awaitable
from app.ports.interfaces import Store
from app.domain.models import AgentTask
from app.domain.enums import ProcessStatus

logger = structlog.get_logger(__name__)

class ExecutionConsistencyCoordinator:
    """
    Ensures atomic state transitions using Redis CAS (Check-And-Set) pattern.
    Aligned with Host Agent architecture (Document 29).
    """
    def __init__(self, store: Store):
        self.store = store

    async def atomic_transition(
        self, 
        task_id: str, 
        target_status: ProcessStatus,
        update_fn: Optional[Callable[[AgentTask], None]] = None
    ) -> bool:
        """
        Performs an optimistic locking update on a task.
        Logic: Load -> Modify -> Save (with internal WATCH/MULTI/EXEC in Store).
        """
        # 1. Load the latest state
        task = await self.store.load_task(task_id)
        if not task:
            logger.error("task_not_found_for_transition", task_id=task_id)
            return False

        # 2. Check if already in target state (idempotency)
        if task.status == target_status:
            logger.info("task_already_in_target_status", task_id=task_id, status=target_status.value)
            return True

        # 3. Apply updates via the provided function
        task.status = target_status
        if update_fn:
            update_fn(task)
        
        # 4. Increment version for optimistic locking
        # Rationale (Why): Version-based CAS prevents overwriting concurrent changes 
        # made by other workers (e.g. timeout handling vs completion).
        task.state_version += 1
        
        try:
            # Rationale (Why): Store implementation handles the atomic WATCH/EXEC retry loop.
            await self.store.save_task(task)
            logger.info("atomic_transition_success", task_id=task_id, to_status=target_status.value)
            return True
        except Exception as e:
            logger.error("atomic_transition_failed", task_id=task_id, error=str(e))
            return False
