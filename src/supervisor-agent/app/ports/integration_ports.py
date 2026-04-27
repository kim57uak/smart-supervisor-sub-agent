from abc import ABC, abstractmethod
from typing import Dict, Any, AsyncGenerator


class A2AInvocationService(ABC):
    """
    Port for invoking downstream agents.
    """
    @abstractmethod
    async def invoke(self, agent_key: str, method: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def invoke_stream(self, agent_key: str, method: str, arguments: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        pass
