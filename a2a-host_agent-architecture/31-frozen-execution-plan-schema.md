# 31. FrozenExecutionPlan Schema

Updated: 2026-04-28 (Final Implementation)

## Required Data Models

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
    schema_version: int = 1
    canonicalization_version: int = 1
    execution_mode: str  # SEND | STREAM
    request_hash: str    # Hash of the normalized input
    frozen_plan_hash: str # Hash of the routing_queue + constraints
    created_at: datetime
    expires_at: datetime
    routing_queue: List[FrozenRoutingStep]
    planner_metadata: Dict[str, Any] = {}
    execution_constraints: ExecutionConstraintSet
```

## Hash Integrity Rules

1. **Deterministic Serialization**: `CanonicalJsonSerializer`를 사용하여 키 순서 정렬 및 공백 제거 후 직렬화한다.
2. **Input Hash**: `request_id`, `message`, `session_id` 등을 포함하여 요청 위변조를 감지한다.
3. **Plan Hash**: 동결된 라우팅 단계와 실행 제약 조건을 포함하여 계획 위변조를 감지한다.

## Verification Protocol

승인(Approve) 시점에는 다음 6단계 검증을 모두 통과해야 한다.

- `session_id` Ownership Check
- `task_id` Existence Check
- `state_version` Sequence Check (Optimistic Locking)
- `request_hash` Integrity Check
- `frozen_plan_hash` Integrity Check
- `drift_policy` (Agent availability check at runtime)
