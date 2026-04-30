import uuid
from typing import Optional, Dict, Any
from ...schemas.agent import ChatRequest
from ...domain.models import Message
from ...domain.enums import AgentRole

class AgentRequestFactory:
    """
    Standardizes the creation of internal request objects from external API inputs.
    Implements Document 26.
    """
    @staticmethod
    def create_chat_context(
        session_id: str, 
        message: str, 
        request_id: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return {
            "session_id": session_id,
            "message": message,
            "request_id": request_id or str(uuid.uuid4()),
            "trace_id": trace_id or f"tr-{uuid.uuid4().hex[:12]}",
            "task_id": str(uuid.uuid4())
        }
