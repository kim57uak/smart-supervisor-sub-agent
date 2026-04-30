from typing import Protocol, Dict, Any, AsyncGenerator

class A2AInvocationService(Protocol):
    """
    Port for invoking downstream agents.
    Uses structural typing (Protocol).
    """
    async def invoke(self, agent_key: str, method: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        ...

    async def invoke_stream(self, agent_key: str, method: str, arguments: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        ...
