from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ..domain.models import FrozenRoutingStep, FrozenExecutionPlan


class SupervisorStateGraphFactory(ABC):
    """
    Port for generating the LangGraph StateGraph.
    """
    @abstractmethod
    def create_graph(self):
        pass


class SupervisorSwarmCoordinator(ABC):
    """
    Port for swarm state coordination.
    """
    @abstractmethod
    async def synchronize_state(self, task_id: str, agent_key: str, state_delta: Dict[str, Any]):
        pass


class HandoffPolicyService(ABC):
    """
    Port for evaluating handoff policies.
    """
    @abstractmethod
    def evaluate(self, current_step: FrozenRoutingStep, context: Dict[str, Any]) -> Any:
        pass
