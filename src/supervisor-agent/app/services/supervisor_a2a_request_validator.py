from typing import Dict, Any, Optional
from ..schemas.jsonrpc import JsonRpcRequest
from ..schemas.supervisor import SendMessageParams, ReviewDecideRequest, TaskEventsParams
from ..domain.enums import Decision, ApiMethod
from ..core.config import settings


class SupervisorA2ARequestValidator:
    """
    Validates A2A requests according to doc 26.
    """
    
    # Doc 20 기준: Supervisor 진입점 전체 method-allowlist (supervisor.yml에서 로드)
    @property
    def allowed_methods(self):
        # supervisor.yml의 host.a2a.method-allowlist를 사용 (진입점 전체 허용 목록)
        return settings.supervisor_config.get("method-allowlist", [
            ApiMethod.SEND_MESSAGE.value, ApiMethod.SEND_MESSAGE_LEGACY.value,
            "message/stream", "SendStreamingMessage",
            "tasks/get", "GetTask",
            "tasks/list", "ListTasks",
            "tasks/cancel", "CancelTask",
            ApiMethod.TASK_EVENTS.value, ApiMethod.TASK_EVENTS_LEGACY.value,
            ApiMethod.REVIEW_GET.value, ApiMethod.REVIEW_GET_LEGACY.value,
            ApiMethod.REVIEW_DECIDE.value, ApiMethod.REVIEW_DECIDE_LEGACY.value,
            ApiMethod.AGENT_CARD.value, ApiMethod.AGENT_CARD_LEGACY.value
        ])

    async def validate_request(self, request: JsonRpcRequest):
        # 1. Method allowlist check
        if request.method not in self.allowed_methods:
            raise ValueError(f"Method {request.method} not allowed")

        # 2. Params schema validation
        if request.method in [ApiMethod.SEND_MESSAGE.value, ApiMethod.SEND_MESSAGE_LEGACY.value]:
            if not request.params:
                raise ValueError("Params required for SendMessage")
            SendMessageParams(**request.params)
            
        elif request.method in [ApiMethod.REVIEW_DECIDE.value, ApiMethod.REVIEW_DECIDE_LEGACY.value]:
            if not request.params:
                raise ValueError("Params required for ReviewDecide")
            ReviewDecideRequest(**request.params)
            
        elif request.method in [ApiMethod.TASK_EVENTS.value, ApiMethod.TASK_EVENTS_LEGACY.value]:
            if not request.params:
                raise ValueError("Params required for TaskEvents")
            TaskEventsParams(**request.params)
            
        # ... other validations ...
        
        return True
