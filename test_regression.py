# test_regression.py
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from src.supervisor_agent.app.common.utils.canonical_json import PlanHashCalculator
from src.supervisor_agent.app.application.read.read_queries import SnapshotVerificationQuery
from src.supervisor_agent.app.domain.enums import ReasonCode, ExecutionMode
from src.supervisor_agent.app.domain.models import (
    ReviewedExecutionSnapshot, FrozenExecutionPlan, 
    FrozenRoutingStep, ExecutionConstraintSet, SnapshotVerificationResult
)

# Mock classes for testing
class MockTaskStore:
    def __init__(self, task_data=None, snapshot_data=None):
        self.task_data = task_data or {}
        self.snapshot_data = snapshot_data or {}
        self.used_tokens = set()

    async def get_task(self, session_id, task_id):
        return self.task_data.get(f"{session_id}:{task_id}")

    async def get_snapshot(self, session_id, task_id):
        return self.snapshot_data.get(f"{session_id}:{task_id}")

    async def mark_resume_token_used(self, session_id, task_id, resume_token):
        key = f"{session_id}:{task_id}:{resume_token}"
        if key in self.used_tokens:
            return True  # Already used
        self.used_tokens.add(key)
        return False  # Not used

class MockAgentRegistry:
    def __init__(self, blocked_agents=None):
        self.blocked_agents = blocked_agents or []
        
    def is_agent_blocked(self, agent_key):
        return agent_key in self.blocked_agents

def create_test_snapshot(
    task_id="task_123", 
    session_id="session_456", 
    routing_queue=None,
    execution_mode=ExecutionMode.STREAM,
    stream_allowed=True,
    max_handoff_depth=5,
    resume_token="token_123"
):
    if routing_queue is None:
        routing_queue = [
            FrozenRoutingStep(
                order=0, agent_key="agent1", method="execute", 
                source_type="planner", reason="test", arguments={}, 
                handoff_depth=0
            )
        ]
    
    constraints = ExecutionConstraintSet(
        stream_allowed=stream_allowed,
        max_handoff_depth=max_handoff_depth
    )
    
    plan = FrozenExecutionPlan(
        task_id=task_id,
        session_id=session_id,
        request_id="req_789",
        trace_id="trace_abc",
        state_version=1,
        execution_mode=execution_mode,
        request_hash="req_hash",
        frozen_plan_hash="plan_hash",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
        routing_queue=routing_queue,
        execution_constraints=constraints
    )
    
    # Recalculate real hashes for valid tests
    plan_data = {
        "schema_version": plan.schema_version,
        "canonicalization_version": plan.canonicalization_version,
        "task_id": plan.task_id,
        "session_id": plan.session_id,
        "request_id": plan.request_id,
        "routing_queue": [step.model_dump() for step in plan.routing_queue],
        "execution_constraints": plan.execution_constraints.model_dump(),
        "planner_metadata": plan.planner_metadata
    }
    plan.frozen_plan_hash = PlanHashCalculator.calculate_frozen_plan_hash(plan_data)
    
    return ReviewedExecutionSnapshot(
        task_id=task_id,
        session_id=session_id,
        request_id="req_789",
        trace_id="trace_abc",
        state_version=1,
        resume_token=resume_token,
        request_hash="req_hash",
        frozen_plan_hash=plan.frozen_plan_hash,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
        sanitized_input={},
        normalized_input={},
        frozen_plan=plan
    )

@pytest.mark.asyncio
async def test_plan_hash_calculation():
    """Test that plan hash calculation is consistent."""
    plan_data = {
        "schema_version": 1,
        "canonicalization_version": 1,
        "task_id": "task_123",
        "session_id": "session_456",
        "request_id": "request_789",
        "routing_queue": [{"agent_key": "agent1", "method": "execute"}],
        "execution_constraints": {"max_handoff_depth": 3},
        "planner_metadata": {}
    }
    hash1 = PlanHashCalculator.calculate_frozen_plan_hash(plan_data)
    hash2 = PlanHashCalculator.calculate_frozen_plan_hash(plan_data)
    assert hash1 == hash2
    assert hash1 is not None

@pytest.mark.asyncio
async def test_resume_token_replay_protection():
    """Test that resume token replay protection works."""
    store = MockTaskStore()
    query = SnapshotVerificationQuery(store, store)

    # First call: token should be available
    result1 = await query._check_resume_token_used("session_456", "task_123", "token_123")
    assert result1 is False

    # Second call: token should be already used
    result2 = await query._check_resume_token_used("session_456", "task_123", "token_123")
    assert result2 is True

@pytest.mark.asyncio
async def test_drift_policy_blocked_agent():
    """Test that drift policy blocks blocked agents."""
    registry = MockAgentRegistry(blocked_agents=["blocked_agent"])
    task_id, session_id = "task_123", "session_456"
    
    snapshot = create_test_snapshot(
        task_id=task_id, session_id=session_id,
        routing_queue=[FrozenRoutingStep(
            order=0, agent_key="blocked_agent", method="execute", 
            source_type="planner", reason="test", arguments={}, handoff_depth=0
        )]
    )
    
    store = MockTaskStore(
        task_data={f"{session_id}:{task_id}": {"session_id": session_id, "version": 1, "state": "RUNNING"}},
        snapshot_data={f"{session_id}:{task_id}": snapshot}
    )
    
    query = SnapshotVerificationQuery(store, store, agent_registry=registry)
    result = await query.execute(task_id, session_id=session_id)
    
    assert result.reason_code == ReasonCode.PLAN_DRIFT_BLOCKED
    assert result.route_allowed is False

@pytest.mark.asyncio
async def test_drift_policy_invalid_method():
    """Test that drift policy blocks invalid methods."""
    task_id, session_id = "task_123", "session_456"
    
    snapshot = create_test_snapshot(
        task_id=task_id, session_id=session_id,
        routing_queue=[FrozenRoutingStep(
            order=0, agent_key="agent1", method="invalid_method", 
            source_type="planner", reason="test", arguments={}, handoff_depth=0
        )]
    )
    
    store = MockTaskStore(
        task_data={f"{session_id}:{task_id}": {"session_id": session_id, "version": 1, "state": "RUNNING"}},
        snapshot_data={f"{session_id}:{task_id}": snapshot}
    )
    
    query = SnapshotVerificationQuery(store, store)
    result = await query.execute(task_id, session_id=session_id)
    
    assert result.reason_code == ReasonCode.PLAN_DRIFT_BLOCKED
    assert result.method_allowed is False

@pytest.mark.asyncio
async def test_drift_policy_stream_not_allowed():
    """Test that drift policy blocks stream when not allowed."""
    task_id, session_id = "task_123", "session_456"
    
    snapshot = create_test_snapshot(
        task_id=task_id, session_id=session_id,
        execution_mode=ExecutionMode.STREAM,
        stream_allowed=False
    )
    
    store = MockTaskStore(
        task_data={f"{session_id}:{task_id}": {"session_id": session_id, "version": 1, "state": "RUNNING"}},
        snapshot_data={f"{session_id}:{task_id}": snapshot}
    )
    
    query = SnapshotVerificationQuery(store, store)
    result = await query.execute(task_id, session_id=session_id)
    
    assert result.reason_code == ReasonCode.PLAN_DRIFT_BLOCKED
    assert result.stream_capability_allowed is False

@pytest.mark.asyncio
async def test_drift_policy_handoff_depth_exceeded():
    """Test that drift policy blocks handoff depth exceeded."""
    task_id, session_id = "task_123", "session_456"
    
    snapshot = create_test_snapshot(
        task_id=task_id, session_id=session_id,
        routing_queue=[FrozenRoutingStep(
            order=0, agent_key="agent1", method="execute", 
            source_type="planner", reason="test", arguments={}, handoff_depth=10
        )],
        max_handoff_depth=5
    )
    
    store = MockTaskStore(
        task_data={f"{session_id}:{task_id}": {"session_id": session_id, "version": 1, "state": "RUNNING"}},
        snapshot_data={f"{session_id}:{task_id}": snapshot}
    )
    
    query = SnapshotVerificationQuery(store, store)
    result = await query.execute(task_id, session_id=session_id)
    
    assert result.reason_code == ReasonCode.PLAN_DRIFT_BLOCKED
    assert result.security_policy_allowed is False

@pytest.mark.asyncio
async def test_resume_token_already_used_integration():
    """Test that RESUME_TOKEN_ALREADY_USED is returned for reused tokens."""
    task_id, session_id = "task_123", "session_456"
    resume_token = "used_token"
    
    snapshot = create_test_snapshot(task_id=task_id, session_id=session_id, resume_token=resume_token)
    store = MockTaskStore(
        task_data={f"{session_id}:{task_id}": {"session_id": session_id, "version": 1, "state": "RUNNING"}},
        snapshot_data={f"{session_id}:{task_id}": snapshot}
    )
    
    # Mark token as used
    await store.mark_resume_token_used(session_id, task_id, resume_token)
    
    query = SnapshotVerificationQuery(store, store)
    result = await query.execute(task_id, session_id=session_id, request_params={"resume_token": resume_token})
    
    assert result.reason_code == ReasonCode.RESUME_TOKEN_ALREADY_USED

if __name__ == "__main__":
    import sys
    pytest.main(["-v", __file__])