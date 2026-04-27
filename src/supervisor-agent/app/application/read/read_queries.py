from typing import Dict, Any, Optional
from datetime import datetime
from ...domain.models import SnapshotVerificationResult, ReviewedExecutionSnapshot
from ...domain.enums import ReasonCode
from ...ports.store_ports import A2ATaskStore, ReviewedExecutionSnapshotStore


class TaskReadModelQuery:
    def __init__(self, task_store: A2ATaskStore):
        self.task_store = task_store

    async def execute(self, task_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        return await self.task_store.get_task(task_id)


class SnapshotVerificationQuery:
    def __init__(self, task_store: A2ATaskStore, snapshot_store: ReviewedExecutionSnapshotStore):
        self.task_store = task_store
        self.snapshot_store = snapshot_store

    async def execute(self, task_id: str, **kwargs) -> SnapshotVerificationResult:
        request_params = kwargs.get("request_params", {})
        
        current_task = await self.task_store.get_task(task_id)
        if not current_task:
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=False, reason_code=ReasonCode.TASK_NOT_FOUND
            )
            
        snapshot = await self.snapshot_store.get_snapshot(task_id)
        if not snapshot:
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=False, reason_code=ReasonCode.SNAPSHOT_NOT_FOUND
            )

        # 1. Session Ownership Check
        if snapshot.session_id != current_task.get("session_id"):
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=True, reason_code=ReasonCode.SESSION_OWNERSHIP_MISMATCH
            )

        # 2. State Version Check
        if snapshot.state_version != int(current_task.get("version", 0)):
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=True, reason_code=ReasonCode.STATE_VERSION_MISMATCH
            )

        # 3. Hash Verification (Check if request hash matches the one generated at planning time)
        if "session_id" in request_params:
            from ...common.utils.canonical_json import PlanHashCalculator
            recalculated_hash = PlanHashCalculator.calculate_request_hash(request_params)
            
            if snapshot.request_hash != recalculated_hash:
                return SnapshotVerificationResult(
                    signature_matched=False, ttl_valid=True, reason_code=ReasonCode.REQUEST_HASH_MISMATCH
                )

        # 4. TTL Check
        if snapshot.expires_at < datetime.utcnow():
            return SnapshotVerificationResult(
                signature_matched=False, ttl_valid=False, reason_code=ReasonCode.SNAPSHOT_EXPIRED
            )
        
        return SnapshotVerificationResult(
            signature_matched=True, ttl_valid=True, reason_code=ReasonCode.SUCCESS
        )
