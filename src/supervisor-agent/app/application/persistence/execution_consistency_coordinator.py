import json
import asyncio
from typing import Tuple, Dict, Any, Optional
from ...domain.enums import TaskState, ReasonCode
from ...ports.store_ports import TaskStore, ExecutionSnapshotStore, SwarmStateStore
from ...domain.models import ReviewedExecutionSnapshot
from ...core.config import settings
import structlog

logger = structlog.get_logger()


class ExecutionConsistencyCoordinator:
    """
    Ensures atomic state transitions using Redis CAS (Doc 01, 29).
    Prevents race conditions in multi-worker environments.
    """
    def __init__(
        self, 
        task_store: TaskStore,
        snapshot_store: ExecutionSnapshotStore,
        swarm_state_store: SwarmStateStore,
        redis_client
    ):
        self.task_store = task_store
        self.snapshot_store = snapshot_store
        self.swarm_state_store = swarm_state_store
        self.redis = redis_client

    def _get_task_key(self, session_id: str, task_id: str) -> str:
        return f"{settings.redis_prefix}:supervisor:session:{session_id}:task:{task_id}"

    def _get_request_lock_key(self, session_id: str, request_id: str) -> str:
        return f"{settings.redis_prefix}:supervisor:request_lock:{session_id}:{request_id}"

    async def check_and_reserve_request(self, session_id: str, request_id: str, task_id: str) -> Tuple[bool, Optional[str]]:
        """
        Uses Redis SET NX to ensure a (session_id + request_id) composite key is processed only once.
        Returns (is_new, existing_task_id).
        """
        lock_key = self._get_request_lock_key(session_id, request_id)
        # Lock expires after 1 hour to prevent indefinite pollution but cover long executions
        success = await self.redis.set(lock_key, task_id, nx=True, ex=3600)
        
        if success:
            return True, task_id
        
        existing_task_id = await self.redis.get(lock_key)
        return False, existing_task_id.decode() if isinstance(existing_task_id, bytes) else existing_task_id

    async def persist_snapshot(self, session_id: str, task_id: str, snapshot: ReviewedExecutionSnapshot, ttl: int):
        await self.snapshot_store.save_snapshot(session_id, task_id, snapshot, ttl)

    async def transition_to_waiting_review(self, session_id: str, task_id: str):
        """Initial task creation or move to review state."""
        task_key = self._get_task_key(session_id, task_id)
        # For initial setup, we ensure version starts at 0 if not exists
        await self.redis.hset(task_key, mapping={
            "task_id": task_id,
            "session_id": session_id,
            "state": TaskState.WAITING_REVIEW.value,
            "version": 0
        })
        
        # Rationale (Why): We must index the task_id -> session_id mapping early so that 
        # the event streaming service can resolve the stream path correctly even before 
        # the first event is appended by the worker.
        idx_key = f"{settings.redis_prefix}:supervisor:index:task_session:{task_id}"
        await self.redis.set(idx_key, session_id, ex=settings.redis_ttl_seconds)
        
        await self.redis.expire(task_key, settings.redis_ttl_seconds)

    async def transition_to_running(self, session_id: str, task_id: str):
        """Move to RUNNING state for a new task."""
        task_key = self._get_task_key(session_id, task_id)
        await self.redis.hset(task_key, mapping={
            "task_id": task_id,
            "session_id": session_id,
            "state": TaskState.RUNNING.value,
            "version": 0
        })
        
        # Index the task-session mapping
        idx_key = f"{settings.redis_prefix}:supervisor:index:task_session:{task_id}"
        await self.redis.set(idx_key, session_id, ex=settings.redis_ttl_seconds)
        
        await self.redis.expire(task_key, settings.redis_ttl_seconds)

    async def start_approved_resume(self, session_id: str, task_id: str, expected_version: int) -> Tuple[bool, ReasonCode, Optional[int]]:
        """WAITING_REVIEW -> RUNNING CAS transition."""
        return await self._atomic_transition(
            session_id, task_id, 
            from_states=[TaskState.WAITING_REVIEW.value],
            to_state=TaskState.RUNNING.value,
            expected_version=expected_version
        )

    async def complete_execution(self, session_id: str, task_id: str, result_data: Dict[str, Any]):
        """
        RUNNING -> COMPLETED CAS transition.
        Also persists the final SwarmState if present in result_data (Doc 03).
        """
        # Extract swarm state if provided by the orchestrator
        swarm_state = result_data.pop("swarm_state", None)
        if swarm_state:
            await self.swarm_state_store.save_swarm_state(session_id, swarm_state)
            logger.info("swarm_state_persisted", task_id=task_id, session_id=session_id)

        # Result data can be large, so we set it in the same transaction
        task_key = self._get_task_key(session_id, task_id)
        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                while True:
                    await pipe.watch(task_key)
                    current_data = await pipe.hgetall(task_key)
                    if not current_data: return
                    
                    if current_data.get("state") in [TaskState.COMPLETED.value, TaskState.FAILED.value]:
                        return # Already terminal
                        
                    version = int(current_data.get("version", 0))
                    pipe.multi()
                    pipe.hset(task_key, mapping={
                        "state": TaskState.COMPLETED.value,
                        "version": version + 1,
                        "result": json.dumps(result_data)
                    })
                    await pipe.execute()
                    return
        except Exception as e:
            logger.error("complete_execution_failed", error=str(e), task_id=task_id)

    async def cancel_task(self, session_id: str, task_id: str) -> bool:
        """Move to CANCELED state if not already terminal."""
        success, code, _ = await self._atomic_transition(
            session_id, task_id,
            from_states=[TaskState.CREATED.value, TaskState.WAITING_REVIEW.value, TaskState.RUNNING.value],
            to_state=TaskState.CANCELED.value
        )
        return success

    async def load_swarm_state(self, session_id: str) -> Dict[str, Any]:
        """
        Loads the latest shared memory (SwarmState) for the session (Doc 01, 03).
        Returns an empty dict if no state exists.
        """
        state = await self.swarm_state_store.get_swarm_state(session_id)
        return state if state else {}

    async def _atomic_transition(
        self, 
        session_id: str, 
        task_id: str, 
        from_states: list, 
        to_state: str,
        expected_version: Optional[int] = None
    ) -> Tuple[bool, ReasonCode, Optional[int]]:
        """Generic CAS helper using Redis WATCH."""
        task_key = self._get_task_key(session_id, task_id)
        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                while True:
                    try:
                        await pipe.watch(task_key)
                        current_data = await pipe.hgetall(task_key)
                        
                        if not current_data:
                            return False, ReasonCode.TASK_NOT_FOUND, None
                            
                        curr_state = current_data.get("state")
                        curr_version = int(current_data.get("version", 0))
                        
                        # Already in target state?
                        if curr_state == to_state:
                            return False, ReasonCode.DUPLICATE_DECISION, curr_version
                            
                        # Terminal check
                        if curr_state in [TaskState.COMPLETED.value, TaskState.FAILED.value, TaskState.CANCELED.value]:
                            return False, ReasonCode.ALREADY_TERMINAL, curr_version
                            
                        # Origin state check
                        if curr_state not in from_states:
                            return False, ReasonCode.TASK_STATE_INVALID, curr_version
                            
                        # Version check
                        if expected_version is not None and curr_version != expected_version:
                            return False, ReasonCode.STATE_VERSION_MISMATCH, curr_version
                            
                        pipe.multi()
                        pipe.hset(task_key, mapping={
                            "state": to_state,
                            "version": curr_version + 1
                        })
                        await pipe.execute()
                        return True, ReasonCode.SUCCESS, curr_version + 1
                        
                    except asyncio.CancelledError: raise
                    except Exception as e:
                        if "WatchError" in str(type(e)): continue
                        raise
        except Exception as e:
            logger.error("atomic_transition_error", error=str(e), task_id=task_id)
            return False, ReasonCode.EXECUTION_FAILURE, None
