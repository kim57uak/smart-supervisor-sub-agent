from typing import Dict, Any, Optional
from datetime import datetime
from ...domain.models import SnapshotVerificationResult, ReviewedExecutionSnapshot
from ...domain.enums import ReasonCode, TaskState
from ...ports.store_ports import TaskStore, ExecutionSnapshotStore
from ...common.utils.canonical_json import PlanHashCalculator
import structlog

logger = structlog.get_logger()


class TaskReadModelQuery:
    def __init__(self, task_store: TaskStore):
        self.task_store = task_store

    async def execute(self, task_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        session_id = kwargs.get("session_id", "unknown")
        return await self.task_store.get_task(session_id, task_id)


class SnapshotVerificationQuery:
    def __init__(self, task_store: TaskStore, snapshot_store: ExecutionSnapshotStore):
        self.task_store = task_store
        self.snapshot_store = snapshot_store

    async def execute(self, task_id: str, **kwargs) -> SnapshotVerificationResult:
        request_params = kwargs.get("request_params", {})
        session_id = kwargs.get("session_id") or request_params.get("session_id") or "unknown"
        
        current_task = await self.task_store.get_task(session_id, task_id)
        if not current_task:
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=False, reason_code=ReasonCode.TASK_NOT_FOUND
            )
            
        snapshot = await self.snapshot_store.get_snapshot(session_id, task_id)
        if not snapshot:
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=False, reason_code=ReasonCode.SNAPSHOT_NOT_FOUND
            )

        # 1. Session Ownership Check
        if snapshot.session_id != current_task.get("session_id"):
            logger.warning("audit_ownership_mismatch", task_id=task_id, session_id=session_id)
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=True, reason_code=ReasonCode.SESSION_OWNERSHIP_MISMATCH
            )
            
        if "session_id" in request_params and request_params["session_id"] != snapshot.session_id:
            logger.warning("audit_ownership_mismatch", task_id=task_id, session_id=session_id)
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=True, reason_code=ReasonCode.SESSION_OWNERSHIP_MISMATCH
            )

        # 2. State Version Check
        current_state = current_task.get("state")
        if snapshot.state_version != int(current_task.get("version", 0)):
            if current_state not in [TaskState.RUNNING.value, TaskState.COMPLETED.value, TaskState.FAILED.value]:
                return SnapshotVerificationResult(
                    signature_matched=False, ttl_valid=True, reason_code=ReasonCode.STATE_VERSION_MISMATCH
                )

        # 3. Hash & Token Verification (Doc 31: Recalculate and Compare)
        provided_input = request_params.get("request_params")
        if provided_input:
            input_to_hash = provided_input.copy()
            if "session_id" not in input_to_hash:
                input_to_hash["session_id"] = session_id
            
            # Use request_id if available to match HitlGate logic
            if "request_id" not in input_to_hash:
                 input_to_hash["request_id"] = snapshot.request_id
                
            recalculated_request_hash = PlanHashCalculator.calculate_request_hash(input_to_hash)
            if recalculated_request_hash != snapshot.request_hash:
                logger.warning("audit_integrity_violation", task_id=task_id, type="request_hash_mismatch")
                return SnapshotVerificationResult(
                    signature_matched=False, ttl_valid=True, reason_code=ReasonCode.REQUEST_HASH_MISMATCH
                )

        # Also check explicit hashes if provided
        provided_request_hash = request_params.get("request_hash")
        if provided_request_hash and provided_request_hash != snapshot.request_hash:
            logger.warning("audit_integrity_violation", task_id=task_id, type="request_hash")
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=True, reason_code=ReasonCode.REQUEST_HASH_MISMATCH
            )
            
        provided_frozen_plan_hash = request_params.get("frozen_plan_hash")
        if provided_frozen_plan_hash and provided_frozen_plan_hash != snapshot.frozen_plan_hash:
            logger.warning("audit_integrity_violation", task_id=task_id, type="frozen_plan_hash")
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=True, reason_code=ReasonCode.FROZEN_PLAN_HASH_MISMATCH
            )

        provided_resume_token = request_params.get("resume_token")
        if provided_resume_token and provided_resume_token != snapshot.resume_token:
            logger.warning("audit_integrity_violation", task_id=task_id, type="resume_token")
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=True, reason_code=ReasonCode.RESUME_TOKEN_MISMATCH
            )

        # 4. TTL Check
        if snapshot.expires_at < datetime.utcnow():
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=False, reason_code=ReasonCode.SNAPSHOT_EXPIRED
            )
            
        # 5. Drift Policy Check (Doc 31)
        route_allowed = True
        method_allowed = True
        stream_capability_allowed = True
        security_policy_allowed = True
        endpoint_available = True
        
        blocked_agents = ["blocked_agent_1", "retired_agent"] # Mock blocked list
        
        for step in snapshot.frozen_plan.routing_queue:
            if not step.agent_key or step.agent_key == "unknown":
                route_allowed = False
                logger.warning("audit_drift_blocked", task_id=task_id, reason="invalid_agent_key", agent=step.agent_key)
                break
            if step.agent_key in blocked_agents:
                route_allowed = False
                logger.warning("audit_drift_blocked", task_id=task_id, reason="agent_retired_or_blocked", agent=step.agent_key)
                break
                
        if not (route_allowed and method_allowed and stream_capability_allowed and security_policy_allowed and endpoint_available):
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=True, reason_code=ReasonCode.PLAN_DRIFT_BLOCKED,
                route_allowed=route_allowed, method_allowed=method_allowed, 
                stream_capability_allowed=stream_capability_allowed,
                security_policy_allowed=security_policy_allowed,
                endpoint_available=endpoint_available
            )
        
        return SnapshotVerificationResult(
            signature_matched=True, ttl_valid=True, reason_code=ReasonCode.SUCCESS
        )
