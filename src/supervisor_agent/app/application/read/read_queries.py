from typing import Dict, Any, Optional
from datetime import datetime, timezone
from ...domain.models import SnapshotVerificationResult, ReviewedExecutionSnapshot
from ...domain.enums import ReasonCode, TaskState
from ...ports.store_ports import TaskStore, ExecutionSnapshotStore
from ...ports.llm_ports import AgentRegistry
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
    def __init__(self, task_store: TaskStore, snapshot_store: ExecutionSnapshotStore, agent_registry: Optional[AgentRegistry] = None):
        self.task_store = task_store
        self.snapshot_store = snapshot_store
        self.agent_registry = agent_registry
        self.used_resume_tokens = set()  # In-memory cache for used tokens

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
            # Use normalized_input if available for hash compatibility
            if hasattr(snapshot, 'normalized_input') and snapshot.normalized_input:
                input_to_hash = snapshot.normalized_input.copy()
            else:
                # Fallback to provided_input
                input_to_hash = provided_input.copy()
                if "session_id" not in input_to_hash:
                    input_to_hash["session_id"] = session_id
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
            
        # 3. Frozen Plan Hash Verification (Doc 31: Always recalculate and compare)
        # Recalculate frozen_plan_hash from the stored snapshot.frozen_plan
        recalculated_frozen_plan_hash = PlanHashCalculator.calculate_frozen_plan_hash({
            "schema_version": snapshot.frozen_plan.schema_version,
            "canonicalization_version": snapshot.frozen_plan.canonicalization_version,
            "task_id": snapshot.frozen_plan.task_id,
            "session_id": snapshot.frozen_plan.session_id,
            "request_id": snapshot.frozen_plan.request_id,
            "routing_queue": [step.model_dump() for step in snapshot.frozen_plan.routing_queue],
            "execution_constraints": snapshot.frozen_plan.execution_constraints.model_dump(),
            "planner_metadata": snapshot.frozen_plan.planner_metadata
        })


        if recalculated_frozen_plan_hash != snapshot.frozen_plan_hash:
            logger.warning("audit_integrity_violation", task_id=task_id, type="frozen_plan_hash_mismatch")
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=True, reason_code=ReasonCode.FROZEN_PLAN_HASH_MISMATCH
            )

        # Also check explicit hashes if provided in request
        provided_frozen_plan_hash = request_params.get("frozen_plan_hash")
        if provided_frozen_plan_hash and provided_frozen_plan_hash != snapshot.frozen_plan_hash:
            logger.warning("audit_integrity_violation", task_id=task_id, type="frozen_plan_hash")
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=True, reason_code=ReasonCode.FROZEN_PLAN_HASH_MISMATCH
            )

        # 4. Resume Token Verification (Doc 31: One-time use guarantee)
        provided_resume_token = request_params.get("resume_token")
        if provided_resume_token and provided_resume_token != snapshot.resume_token:
            logger.warning("audit_integrity_violation", task_id=task_id, type="resume_token")
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=True, reason_code=ReasonCode.RESUME_TOKEN_MISMATCH
            )

        # 4.1 Resume Token Replay Protection: Check if token has already been used
        if provided_resume_token:
            token_already_used = await self._check_resume_token_used(session_id, task_id, provided_resume_token)
            if token_already_used:
                logger.warning("audit_replay_attack_detected", task_id=task_id, type="resume_token_reuse")
                return SnapshotVerificationResult(
                    signature_matched=False, ttl_valid=True, reason_code=ReasonCode.RESUME_TOKEN_ALREADY_USED
                )

        # 4. TTL Check
        if snapshot.expires_at < datetime.now(timezone.utc):
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=False, reason_code=ReasonCode.SNAPSHOT_EXPIRED
            )
            
        # 5. Drift Policy Check (Doc 31: Real-time validation before execution)
        route_allowed = True
        method_allowed = True
        stream_capability_allowed = True
        security_policy_allowed = True
        endpoint_available = True

        for step in snapshot.frozen_plan.routing_queue:
            # 5.1 Route Validation: Check agent availability and retirement status
            if not step.agent_key or step.agent_key == "unknown":
                route_allowed = False
                logger.warning("audit_drift_blocked", task_id=task_id, reason="invalid_agent_key", agent=step.agent_key)
                break

            # Rationale (Why): Using the dynamic AgentRegistry (Port) to verify if the agent
            # is still active and discovered. This replaces the previous mock list.
            if self.agent_registry and self.agent_registry.is_agent_blocked(step.agent_key):
                route_allowed = False
                logger.warning("audit_drift_blocked", task_id=task_id, reason="agent_retired_or_blocked", agent=step.agent_key)
                break

            # 5.2 Method Validation: Check if the method is in the allowlist
            allowed_methods = ["execute", "process", "handle", "generate", "analyze", "message/send"]  # Doc 31 allowlist
            if step.method not in allowed_methods:
                method_allowed = False
                logger.warning("audit_drift_blocked", task_id=task_id, reason="method_not_allowed", method=step.method)
                break

            # 5.3 Stream Capability Validation: Check execution mode compatibility
            if (snapshot.frozen_plan.execution_mode == "STREAM" or str(snapshot.frozen_plan.execution_mode) == "ExecutionMode.STREAM") and not snapshot.frozen_plan.execution_constraints.stream_allowed:
                stream_capability_allowed = False
                logger.warning("audit_drift_blocked", task_id=task_id, reason="stream_not_allowed")
                break

            # 5.4 Security Policy Validation: Check handoff depth limits
            if step.handoff_depth > snapshot.frozen_plan.execution_constraints.max_handoff_depth:
                security_policy_allowed = False
                logger.warning("audit_drift_blocked", task_id=task_id, reason="max_handoff_depth_exceeded",
                              depth=step.handoff_depth, max_allowed=snapshot.frozen_plan.execution_constraints.max_handoff_depth)
                break

        # 5.5 Endpoint Availability Validation: Check if supervisor endpoints are operational
        # This would typically involve checking service health, circuit breakers, etc.
        # For now, we'll implement a basic check that can be enhanced with real health checks
        try:
            # Placeholder for actual endpoint availability checking logic
            # In production, this would check service discovery, circuit breakers, etc.
            endpoint_available = True  # Assume available unless we have evidence otherwise
        except Exception as e:
            logger.warning("audit_drift_blocked", task_id=task_id, reason="endpoint_unavailable", error=str(e))
            endpoint_available = False
                
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

    async def _check_resume_token_used(self, session_id: str, task_id: str, resume_token: str) -> bool:
        """Check if a resume token has already been used to prevent replay attacks."""
        # First check in-memory cache
        if resume_token in self.used_resume_tokens:
            logger.warning("resume_token_reuse_detected_in_memory_cache", task_id=task_id)
            return True

        try:
            # Then check persistent store
            if hasattr(self.snapshot_store, 'mark_resume_token_used'):
                is_used = await self.snapshot_store.mark_resume_token_used(session_id, task_id, resume_token)
                if is_used:
                    self.used_resume_tokens.add(resume_token)  # Update cache
                    return True
                return False
            else:
                # If store doesn't support tracking, use in-memory cache only
                self.used_resume_tokens.add(resume_token)
                return False
        except Exception as e:
            logger.error("resume_token_tracking_failed", session_id=session_id, task_id=task_id, error=str(e))
            # Fail safe: If tracking fails, assume it's a replay attack
            return True
