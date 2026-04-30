# 31. FrozenExecutionPlan Schema

Updated: 2026-04-30 (Final Implementation)

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

class ReviewedExecutionSnapshot(BaseModel):
    task_id: str
    session_id: str
    request_id: str
    trace_id: str
    state_version: int
    resume_token: str    # One-time token for secure resume
    request_hash: str
    frozen_plan_hash: str
    created_at: datetime
    expires_at: datetime
    sanitized_input: Dict[str, Any]
    frozen_plan: FrozenExecutionPlan
```

## Hash Integrity Rules

1. **Deterministic Serialization**: `CanonicalJsonSerializer`를 사용하여 키 순서 정렬 및 공백 제거(`separators=(',', ':')`) 후 직렬화한다.
2. **Input Hash**: `session_id`, `request_id`, `execution_mode`, `message`, `normalized_business_params` 등을 포함하여 요청 위변조를 감지한다.
3. **Plan Hash**: `routing_queue`, `execution_constraints`, `planner_metadata`를 포함하여 계획 위변조를 감지한다.

## Verification Protocol

승인(Approve) 시점에는 `SnapshotVerificationQuery`를 통해 다음 6단계 검증을 모두 통과해야 한다.

- **Session Ownership**: `session_id`가 원래 요청자와 일치하는지 확인.
- **State Version**: `task_id`의 현재 버전과 스냅샷의 `state_version`이 일치하는지 확인 (Optimistic Locking).
- **Request Hash**: 승인 시점에 전달된 파라미터가 최초 플래닝 시점과 동일한지 해시 대조.
- **Plan Hash**: 보관된 `frozen_plan_hash`와 전달된 값이 일치하는지 확인.
- **Resume Token**: 일회용 `resume_token`의 유효성 검증.
- **Drift Policy (Safety)**: 실행 직전, 계획에 포함된 에이전트들의 상태(은퇴, 차단 여부)를 실시간으로 최종 점검.
