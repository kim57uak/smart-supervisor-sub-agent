# 24. Supervisor Domain Class Model Reference

Updated: 2026-04-28 (Implementation Aligned)

## Core Execution Models

```python
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class FrozenRoutingStep(BaseModel):
    order: int
    agent_key: str
    method: str
    source_type: str  # PLANNER | HANDOFF
    reason: str
    arguments: Dict[str, Any]
    handoff_depth: int
    parent_agent_key: Optional[str] = None

class ExecutionConstraintSet(BaseModel):
    max_concurrency: int = 1
    stream_allowed: bool = True
    invoke_timeout_ms: int = 30000
    max_handoff_depth: int = 5
    a2ui_allowed: bool = True

class FrozenExecutionPlan(BaseModel):
    task_id: str
    session_id: str
    request_id: str
    trace_id: str
    state_version: int
    execution_mode: str  # SEND | STREAM
    request_hash: str
    frozen_plan_hash: str
    created_at: datetime
    expires_at: datetime
    routing_queue: List[FrozenRoutingStep]
    planner_metadata: Dict[str, Any]
    execution_constraints: ExecutionConstraintSet
```

## Security & Snapshot Models

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
    sanitized_input: Dict[str, Any]
    frozen_plan: FrozenExecutionPlan

class SnapshotVerificationResult(BaseModel):
    signature_matched: bool
    ttl_valid: bool
    reason_code: str
    route_allowed: bool = True
    method_allowed: bool = True
    stream_capability_allowed: bool = True
    security_policy_allowed: bool = True
    endpoint_available: bool = True
```

## Protocol & Event Models

```python
class SupervisorTaskEvent(BaseModel):
    task_id: str
    event_id: str
    cursor: str
    event_type: str  # progress, reasoning, chunk, a2ui, done, error
    created_at: datetime
    payload: Dict[str, Any]
```
