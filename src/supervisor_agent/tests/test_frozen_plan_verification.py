"""
Regression tests for frozen plan verification fixes.
Tests the critical security and integrity improvements made to align with Doc 31.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.supervisor_agent.app.application.read.read_queries import SnapshotVerificationQuery
from src.supervisor_agent.app.domain.models import (
    FrozenExecutionPlan,
    ReviewedExecutionSnapshot,
    FrozenRoutingStep,
    ExecutionConstraintSet
)
from src.supervisor_agent.app.domain.enums import ReasonCode
from src.supervisor_agent.app.common.utils.canonical_json import PlanHashCalculator


@pytest.mark.asyncio
async def test_frozen_plan_hash_verification_always_recalculates():
    """Test that frozen plan hash is always recalculated from stored data (Priority 1 fix)."""

    # Setup mock stores
    mock_task_store = AsyncMock()
    mock_snapshot_store = AsyncMock()
    mock_agent_registry = MagicMock()

    # Mock the resume token tracking to return False (token not used yet)
    mock_snapshot_store.mark_resume_token_used = AsyncMock(return_value=False)

    # Mock agent registry to allow our test agent
    mock_agent_registry.is_agent_blocked = MagicMock(return_value=False)

    query = SnapshotVerificationQuery(mock_task_store, mock_snapshot_store, mock_agent_registry)

    # Create a valid frozen plan
    frozen_plan = FrozenExecutionPlan(
        task_id="test-task-1",
        session_id="test-session-1",
        request_id="test-request-1",
        trace_id="test-trace-1",
        state_version=1,
        schema_version=1,
        canonicalization_version=1,
        execution_mode="STREAM",
        request_hash="test-request-hash",
        frozen_plan_hash="correct-frozen-hash",  # This should match recalculated hash
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
        routing_queue=[
            FrozenRoutingStep(
                order=1,
                agent_key="test-agent",
                method="execute",
                source_type="PLANNER",
                reason="test",
                arguments={},
                handoff_depth=0
            )
        ],
        execution_constraints=ExecutionConstraintSet(),
        planner_metadata={}
    )

    # Calculate the correct hash that should be stored
    # Note: This matches how HitlGateService calculates the hash
    correct_hash = PlanHashCalculator.calculate_frozen_plan_hash({
        "schema_version": 1,
        "canonicalization_version": 1,
        "task_id": "test-task-1",
        "session_id": "test-session-1",
        "request_id": "test-request-1",
        "routing_queue": [step.model_dump() for step in frozen_plan.routing_queue],
        "execution_constraints": frozen_plan.execution_constraints.model_dump(),
        "planner_metadata": frozen_plan.planner_metadata
    })

    # Set the correct hash in the frozen plan
    frozen_plan.frozen_plan_hash = correct_hash
    # Create snapshot with the frozen plan
    snapshot = ReviewedExecutionSnapshot(
        task_id="test-task-1",
        session_id="test-session-1",
        request_id="test-request-1",
        trace_id="test-trace-1",
        state_version=1,
        resume_token="test-resume-token",
        request_hash="test-request-hash",
        frozen_plan_hash=correct_hash,  # This matches the recalculated hash
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
        sanitized_input={"message": "test"},
        frozen_plan=frozen_plan,
        review_reason="test"
    )

    # Mock the stores to return our test data
    mock_task_store.get_task.return_value = {
        "session_id": "test-session-1",
        "task_id": "test-task-1",
        "state": "WAITING_REVIEW",
        "version": 1
    }
    mock_snapshot_store.get_snapshot.return_value = snapshot

    # Execute verification
    result = await query.execute("test-task-1",
                                session_id="test-session-1",
                                request_params={"resume_token": "test-resume-token"})

    # Should succeed because the recalculated hash matches the stored hash
    assert result.signature_matched == True
    assert result.ttl_valid == True
    assert result.reason_code == ReasonCode.SUCCESS


@pytest.mark.asyncio
async def test_frozen_plan_hash_verification_detects_tampering():
    """Test that tampered frozen plans are detected (Priority 1 fix)."""

    # Setup mock stores
    mock_task_store = AsyncMock()
    mock_snapshot_store = AsyncMock()
    mock_agent_registry = MagicMock()

    # Mock the resume token tracking to return False (token not used yet)
    mock_snapshot_store.mark_resume_token_used = AsyncMock(return_value=False)

    # Mock agent registry to allow our test agent
    mock_agent_registry.is_agent_blocked = MagicMock(return_value=False)

    query = SnapshotVerificationQuery(mock_task_store, mock_snapshot_store, mock_agent_registry)

    # Create a frozen plan with tampered hash
    frozen_plan = FrozenExecutionPlan(
        task_id="test-task-2",
        session_id="test-session-2",
        request_id="test-request-2",
        trace_id="test-trace-2",
        state_version=1,
        schema_version=1,
        canonicalization_version=1,
        execution_mode="STREAM",
        request_hash="test-request-hash",
        frozen_plan_hash="tampered-hash-that-does-not-match",  # This is wrong!
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
        routing_queue=[
            FrozenRoutingStep(
                order=1,
                agent_key="test-agent",
                method="execute",
                source_type="PLANNER",
                reason="test",
                arguments={},
                handoff_depth=0
            )
        ],
        execution_constraints=ExecutionConstraintSet(),
        planner_metadata={}
    )

    # Create snapshot with the tampered frozen plan
    snapshot = ReviewedExecutionSnapshot(
        task_id="test-task-2",
        session_id="test-session-2",
        request_id="test-request-2",
        trace_id="test-trace-2",
        state_version=1,
        resume_token="test-resume-token",
        request_hash="test-request-hash",
        frozen_plan_hash="tampered-hash-that-does-not-match",  # Tampered hash
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
        sanitized_input={"message": "test"},
        frozen_plan=frozen_plan,
        review_reason="test"
    )

    # Mock the stores
    mock_task_store.get_task.return_value = {
        "session_id": "test-session-2",
        "task_id": "test-task-2",
        "state": "WAITING_REVIEW",
        "version": 1
    }
    mock_snapshot_store.get_snapshot.return_value = snapshot

    # Execute verification - should detect tampering
    result = await query.execute("test-task-2",
                                session_id="test-session-2",
                                request_params={"resume_token": "test-resume-token"})

    # Should fail because recalculated hash won't match stored hash
    assert result.signature_matched == False
    assert result.reason_code == ReasonCode.FROZEN_PLAN_HASH_MISMATCH


@pytest.mark.asyncio
async def test_drift_policy_method_validation():
    """Test that method allowlist validation works (Priority 2 fix)."""

    # Setup mock stores
    mock_task_store = AsyncMock()
    mock_snapshot_store = AsyncMock()
    mock_agent_registry = MagicMock()

    # Mock the resume token tracking to return False (token not used yet)
    mock_snapshot_store.mark_resume_token_used = AsyncMock(return_value=False)

    # Mock agent registry to allow our test agent
    mock_agent_registry.is_agent_blocked = MagicMock(return_value=False)

    query = SnapshotVerificationQuery(mock_task_store, mock_snapshot_store, mock_agent_registry)

    # Create a frozen plan with invalid method
    frozen_plan = FrozenExecutionPlan(
        task_id="test-task-3",
        session_id="test-session-3",
        request_id="test-request-3",
        trace_id="test-trace-3",
        state_version=1,
        schema_version=1,
        canonicalization_version=1,
        execution_mode="STREAM",
        request_hash="test-request-hash",
        frozen_plan_hash="test-hash",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
        routing_queue=[
            FrozenRoutingStep(
                order=1,
                agent_key="test-agent",
                method="invalid_method",  # This should fail validation
                source_type="PLANNER",
                reason="test",
                arguments={},
                handoff_depth=0
            )
        ],
        execution_constraints=ExecutionConstraintSet(),
        planner_metadata={}
    )

    # Calculate correct hash
    correct_hash = PlanHashCalculator.calculate_frozen_plan_hash({
        "schema_version": 1,
        "canonicalization_version": 1,
        "task_id": "test-task-3",
        "session_id": "test-session-3",
        "request_id": "test-request-3",
        "routing_queue": [step.model_dump() for step in frozen_plan.routing_queue],
        "execution_constraints": frozen_plan.execution_constraints.model_dump(),
        "planner_metadata": frozen_plan.planner_metadata
    })
    frozen_plan.frozen_plan_hash = correct_hash

    snapshot = ReviewedExecutionSnapshot(
        task_id="test-task-3",
        session_id="test-session-3",
        request_id="test-request-3",
        trace_id="test-trace-3",
        state_version=1,
        resume_token="test-resume-token",
        request_hash="test-request-hash",
        frozen_plan_hash=correct_hash,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
        sanitized_input={"message": "test"},
        frozen_plan=frozen_plan,
        review_reason="test"
    )

    # Mock the stores
    mock_task_store.get_task.return_value = {
        "session_id": "test-session-3",
        "task_id": "test-task-3",
        "state": "WAITING_REVIEW",
        "version": 1
    }
    mock_snapshot_store.get_snapshot.return_value = snapshot

    # Execute verification
    result = await query.execute("test-task-3",
                                session_id="test-session-3",
                                request_params={"resume_token": "test-resume-token"})

    # Should fail method validation
    assert result.signature_matched == False
    assert result.reason_code == ReasonCode.PLAN_DRIFT_BLOCKED
    assert result.method_allowed == False


@pytest.mark.asyncio
async def test_hash_payload_includes_all_fields():
    """Test that hash calculation includes all required fields (Priority 3 fix)."""

    # Test data
    plan_data = {
        "schema_version": 1,
        "canonicalization_version": 1,
        "task_id": "test-task-4",
        "session_id": "test-session-4",
        "request_id": "test-request-4",
        "routing_queue": [
            {
                "order": 1,
                "agent_key": "test-agent",
                "method": "execute",
                "source_type": "PLANNER",
                "reason": "test",
                "arguments": {},
                "handoff_depth": 0
            }
        ],
        "execution_constraints": {},
        "planner_metadata": {}
    }

    # Calculate hash
    hash_result = PlanHashCalculator.calculate_frozen_plan_hash(plan_data)

    # Should not raise an error and should return a valid SHA-256 hash
    assert isinstance(hash_result, str)
    assert len(hash_result) == 64  # SHA-256 hash length

    # Test that different task_id produces different hash
    plan_data["task_id"] = "different-task-id"
    different_hash = PlanHashCalculator.calculate_frozen_plan_hash(plan_data)

    assert hash_result != different_hash  # Different task_id should produce different hash


@pytest.mark.asyncio
async def test_resume_token_replay_protection():
    """Test that resume token replay attacks are prevented (Priority 4 fix)."""

    # Setup mock stores
    mock_task_store = AsyncMock()
    mock_snapshot_store = AsyncMock()
    mock_agent_registry = MagicMock()

    # Create a mock snapshot store that simulates token tracking
    mock_snapshot_store.mark_resume_token_used = AsyncMock(return_value=True)  # Token already used

    query = SnapshotVerificationQuery(mock_task_store, mock_snapshot_store, mock_agent_registry)

    # Create a valid frozen plan
    frozen_plan = FrozenExecutionPlan(
        task_id="test-task-5",
        session_id="test-session-5",
        request_id="test-request-5",
        trace_id="test-trace-5",
        state_version=1,
        schema_version=1,
        canonicalization_version=1,
        execution_mode="STREAM",
        request_hash="test-request-hash",
        frozen_plan_hash="test-hash",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
        routing_queue=[
            FrozenRoutingStep(
                order=1,
                agent_key="test-agent",
                method="execute",
                source_type="PLANNER",
                reason="test",
                arguments={},
                handoff_depth=0
            )
        ],
        execution_constraints=ExecutionConstraintSet(),
        planner_metadata={}
    )

    # Calculate correct hash
    correct_hash = PlanHashCalculator.calculate_frozen_plan_hash({
        "schema_version": 1,
        "canonicalization_version": 1,
        "task_id": "test-task-5",
        "session_id": "test-session-5",
        "request_id": "test-request-5",
        "routing_queue": [step.model_dump() for step in frozen_plan.routing_queue],
        "execution_constraints": frozen_plan.execution_constraints.model_dump(),
        "planner_metadata": frozen_plan.planner_metadata
    })
    frozen_plan.frozen_plan_hash = correct_hash

    snapshot = ReviewedExecutionSnapshot(
        task_id="test-task-5",
        session_id="test-session-5",
        request_id="test-request-5",
        trace_id="test-trace-5",
        state_version=1,
        resume_token="already-used-token",
        request_hash="test-request-hash",
        frozen_plan_hash=correct_hash,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
        sanitized_input={"message": "test"},
        frozen_plan=frozen_plan,
        review_reason="test"
    )

    # Mock the stores
    mock_task_store.get_task.return_value = {
        "session_id": "test-session-5",
        "task_id": "test-task-5",
        "state": "WAITING_REVIEW",
        "version": 1
    }
    mock_snapshot_store.get_snapshot.return_value = snapshot

    # Execute verification with already-used token
    result = await query.execute("test-task-5",
                                session_id="test-session-5",
                                request_params={"resume_token": "already-used-token"})

    # Should fail because token was already used (replay attack detected)
    assert result.signature_matched == False
    assert result.reason_code == ReasonCode.RESUME_TOKEN_ALREADY_USED


@pytest.mark.asyncio
async def test_stream_capability_validation():
    """Test stream capability validation in drift policy."""

    # Setup mock stores
    mock_task_store = AsyncMock()
    mock_snapshot_store = AsyncMock()
    mock_agent_registry = MagicMock()

    # Mock the resume token tracking to return False (token not used yet)
    mock_snapshot_store.mark_resume_token_used = AsyncMock(return_value=False)

    # Mock agent registry to allow our test agent
    mock_agent_registry.is_agent_blocked = MagicMock(return_value=False)

    query = SnapshotVerificationQuery(mock_task_store, mock_snapshot_store, mock_agent_registry)

    # Create a frozen plan with stream mode but stream not allowed
    constraints = ExecutionConstraintSet(stream_allowed=False)

    frozen_plan = FrozenExecutionPlan(
        task_id="test-task-6",
        session_id="test-session-6",
        request_id="test-request-6",
        trace_id="test-trace-6",
        state_version=1,
        schema_version=1,
        canonicalization_version=1,
        execution_mode="STREAM",  # Wants stream
        request_hash="test-request-hash",
        frozen_plan_hash="test-hash",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
        routing_queue=[
            FrozenRoutingStep(
                order=1,
                agent_key="test-agent",
                method="execute",
                source_type="PLANNER",
                reason="test",
                arguments={},
                handoff_depth=0
            )
        ],
        execution_constraints=constraints,
        planner_metadata={}
    )

    # Calculate correct hash
    correct_hash = PlanHashCalculator.calculate_frozen_plan_hash({
        "schema_version": 1,
        "canonicalization_version": 1,
        "task_id": "test-task-6",
        "session_id": "test-session-6",
        "request_id": "test-request-6",
        "routing_queue": [step.model_dump() for step in frozen_plan.routing_queue],
        "execution_constraints": frozen_plan.execution_constraints.model_dump(),
        "planner_metadata": frozen_plan.planner_metadata
    })
    frozen_plan.frozen_plan_hash = correct_hash

    snapshot = ReviewedExecutionSnapshot(
        task_id="test-task-6",
        session_id="test-session-6",
        request_id="test-request-6",
        trace_id="test-trace-6",
        state_version=1,
        resume_token="test-resume-token",
        request_hash="test-request-hash",
        frozen_plan_hash=correct_hash,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
        sanitized_input={"message": "test"},
        frozen_plan=frozen_plan,
        review_reason="test"
    )

    # Mock the stores
    mock_task_store.get_task.return_value = {
        "session_id": "test-session-6",
        "task_id": "test-task-6",
        "state": "WAITING_REVIEW",
        "version": 1
    }
    mock_snapshot_store.get_snapshot.return_value = snapshot

    # Execute verification
    result = await query.execute("test-task-6",
                                session_id="test-session-6",
                                request_params={"resume_token": "test-resume-token"})

    # Should fail stream capability validation
    assert result.signature_matched == False
    assert result.reason_code == ReasonCode.PLAN_DRIFT_BLOCKED
    assert result.stream_capability_allowed == False