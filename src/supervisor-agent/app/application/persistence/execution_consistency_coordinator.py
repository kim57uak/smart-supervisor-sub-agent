import json
import asyncio
from typing import Tuple, Dict, Any, Optional
from ...domain.enums import TaskState, ReasonCode
from ...ports.store_ports import A2ATaskStore, ReviewedExecutionSnapshotStore
from ...domain.models import ReviewedExecutionSnapshot
import structlog

logger = structlog.get_logger()


class ExecutionConsistencyCoordinator:
    """
    Ensures atomic state transitions and coordinates subordinate writes.
    Uses TaskStore and SnapshotStore ports.
    """
    def __init__(
        self, 
        task_store: A2ATaskStore,
        snapshot_store: ReviewedExecutionSnapshotStore,
        redis_client # Need raw redis for CAS/Transactions if ports don't abstract it
    ):
        self.task_store = task_store
        self.snapshot_store = snapshot_store
        self.redis = redis_client

    async def persist_snapshot(self, task_id: str, snapshot: ReviewedExecutionSnapshot, ttl: int):
        await self.snapshot_store.save_snapshot(task_id, snapshot, ttl)

    async def transition_to_waiting_review(self, task_id: str, session_id: str = "unknown"):
        # Simplified: in reality, use CAS
        task = await self.task_store.get_task(task_id)
        if not task:
            task = {"task_id": task_id, "version": 0, "session_id": session_id}
        task["state"] = TaskState.WAITING_REVIEW.value
        await self.task_store.save_task(task_id, task)

    async def start_approved_resume(self, task_id: str, expected_version: int) -> Tuple[bool, ReasonCode, Optional[int]]:
        """
        Executes WAITING_REVIEW -> RUNNING CAS transition.
        """
        # Using raw Redis for WATCH/MULTI/EXEC CAS
        task_key = f"supervisor:task:{task_id}"
        
        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                while True:
                    try:
                        await pipe.watch(task_key)
                        current_data = await pipe.hgetall(task_key)
                        
                        if not current_data:
                            return False, ReasonCode.TASK_NOT_FOUND, None
                            
                        current_state = current_data.get("state")
                        current_version = int(current_data.get("version", 0))
                        
                        if current_state in [TaskState.COMPLETED.value, TaskState.FAILED.value, TaskState.CANCELED.value]:
                            return False, ReasonCode.ALREADY_TERMINAL, current_version
                            
                        if current_state == TaskState.RUNNING.value:
                            return False, ReasonCode.DUPLICATE_DECISION, current_version
                            
                        if current_state != TaskState.WAITING_REVIEW.value:
                            return False, ReasonCode.TASK_STATE_INVALID, current_version
                            
                        if current_version != expected_version:
                            return False, ReasonCode.STATE_VERSION_MISMATCH, current_version
                            
                        pipe.multi()
                        pipe.hset(task_key, mapping={
                            "state": TaskState.RUNNING.value,
                            "version": current_version + 1
                        })
                        await pipe.execute()
                        return True, ReasonCode.SUCCESS, current_version + 1
                        
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        # WatchError means someone else modified it
                        if "WatchError" in str(type(e)):
                            continue
                        raise
        except Exception as e:
            logger.error("cas_transition_error", error=str(e))
            return False, ReasonCode.EXECUTION_FAILURE, None

    async def complete_execution(self, task_id: str, result_data: Dict[str, Any]):
        task = await self.task_store.get_task(task_id)
        if task:
            task["state"] = TaskState.COMPLETED.value
            task.update(result_data)
            await self.task_store.save_task(task_id, task)
