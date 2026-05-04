import asyncio
import json
import uuid
from typing import Union, AsyncIterator, Optional
from fastapi import APIRouter, Request, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.schemas.jsonrpc import JsonRpcRequest, JsonRpcResponse, JsonRpcError
from app.schemas.supervisor import (
    SendMessageParams, 
    ReviewDecideRequest, 
    ReviewApproveAck, 
    ReviewRejectResult,
    TaskEventsParams,
    CancelTaskRequest
)
from app.domain.enums import (
    Decision, ExecutionMode, ReasonCode, TaskState, EventType,
    ApiMethod, RpcErrorCode, ProcessStatus
)
from app.core.dependencies import (
    get_validator,
    get_translator,
    get_supervisor_agent_service,
    get_event_service
)
from app.core.config import settings
from app.adapters.llm.voice_adapter_factory import VoiceAdapterFactory

import structlog
logger = structlog.get_logger(__name__)

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
        session_id = request_data.params.get("session_id")
        task_id = request_data.params.get("task_id")
        if not session_id or not task_id:
            return translator.to_rpc_error(request_data.id, RpcErrorCode.INVALID_PARAMS.value, "session_id and task_id are required")
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
        session_id = params.session_id
        if not session_id:
            return translator.to_rpc_error(request_data.id, RpcErrorCode.INVALID_PARAMS.value, "session_id is required")
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
                session_id = params.session_id
                if not session_id:
                     yield f"event: error\ndata: {json.dumps({'error': 'SESSION_ID_REQUIRED'})}\n\n"
                     return
                logger.info("stream_subscription_started", task_id=params.task_id, session_id=session_id, cursor=params.cursor)
                async for event in event_service.subscribe(session_id, params.task_id, params.cursor, replay=params.replay):
                    yield f"event: {event.event_type}\ndata: {json.dumps(event.payload)}\n\n"
            except ValueError as e:
                error_msg = "CURSOR_EXPIRED" if str(e) == "CURSOR_EXPIRED" else str(e)
                yield f"event: error\ndata: {json.dumps({'error': error_msg})}\n\n"
        
        return StreamingResponse(event_generator(), media_type="text/event-stream")
    
    raise HTTPException(status_code=400, detail="Invalid stream method")


@router.websocket("/voice/stream")
async def websocket_voice_stream(
    websocket: WebSocket,
    session_id: str,
    agent_service=Depends(get_supervisor_agent_service)
):
    """
    브라우저에서 오는 실시간 오디오 스트림을 수신하고, 
    텍스트 변환 완료 시 서버에서 즉시 에이전트 작업을 트리거합니다 (Doc 20/23).
    """
    await websocket.accept()
    
    try:
        logger.info("voice_websocket_connected", session_id=session_id, client_host=websocket.client.host)
        adapter = VoiceAdapterFactory.create_adapter()
    except Exception as e:
        logger.error("voice_adapter_creation_failed", error=str(e))
        await websocket.send_json({"type": "error", "message": "Voice provider not available"})
        await websocket.close()
        return
    
    try:
        await adapter.connect()
        
        async def receive_loop():
            try:
                # Rationale (Why): iter_bytes is cleaner for binary streaming.
                chunk_count = 0
                async for message in websocket.iter_bytes():
                    chunk_count += 1
                    await adapter.send_audio(message)
            except WebSocketDisconnect:
                logger.info("voice_receive_loop_disconnected")
            except Exception as e:
                if "disconnect" not in str(e).lower():
                    logger.error("voice_receive_loop_failed", error=str(e))

        async def send_loop():
            try:
                async for event in adapter.listen():
                    # Rationale (Why): Server-side orchestration triggers task immediately after STT.
                    if event.get("type") == "final_transcript":
                        transcript = event.get("text")
                        if transcript:
                            request_id = str(uuid.uuid4())
                            logger.info("voice_stt_completed_triggering_task", session_id=session_id, transcript=transcript)
                            
                            # Trigger the same logic as POST /tasks
                            result = await agent_service.execute_task(session_id, transcript, request_id)
                            
                            # Notify client that task has started on server
                            event["task_started"] = True
                            event["task_id"] = result.get("task_id")
                            event["status"] = result.get("status")
                            event["review_reason"] = result.get("review_reason")
                    
                    # Rationale (Why): Check if client is still connected before sending.
                    # Prevent "Unexpected ASGI message" error when client closes WS after receiving final_transcript.
                    if websocket.client_state.name == "CONNECTED":
                        await websocket.send_json(event)
                    else:
                        logger.info("voice_send_loop_skipping_send_closed")
                        break
            except WebSocketDisconnect:
                logger.info("voice_send_loop_disconnected")
            except Exception as e:
                # Suppress common race condition errors during disconnect
                if "disconnect" not in str(e).lower() and "websocket.send" not in str(e).lower():
                    logger.error("voice_send_loop_failed", error=str(e))

        # Run receive and send in parallel to avoid blocking.
        await asyncio.gather(receive_loop(), send_loop())
                
    except Exception as e:
        if "disconnect" not in str(e).lower():
            logger.error("voice_websocket_failed", error=str(e))
    finally:
        await adapter.close()
        try:
            await websocket.close()
        except:
            pass
