from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, List, AsyncGenerator


class SupervisorPlanningService(ABC):
    """
    Port for the Planning Service.
    Responsible for generating the FrozenExecutionPlan structure.
    """
    @abstractmethod
    async def plan(self, user_input: str, context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        pass


class SupervisorResponseComposeService(ABC):
    """
    Port for the Response Compose Service.
    Responsible for synthesizing the final response from multiple results.
    """
    @abstractmethod
    async def compose(self, results: List[Dict[str, Any]], context: Dict[str, Any]) -> str:
        pass

    @abstractmethod
    async def stream_compose(self, results: List[Dict[str, Any]], context: Dict[str, Any]) -> AsyncGenerator[Tuple[str, str], None]:
        """
        Stream the final response synthesis.
        Yields (event_type, token) where event_type is 'reasoning' or 'chunk'.
        """
        pass
