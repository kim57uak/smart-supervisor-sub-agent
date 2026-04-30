from typing import Dict, Any, Optional
from ...domain.enums import ProcessStatus

class AgentResponseMapper:
    """
    Standardizes the mapping of internal results to external API responses.
    Implements Document 26.
    """
    @staticmethod
    def map_to_chat_response(
        task_id: str, 
        trace_id: str, 
        status: ProcessStatus = ProcessStatus.ACCEPTED
    ) -> Dict[str, Any]:
        return {
            "task_id": task_id,
            "status": status.value,
            "trace_id": trace_id,
            "stream_url": f"/api/v1/stream/{task_id}"
        }

    @staticmethod
    def map_duplicate_response(request_id: str, trace_id: str) -> Dict[str, Any]:
        return {
            "status": "ALREADY_PROCESSED", 
            "request_id": request_id, 
            "trace_id": trace_id
        }
