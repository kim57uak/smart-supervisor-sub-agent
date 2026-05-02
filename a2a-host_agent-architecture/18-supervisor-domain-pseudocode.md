# 18. Supervisor Domain Pseudocode

## Request / Parameters

```python
from pydantic import BaseModel
from typing import Optional, Dict, Any

class SendMessageParams(BaseModel):
    session_id: str
    message: str
    request_id: Optional[str] = None
    model: Optional[str] = None

class ReviewDecideRequest(BaseModel):
    task_id: str
    decision: Decision
    session_id: Optional[str] = None
    request_params: Optional[Dict[str, Any]] = None
```

## Frozen Plan / Routing Step

```python
from datetime import datetime
from typing import List, Dict, Any

class FrozenRoutingStep(BaseModel):
    order: int
    agent_key: str
    method: str
    source_type: str  # PLANNER | HANDOFF
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
    execution_mode: str  # SEND | STREAM
    request_hash: str
    frozen_plan_hash: str
    created_at: datetime
    expires_at: datetime
    routing_queue: List[FrozenRoutingStep]
    planner_metadata: Dict[str, Any]
    execution_constraints: ExecutionConstraintSet
```

## Reviewed Snapshot

```python
class ReviewedExecutionSnapshot(BaseModel):
    task_id: str
    session_id: str
    request_id: str
    state_version: int
    resume_token: str
    request_hash: str
    frozen_plan_hash: str
    frozen_plan: FrozenExecutionPlan
```

## Core Execution logic (Service Tier)

```python
# SupervisorAgentService.execute_task (API Entry)
async def execute_task(self, session_id, message, request_id):
    # 0. Idempotency Check (Redis SET NX)
    is_new, task_id = await self.coordinator.check_and_reserve_request(request_id)
    if not is_new: return self.read_facade.get_task_view(task_id)

    # 1. HITL Gate (Planning + Review Evaluation)
    review_required, plan = await self.hitl_gate.evaluate_and_open_review(task_id, session_id, request_id, message)
    
    if review_required:
        return {"status": "WAITING_REVIEW", "task_id": task_id}

    # 2. Queue for Worker (Decoupled)
    await self.task_queue.enqueue_task(session_id, task_id, plan)
    return {"status": "STREAMING", "task_id": task_id, "stream_endpoint": "/stream"}
```

## Graph Orchestrator logic (Worker Tier)

```python
# SupervisorGraphExecutionService.execute_plan (Worker Internal)
async def execute_plan(self, session_id, task_id, plan):
    # 1. Restore Shared State
    swarm_state = await self.persistence_facade.load_swarm_state(session_id)
    
    # 2. Run LangGraph via OrchestrationEngine
    # Nodes: select -> invoke -> handoff_evaluate -> handoff_apply -> merge
    final_state = await self.engine.execute(session_id, task_id, plan, initial_state)

    # 3. Post-graph Compose & Stream (Outside Graph)
    final_answer = await self._compose_and_publish_results(
        session_id, task_id, final_state["results"], context
    )

    # 4. Atomic Terminal Persistence
    await self.persistence_facade.persist_execution_completion(session_id, task_id, {
        "results": final_state["results"],
        "final_answer": final_answer,
        "swarm_state": final_state.get("swarm_state")
    })
```

## Review Approval & Audit

```python
# SnapshotVerificationQuery (Integrity Guard)
async def verify(self, task_id, session_id, request_params):
    snapshot = await self.snapshot_store.get(session_id, task_id)
    
    # 1. Ownership & TTL Audit
    if snapshot.session_id != session_id: return FAIL(SESSION_MISMATCH)
    if snapshot.expired(): return FAIL(SNAPSHOT_EXPIRED)

    # 2. Tamper Detection (Hash Audit)
    recalculated_hash = calculate_request_hash(request_params)
    if recalculated_hash != snapshot.request_hash: return FAIL(TAMPER_DETECTED)

    # 3. Drift Audit (Agent Policy)
    if any(agent.is_retired() for agent in snapshot.plan.routing_queue): return FAIL(PLAN_DRIFT)

    return SUCCESS
```

`task/review/checkpoint/swarm/snapshot`은 동일한 `task_id + state_version` 문맥으로 정렬한다.
비동기 워커 모델로 인해 API 응답은 즉시 반환되며, 모든 진행 상태는 Redis Stream을 통해 클라이언트로 전파된다.
