from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from app.application.execution.chat_usecase import AgentChatUseCase
from app.services.agent_authorization_service import AgentAuthorizationService
from app.core.dependencies import get_agent_usecase, get_auth_service

router = APIRouter()

class ChatRequest(BaseModel):
    session_id: str
    message: str
    request_id: Optional[str] = None
    trace_id: Optional[str] = None

class ChatResponse(BaseModel):
    task_id: str
    status: str
    trace_id: Optional[str] = None
    stream_url: str

@router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_202_ACCEPTED)
async def chat(
    request: ChatRequest, 
    agent_usecase: AgentChatUseCase = Depends(get_agent_usecase),
    auth_service: AgentAuthorizationService = Depends(get_auth_service)
):
    """Generic chat endpoint."""
    # Rationale (Why): Security must be enforced before processing (Doc 19).
    await auth_service.assert_authorized(request.session_id, "chat")
    return await _handle_chat(request, agent_usecase)

@router.post("/sale-product/chat", response_model=ChatResponse, status_code=status.HTTP_202_ACCEPTED)
async def sale_product_chat(
    request: ChatRequest, 
    agent_usecase: AgentChatUseCase = Depends(get_agent_usecase),
    auth_service: AgentAuthorizationService = Depends(get_auth_service)
):
    """Product-specific chat endpoint (Document 06)."""
    await auth_service.assert_authorized(request.session_id, "sale-product")
    return await _handle_chat(request, agent_usecase)

@router.post("/reservation/chat", response_model=ChatResponse, status_code=status.HTTP_202_ACCEPTED)
async def reservation_chat(
    request: ChatRequest, 
    agent_usecase: AgentChatUseCase = Depends(get_agent_usecase),
    auth_service: AgentAuthorizationService = Depends(get_auth_service)
):
    """Reservation-specific chat endpoint (Document 07)."""
    await auth_service.assert_authorized(request.session_id, "reservation")
    return await _handle_chat(request, agent_usecase)

async def _handle_chat(request: ChatRequest, agent_usecase: AgentChatUseCase) -> ChatResponse:
    try:
        result = await agent_usecase.handle_chat_request(
            session_id=request.session_id,
            message=request.message,
            request_id=request.request_id,
            trace_id=request.trace_id
        )
        return ChatResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
