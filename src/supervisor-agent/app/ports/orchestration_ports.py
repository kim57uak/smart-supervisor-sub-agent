from typing import Protocol, Dict, Any, Optional
from ..domain.models import FrozenRoutingStep, FrozenExecutionPlan

class StateGraphFactory(Protocol):
    """
    Port for generating the LangGraph StateGraph.
    Uses structural typing.
    """
    def create_graph(self):
        ...

class SwarmCoordinator(Protocol):
    """
    Port for swarm state coordination.
    """
    async def synchronize_state(self, task_id: str, agent_key: str, state_delta: Dict[str, Any]):
        ...

class HandoffPolicyService(Protocol):
    """
    Port for evaluating handoff policies.
    """
    def evaluate(self, current_step: FrozenRoutingStep, context: Dict[str, Any]) -> Any:
        ...
