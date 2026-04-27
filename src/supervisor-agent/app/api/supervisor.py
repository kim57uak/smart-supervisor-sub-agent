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
    TaskEventsParams
)
from ..domain.enums import Decision, ExecutionMode, ReasonCode, TaskState, EventType
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
    """
    try:
        await validator.validate_request(request_data)
    except ValueError as e:
        logger.warning("request_validation_failed", method=request_data.method, error=str(e))
        return translator.to_rpc_error(request_data.id, -32602, str(e))

    method = request_data.method
    
    if method in ["message/send", "SendMessage"]:
        params = SendMessageParams(**request_data.params)
        result = await agent_service.execute_task(params.session_id, params.message)
        return JsonRpcResponse(id=request_data.id, result=result)
    
    elif method == "tasks/review/decide":
        params = ReviewDecideRequest(**request_data.params)
        success, reason_code, resume_data = await agent_service.handle_review_decision(params)
        
        if not success:
            return translator.to_review_reject_response(
                request_data.id, 
                params.task_id, 
                reason_code, 
                "UNKNOWN", 
                0
            )
            
        if params.decision == Decision.CANCEL:
            return JsonRpcResponse(id=request_data.id, result={"task_id": params.task_id, "status": "CANCELED"})
            
        return JsonRpcResponse(
            id=request_data.id,
            result=ReviewApproveAck(
                task_id=params.task_id,
                state_version=resume_data["state_version"],
                execution_mode=ExecutionMode.STREAM.value,
                resume_accepted=True,
                stream_resume_required=True,
                stream_method="tasks/events",
                stream_endpoint=f"{settings.api_prefix}/stream",
                initial_cursor=resume_data["initial_cursor"]
            )
        )
    
    return translator.to_rpc_error(request_data.id, -32601, "Method not found")


@router.post("/stream")
async def handle_supervisor_stream(
    request_data: JsonRpcRequest,
    event_service=Depends(get_event_service)
):
    """
    SSE entrypoint for supervisor events and stream requests.
    """
    method = request_data.method
    
    if method in ["tasks/events", "TaskEvents"]:
        params = TaskEventsParams(**request_data.params)
        
        async def event_generator():
            async for event in event_service.subscribe(params.task_id, params.cursor):
                yield f"event: {event.event_type}\ndata: {json.dumps(event.payload)}\n\n"
        
        return StreamingResponse(event_generator(), media_type="text/event-stream")
    
    raise HTTPException(status_code=400, detail="Invalid stream method")
