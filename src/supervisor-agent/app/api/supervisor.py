import asyncio
import json
import uuid
from typing import Union, AsyncIterator
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse

from ..schemas.jsonrpc import JsonRpcRequest, JsonRpcResponse, JsonRpcError
from ..schemas.supervisor import (
    SendMessageParams, 
    ReviewDecideRequest, 
    ReviewApproveAck, 
    ReviewRejectResult,
    TaskEventsParams,
    CancelTaskRequest
)
from ..domain.enums import (
    Decision, ExecutionMode, ReasonCode, TaskState, EventType,
    ApiMethod, RpcErrorCode, ProcessStatus
)
from ..core.dependencies import (
    get_validator,
    get_translator,
    get_supervisor_agent_service,
    get_event_service
)
from ..core.config import settings

import structlog
logger = structlog.get_logger()

router = APIRouter()


@router.post("", response_model=JsonRpcResponse)
async def handle_supervisor_request(
    request_data: JsonRpcRequest,
    validator=Depends(get_validator),
    translator=Depends(get_translator),
    agent_service=Depends(get_supervisor_agent_service)
):
    """
    Main entrypoint for unary supervisor requests.
    Supports both standard (path-based) and legacy (PascalCase) method names.
    Adheres to SOLID principles by decoupling validation, translation, and business logic.
    """
    try:
        await validator.validate_request(request_data)
    except ValueError as e:
        logger.warning("request_validation_failed", method=request_data.method, error=str(e))
        return translator.to_rpc_error(request_data.id, RpcErrorCode.INVALID_PARAMS.value, str(e))

    method = request_data.method
    
    # 1. message/send | SendMessage
    if method in [ApiMethod.SEND_MESSAGE.value, ApiMethod.SEND_MESSAGE_LEGACY.value]:
        params = SendMessageParams(**request_data.params)
        result = await agent_service.execute_task(params.session_id, params.message, params.request_id)
        return JsonRpcResponse(id=request_data.id, result=result)
    
    # 2. tasks/review/decide | ReviewDecide
    elif method in [ApiMethod.REVIEW_DECIDE.value, ApiMethod.REVIEW_DECIDE_LEGACY.value]:
        params = ReviewDecideRequest(**request_data.params)
        success, reason_code, resume_data = await agent_service.handle_review_decision(params)
        
        if not success:
            logger.warning("review_decide_rejected", task_id=params.task_id, reason_code=reason_code)
            return translator.to_review_reject_response(
                request_data.id, 
                params.task_id, 
                reason_code, 
                "UNKNOWN", 
                0
            )
            
        if params.decision == Decision.CANCEL:
            logger.info("review_decide_canceled", task_id=params.task_id)
            return JsonRpcResponse(
                id=request_data.id, 
                result={"task_id": params.task_id, "status": ProcessStatus.CANCELED.value}
            )
            
        return JsonRpcResponse(
            id=request_data.id,
            result=ReviewApproveAck(
                task_id=params.task_id,
                session_id=params.session_id,
                state_version=resume_data["state_version"],
                execution_mode=ExecutionMode.STREAM.value,
                resume_accepted=True,
                stream_resume_required=True,
                stream_method=ApiMethod.TASK_EVENTS.value,
                stream_endpoint=f"{settings.api_prefix}/stream",
                initial_cursor=resume_data["initial_cursor"]
            )
        )
    
    # 3. tasks/review/get | GetReview
    elif method in [ApiMethod.REVIEW_GET.value, ApiMethod.REVIEW_GET_LEGACY.value]:
        task_id = request_data.params.get("task_id")
        session_id = request_data.params.get("session_id", "unknown")
        snapshot = await agent_service.read_facade.get_snapshot(session_id, task_id)
        if not snapshot:
            return translator.to_rpc_error(
                request_data.id, 
                RpcErrorCode.REVIEW_SNAPSHOT_NOT_FOUND.value, 
                "Review snapshot not found"
            )
        return JsonRpcResponse(id=request_data.id, result=snapshot.model_dump())

    # 4. agent/card | GetAgentCard
    elif method in [ApiMethod.AGENT_CARD.value, ApiMethod.AGENT_CARD_LEGACY.value]:
        from ..adapters.llm.llm_planning_service import LlmPlanningService
        cards = LlmPlanningService.get_cached_agent_cards()
        if not cards:
            await LlmPlanningService.load_agent_cards()
            cards = LlmPlanningService.get_cached_agent_cards()
        return JsonRpcResponse(id=request_data.id, result=cards)

    # 5. tasks/cancel | CancelTask
    elif method in [ApiMethod.CANCEL_TASK.value, ApiMethod.CANCEL_TASK_LEGACY.value]:
        params = CancelTaskRequest(**request_data.params)
        session_id = params.session_id or "unknown"
        success = await agent_service.cancel_task(session_id, params.id)
        return JsonRpcResponse(
            id=request_data.id, 
            result={"task_id": params.id, "success": success}
        )

    # 6. session/clear | ClearSession
    elif method in [ApiMethod.CLEAR_SESSION.value, ApiMethod.CLEAR_SESSION_LEGACY.value]:
        session_id = request_data.params.get("session_id")
        if not session_id:
            return translator.to_rpc_error(request_data.id, RpcErrorCode.INVALID_PARAMS.value, "session_id is required")
        success = await agent_service.clear_session(session_id)
        return JsonRpcResponse(
            id=request_data.id,
            result={"session_id": session_id, "success": success}
        )
    
    return translator.to_rpc_error(request_data.id, RpcErrorCode.METHOD_NOT_FOUND.value, "Method not found")


@router.post("/stream")
async def handle_supervisor_stream(
    request_data: JsonRpcRequest,
    event_service=Depends(get_event_service)
):
    """
    SSE entrypoint for supervisor events and stream requests.
    Supports both standard and legacy method names.
    """
    method = request_data.method
    
    if method in [ApiMethod.TASK_EVENTS.value, ApiMethod.TASK_EVENTS_LEGACY.value]:
        params = TaskEventsParams(**request_data.params)
        
        async def event_generator():
            try:
                session_id = params.session_id or "unknown"
                logger.info("stream_subscription_started", task_id=params.task_id, session_id=session_id, cursor=params.cursor)
                async for event in event_service.subscribe(session_id, params.task_id, params.cursor, replay=params.replay):
                    yield f"event: {event.event_type}\ndata: {json.dumps(event.payload)}\n\n"
            except ValueError as e:
                error_msg = "CURSOR_EXPIRED" if str(e) == "CURSOR_EXPIRED" else str(e)
                yield f"event: error\ndata: {json.dumps({'error': error_msg})}\n\n"
        
        return StreamingResponse(event_generator(), media_type="text/event-stream")
    
    raise HTTPException(status_code=400, detail="Invalid stream method")
