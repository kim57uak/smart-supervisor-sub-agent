"""
Tests for SnapshotVerificationQuery.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta, timezone
from src.supervisor_agent.app.application.read.read_queries import SnapshotVerificationQuery
from src.supervisor_agent.app.domain.models import (
    ReviewedExecutionSnapshot, FrozenExecutionPlan, ExecutionConstraintSet,
    SnapshotVerificationResult
)
from src.supervisor_agent.app.domain.enums import ReasonCode
from src.supervisor_agent.app.common.utils.canonical_json import PlanHashCalculator


@pytest.mark.asyncio
async def test_resume_token_reuse_detection():
    """Test that resume token reuse is detected."""
    task_store = AsyncMock()
    snapshot_store = AsyncMock()
    snapshot_store.mark_resume_token_used.side_effect = [False, True]

    query = SnapshotVerificationQuery(task_store, snapshot_store)

    now = datetime.now(timezone.utc)
    normalized_input = {"message": "", "request_id": "req1", "session_id": "session1"}
    request_hash = PlanHashCalculator.calculate_request_hash(normalized_input)
    frozen_plan_hash = PlanHashCalculator.calculate_frozen_plan_hash({
        "task_id": "task1",
        "session_id": "session1",
        "request_id": "req1",
        "routing_queue": [],
        "execution_constraints": ExecutionConstraintSet().model_dump(),
        "planner_metadata": {}
    })

    # First use should succeed
    task_store.get_task.return_value = {"session_id": "session1", "state": "RUNNING", "version": 0}
    snapshot = ReviewedExecutionSnapshot(
        task_id="task1",
        session_id="session1",
        request_id="req1",
        trace_id="trace1",
        state_version=0,
        resume_token="token123",
        request_hash=request_hash,
        frozen_plan_hash=frozen_plan_hash,
        created_at=now,
        expires_at=now + timedelta(hours=1),
        sanitized_input={},
        normalized_input=normalized_input,
        frozen_plan=FrozenExecutionPlan(
            task_id="task1",
            session_id="session1",
            request_id="req1",
            trace_id="trace1",
            state_version=0,
            execution_mode="STREAM",
            request_hash=request_hash,
            frozen_plan_hash=frozen_plan_hash,
            created_at=now,
            expires_at=now + timedelta(hours=1),
            routing_queue=[],
            execution_constraints=ExecutionConstraintSet()
        )
    )
    snapshot_store.get_snapshot.return_value = snapshot

    result = await query.execute("task1", request_params={"resume_token": "token123"})
    assert result.signature_matched is True

    # Second use should fail
    result = await query.execute("task1", request_params={"resume_token": "token123"})
    assert result.signature_matched is False
    assert result.reason_code == ReasonCode.RESUME_TOKEN_ALREADY_USED


@pytest.mark.asyncio
@pytest.mark.skipif(True, reason="Requires real Redis — integration test")
async def test_redis_token_tracking():
    """Test that Redis store properly tracks resume tokens. Requires real Redis."""
    redis_store = RedisExecutionSnapshotStore()

    is_used = await redis_store.mark_resume_token_used("session1", "task1", "token123")
    assert is_used is False

    is_used = await redis_store.mark_resume_token_used("session1", "task1", "token123")
    assert is_used is True


@pytest.mark.asyncio
async def test_normalized_input_hash_compatibility():
    """Test hash verification using normalized_input for compatibility."""
    task_store = AsyncMock()
    snapshot_store = AsyncMock()
    snapshot_store.mark_resume_token_used.return_value = False

    now = datetime.now(timezone.utc)
    task_store.get_task.return_value = {"session_id": "session1", "state": "RUNNING", "version": 0}
    normalized_input = {"message": "test", "request_id": "req1", "session_id": "session1"}
    request_hash = PlanHashCalculator.calculate_request_hash(normalized_input)
    frozen_plan_hash = PlanHashCalculator.calculate_frozen_plan_hash({
        "task_id": "task1",
        "session_id": "session1",
        "request_id": "req1",
        "routing_queue": [],
        "execution_constraints": ExecutionConstraintSet().model_dump(),
        "planner_metadata": {}
    })
    snapshot = ReviewedExecutionSnapshot(
        task_id="task1",
        session_id="session1",
        request_id="req1",
        trace_id="trace1",
        state_version=0,
        resume_token="token123",
        request_hash=request_hash,
        frozen_plan_hash=frozen_plan_hash,
        created_at=now,
        expires_at=now + timedelta(hours=1),
        sanitized_input={},
        normalized_input=normalized_input,  # Key for compatibility
        frozen_plan=FrozenExecutionPlan(
            task_id="task1",
            session_id="session1",
            request_id="req1",
            trace_id="trace1",
            state_version=0,
            execution_mode="STREAM",
            request_hash=request_hash,
            frozen_plan_hash=frozen_plan_hash,
            created_at=now,
            expires_at=now + timedelta(hours=1),
            routing_queue=[],
            execution_constraints=ExecutionConstraintSet()
        )
    )
    snapshot_store.get_snapshot.return_value = snapshot

    query = SnapshotVerificationQuery(task_store, snapshot_store)

    # Should use normalized_input for hash calculation
    result = await query.execute("task1", request_params={"resume_token": "token123"})
    assert result.signature_matched is True