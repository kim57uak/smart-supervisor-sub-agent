# 24. Supervisor Domain Class Model Pseudocode

```python
from pydantic import BaseModel


class SupervisorAgentRequest(BaseModel):
    session_id: str
    message: str
    model: str | None = None
```

```python
class RoutingPlan(BaseModel):
    agent_key: str
    method: str
    reason: str
    priority: int
    arguments: dict
```

```python
class ExecutionConstraintSet(BaseModel):
    max_concurrency: int
    stream_allowed: bool
    invoke_timeout_ms: int
    max_handoff_depth: int
    a2ui_allowed: bool
```

```python
class DownstreamCallResult(BaseModel):
    agent_key: str
    task_id: str | None = None
    status: str
    payload: dict | None = None
    error_code: str | None = None
    error_message: str | None = None
```

```python
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
    created_at: str
    expires_at: str
    routing_queue: list[RoutingPlan]
    planner_metadata: dict
    execution_constraints: ExecutionConstraintSet
```

```python
class ReviewedExecutionSnapshot(BaseModel):
    task_id: str
    session_id: str
    request_id: str
    trace_id: str
    sanitized_input: dict
    request_hash: str
    frozen_plan_hash: str
    state_version: int
    resume_token: str
    created_at: str
    expires_at: str
    frozen_plan: FrozenExecutionPlan
```

```python
class SupervisorPlanningDecision(BaseModel):
    routing_queue: list[RoutingPlan]
    review_required: bool
    review_reason: str | None = None
    risk_tags: list[str] = []
    planner_metadata: dict = {}
    pre_hitl_a2ui: dict | None = None
```

```python
class A2uiRenderResult(BaseModel):
    message: str
    protocol_payload_json: str
```

```python
class AgentRouteDefinition(BaseModel):
    agent_key: str
    endpoint: str
    default_method: str
    timeout_ms: int
    enabled: bool
```

```python
class AgentCardSummary(BaseModel):
    agent_key: str
    capabilities: list[str]
    supported_methods: list[str]
    streaming_supported: bool
    mutation_capable: bool
    a2ui_hint_available: bool
```

```python
class AgentRegistry(Protocol):
    async def list_enabled_agents(self) -> list[AgentRouteDefinition]: ...
    async def get(self, agent_key: str) -> AgentRouteDefinition | None: ...
```

```python
class AgentCardReader(Protocol):
    async def read(self, agent_key: str) -> AgentCardSummary | None: ...
```

```python
class RawPayloadNormalizer(Protocol):
    def supports(self, agent_key: str, payload_shape_hint: str) -> bool: ...

    async def normalize(
        self,
        agent_key: str,
        result: DownstreamCallResult,
        context: "SupervisorPlanningContext",
    ) -> dict | None: ...
```
