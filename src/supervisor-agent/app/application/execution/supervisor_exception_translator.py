from typing import Any, Dict
from ...schemas.jsonrpc import JsonRpcResponse, JsonRpcError
from ...schemas.supervisor import ReviewRejectResult
from ...domain.enums import ReasonCode


class SupervisorExceptionTranslator:
    """
    Implements Item 8: Response Mapper.
    Maps domain errors and verification failures to standard A2A responses.
    """
    
    @staticmethod
    def to_review_reject_response(
        rpc_id: Any, 
        task_id: str, 
        reason: ReasonCode, 
        current_state: str,
        state_version: int
    ) -> JsonRpcResponse:
        return JsonRpcResponse(
            id=rpc_id,
            result=ReviewRejectResult(
                task_id=task_id,
                resume_accepted=False,
                reason_code=reason.value,
                current_state=current_state,
                state_version=state_version
            )
        )

    @staticmethod
    def to_rpc_error(rpc_id: Any, code: int, message: str) -> JsonRpcResponse:
        return JsonRpcResponse(
            id=rpc_id,
            error=JsonRpcError(code=code, message=message)
        )
