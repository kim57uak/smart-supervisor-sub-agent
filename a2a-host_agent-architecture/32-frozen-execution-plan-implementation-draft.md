# 32. FrozenExecutionPlan Implementation Draft

Updated: 2026-04-25

## Purpose

본 문서는 `31-frozen-execution-plan-schema.md`의 계약을 Python 구현 초안으로 내린 문서다.
파일명은 유지하지만 내용 기준선은 Java가 아니라 Python이다.

## Package Proposal

```text
src/app
├── domain/supervisor
│   ├── frozen_execution_plan.py
│   ├── frozen_routing_step.py
│   ├── execution_constraint_set.py
│   ├── reviewed_execution_snapshot.py
│   ├── snapshot_verification.py
│   ├── environment_drift_verdict.py
│   ├── review_approve_ack.py
│   └── supervisor_task_event.py
├── application/agent/hitl
│   ├── frozen_execution_plan_factory.py
│   ├── snapshot_verification_service.py
│   ├── environment_drift_guard.py
│   └── task_event_stream_service.py
├── application/agent/consistency
│   └── execution_consistency_coordinator.py
└── infrastructure/redis
    ├── reviewed_execution_snapshot_store.py
    └── frozen_execution_plan_store.py
```

## Pydantic Drafts

```python
from datetime import datetime
from pydantic import BaseModel


class FrozenRoutingStep(BaseModel):
    order: int
    agent_key: str
    method: str
    source_type: str
    reason: str
    arguments: dict
    handoff_depth: int
    parent_agent_key: str | None = None


class ExecutionConstraintSet(BaseModel):
    max_concurrency: int
    stream_allowed: bool
    invoke_timeout_ms: int
    max_handoff_depth: int
    a2ui_allowed: bool


class FrozenExecutionPlan(BaseModel):
    task_id: str
    session_id: str
    request_id: str
    trace_id: str
    state_version: int
    schema_version: int
    canonicalization_version: int
    execution_mode: str
    resume_state: str
    request_hash: str
    frozen_plan_hash: str
    created_at: datetime
    expires_at: datetime
    routing_queue: list[FrozenRoutingStep]
    planner_metadata: dict
    execution_constraints: ExecutionConstraintSet
```

```python
class ReviewedExecutionSnapshot(BaseModel):
    task_id: str
    session_id: str
    request_id: str
    trace_id: str
    state_version: int
    resume_token: str
    request_hash: str
    frozen_plan_hash: str
    created_at: datetime
    expires_at: datetime
    sanitized_input: dict
    frozen_plan: FrozenExecutionPlan
```

## Verification Models

```python
class SnapshotVerificationRequest(BaseModel):
    task_id: str
    session_id: str
    resume_token: str
    state_version: int
    request_hash: str
    frozen_plan_hash: str


class EnvironmentDriftVerdict(BaseModel):
    route_allowed: bool
    method_allowed: bool
    stream_capability_allowed: bool
    security_policy_allowed: bool
    endpoint_available: bool
    violations: list[str]
    action: str


class SnapshotVerificationResult(BaseModel):
    signature_matched: bool
    ttl_valid: bool
    drift_verdict: EnvironmentDriftVerdict

    @property
    def resume_allowed(self) -> bool:
        return (
            self.signature_matched
            and self.ttl_valid
            and self.drift_verdict.action == "ALLOW_RESUME"
        )
```

```python
class ReviewApproveAck(BaseModel):
    task_id: str
    state_version: int
    execution_mode: str
    resume_accepted: bool
    stream_resume_required: bool
    stream_method: str | None = None
    stream_endpoint: str | None = None
    initial_cursor: str | None = None
```
