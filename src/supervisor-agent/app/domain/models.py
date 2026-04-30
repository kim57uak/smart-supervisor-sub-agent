from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from .enums import TaskState, ExecutionMode, ReasonCode


class FrozenRoutingStep(BaseModel):
    order: int
    agent_key: str
    method: str
    source_type: str
    reason: str
    arguments: Dict[str, Any]
    handoff_depth: int
    parent_agent_key: Optional[str] = None
    pre_hitl_a2ui: Optional[str] = None


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
    execution_mode: ExecutionMode
    resume_state: str = "ROUTING_SELECTED"
    request_hash: str
    frozen_plan_hash: str
    created_at: datetime
    expires_at: datetime
    routing_queue: List[FrozenRoutingStep]
    planner_metadata: Dict[str, Any] = {}
    execution_constraints: ExecutionConstraintSet
    review_reason: Optional[str] = None


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
    review_reason: Optional[str] = None


class SnapshotVerificationResult(BaseModel):
    signature_matched: bool
    ttl_valid: bool
    reason_code: ReasonCode = ReasonCode.SUCCESS
    
    route_allowed: bool = True
    method_allowed: bool = True
    stream_capability_allowed: bool = True
    security_policy_allowed: bool = True
    endpoint_available: bool = True
    
    @property
    def is_allowed(self) -> bool:
        return (
            self.signature_matched 
            and self.ttl_valid 
            and self.route_allowed 
            and self.method_allowed 
            and self.stream_capability_allowed 
            and self.security_policy_allowed 
            and self.endpoint_available
        )


class SupervisorTaskEvent(BaseModel):
    task_id: str
    event_id: str
    cursor: str
    event_type: str
    created_at: datetime
    payload: Dict[str, Any]
    is_replayable: bool = True
