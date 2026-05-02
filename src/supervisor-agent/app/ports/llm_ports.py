from typing import Protocol, Dict, Any, Tuple, List, AsyncGenerator

class PlanningService(Protocol):
    """
    Port for the Planning Service.
    Uses structural typing (Protocol) for maximum flexibility.
    """
    async def plan(self, user_input: str, context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        ...

class AgentRegistry(Protocol):
    """
    Port for discovering and verifying sub-agents.
    """
    def get_active_agent_keys(self) -> List[str]:
        ...
    
    def is_agent_blocked(self, agent_key: str) -> bool:
        ...

class ResponseComposeService(Protocol):
    """
    Port for the Response Compose Service.
    Responsible for synthesizing the final response.
    """
    async def compose(self, results: List[Dict[str, Any]], context: Dict[str, Any]) -> str:
        ...

    async def stream_compose(self, results: List[Dict[str, Any]], context: Dict[str, Any]) -> AsyncGenerator[Tuple[str, str], None]:
        """
        Stream the final response synthesis.
        Yields (event_type, token) where event_type is 'reasoning' or 'chunk'.
        """
        ...
