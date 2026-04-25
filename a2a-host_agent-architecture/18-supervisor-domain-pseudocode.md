# 18. Supervisor Domain Pseudocode

## Request

```python
from pydantic import BaseModel


class SupervisorAgentRequest(BaseModel):
    session_id: str
    message: str
    model: str | None = None
```

## Routing Plan

```python
from typing import Any


class RoutingPlan(BaseModel):
    agent_key: str
    method: str
    reason: str
    priority: int
    arguments: dict[str, Any]
    source_type: str  # PLANNER | HANDOFF
    handoff_depth: int = 0
    parent_agent_key: str | None = None
```

## Planner Decision

```python
class SupervisorPlanningDecision(BaseModel):
    routing_plans: list[RoutingPlan]
    review_required: bool
    review_reason: str | None = None
    risk_tags: list[str] = []
    planner_metadata: dict[str, Any] = {}
    pre_hitl_a2ui: dict[str, Any] | None = None
```

## Frozen Plan / Reviewed Snapshot

```python
from datetime import datetime


class FrozenExecutionPlan(BaseModel):
    task_id: str
    session_id: str
    request_id: str
    trace_id: str
    state_version: int
    schema_version: int
    canonicalization_version: int
    execution_mode: str  # SEND | STREAM
    resume_state: str  # ROUTING_SELECTED
    request_hash: str
    frozen_plan_hash: str
    created_at: datetime
    expires_at: datetime
    routing_queue: list[RoutingPlan]
    planner_metadata: dict[str, Any]
    execution_constraints: dict[str, Any]
```

```python
class ReviewedExecutionSnapshot(BaseModel):
    task_id: str
    session_id: str
    request_id: str
    trace_id: str
    sanitized_input: dict[str, Any]
    request_hash: str
    frozen_plan_hash: str
    state_version: int
    resume_token: str
    created_at: datetime
    expires_at: datetime
    frozen_plan: FrozenExecutionPlan
```

## Downstream Result

```python
class DownstreamCallResult(BaseModel):
    agent_key: str
    task_id: str | None = None
    status: str
    payload: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    handoff_requested: bool = False
    next_agent_key: str | None = None
    handoff_method: str | None = None
    handoff_reason: str | None = None
    handoff_arguments: dict[str, Any] | None = None
```

## Handoff Directive

```python
class HandoffDirective(BaseModel):
    next_agent_key: str
    method: str
    reason: str
    arguments: dict[str, Any]
```

## Orchestrator Skeleton

```python
async def execute(self, request: SupervisorAgentRequest):
    context = await self.load_context(request)
    decision = await self.planning_service.plan(context)

    if not decision or not decision.routing_plans:
        yield SupervisorOutputEvent.waiting_review(
            "planner decision missing; fail-closed"
        )
        return

    if decision.review_required:
        frozen_plan = self.frozen_execution_plan_factory.freeze(
            context=context,
            decision=decision,
            next_state_version=self.next_state_version(),
        )
        snapshot = ReviewedExecutionSnapshot(
            **self.snapshot_payload(context, decision, frozen_plan)
        )
        await self.persistence_facade.persist(self.open_review(snapshot))
        yield SupervisorOutputEvent.waiting_review(decision.review_reason or "review")
        return

    queue = list(self.bounded(decision.routing_plans))
    while queue:
        plan = queue.pop(0)
        result = await self.invocation_service.invoke(plan, context)
        context.add_result(result)

        if self.handoff_enabled() and result.handoff_requested:
            checked = await self.handoff_policy_service.evaluate(result, context)
            if checked.accepted:
                queue.append(self.to_handoff_plan(result, checked))

        await self.progress_publisher.record_progress(
            context=context,
            stage="handoff",
            percent=65,
            message="handoff evaluated",
        )

    async for event in self.compose_service.stream_compose_events(context):
        yield event

    await self.persistence_facade.persist(
        self.complete_execution(context.task_id, context.collected_result)
    )
```

```python
async def approve_and_resume(self, request: ReviewDecisionRequest):
    verified = await self.read_facade.read(
        snapshot_verification_query(
            task_id=request.task_id,
            session_id=request.session_id,
            resume_token=request.resume_token,
            state_version=request.state_version,
            request_hash=request.request_hash,
            frozen_plan_hash=request.frozen_plan_hash,
        )
    )

    if not verified.resume_allowed:
        return verified

    await self.execution_consistency_coordinator.start_approved_resume(
        task_id=request.task_id,
        session_id=request.session_id,
        state_version=request.state_version,
    )
    return verified
```

`execution_mode=STREAM` approve 흐름:

- approve API는 runtime stream payload를 직접 반환하지 않는다.
- approve 성공 응답은 내부 기준 `task_id + state_version + execution_mode + resume_accepted` ack만 반환한다.
- client는 approve ack 이후 `task_id` 기준 event stream에 재구독한다.
- resumed runtime은 task-scoped event publisher를 통해 `progress/chunk/a2ui/done|error`를 발행한다.

## Swarm State Skeleton

```python
class SwarmSharedState(BaseModel):
    state_version: int
    shared_facts: dict[str, Any]
    event_log: list[dict[str, Any]]
```

`task/review/checkpoint/swarm/snapshot`은 동일한 `task_id + state_version` 문맥으로 정렬한다.
approve resume는 `resume_token + state_version + request_hash + frozen_plan_hash` 검증을 통과한 snapshot만 허용한다.
approve 시 drift가 감지되면 planner 재호출이 아니라 `REJECT_RESUME` 또는 `REOPEN_REVIEW`로 처리한다.
