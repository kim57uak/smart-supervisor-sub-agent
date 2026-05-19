"""
[Sub-Agent] 사용자 채팅 API 엔드포인트
=======================================
책임: 사용자/슈퍼바이저의 채팅 요청을 수신하고 비동기 태스크로 처리
아키텍처 위치: API Layer — Inbound Adapter (REST → Application)

엔드포인트:
  POST /api/v1/agent/chat            — 일반 채팅 (scope: chat)
  POST /api/v1/agent/sale-product/chat — 상품 전용 채팅 (scope: sale-product)
  POST /api/v1/agent/reservation/chat  — 예약 전용 채팅 (scope: reservation)

처리 흐름 (202 Accepted):
  1. auth_service.assert_authorized() → scope 기반 권한 검증
  2. AgentChatUseCase.handle_chat_request() → Idempotency 체크 + 큐잉
  3. 즉시 202 Accepted + task_id 반환
  4. Worker가 백그라운드에서 실제 실행
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from app.application.execution.chat_usecase import AgentChatUseCase
from app.services.agent_authorization_service import AgentAuthorizationService
from app.core.dependencies import get_agent_usecase, get_auth_service

router = APIRouter()

class ChatRequest(BaseModel):
    """채팅 요청 body — session_id는 UI에서 생성, 서버 생성 금지"""
    session_id: str
    message: str
    request_id: Optional[str] = None
    trace_id: Optional[str] = None

class ChatResponse(BaseModel):
    """202 Accepted 응답 — task_id로 이후 상태 조회"""
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
    """일반 채팅 요청 처리 (scope: chat)"""
    await auth_service.assert_authorized(request.session_id, "chat")
    return await _handle_chat(request, agent_usecase)

@router.post("/sale-product/chat", response_model=ChatResponse, status_code=status.HTTP_202_ACCEPTED)
async def sale_product_chat(
    request: ChatRequest, 
    agent_usecase: AgentChatUseCase = Depends(get_agent_usecase),
    auth_service: AgentAuthorizationService = Depends(get_auth_service)
):
    """상품 전용 채팅 요청 처리 (scope: sale-product)"""
    await auth_service.assert_authorized(request.session_id, "sale-product")
    return await _handle_chat(request, agent_usecase)

@router.post("/reservation/chat", response_model=ChatResponse, status_code=status.HTTP_202_ACCEPTED)
async def reservation_chat(
    request: ChatRequest, 
    agent_usecase: AgentChatUseCase = Depends(get_agent_usecase),
    auth_service: AgentAuthorizationService = Depends(get_auth_service)
):
    """예약 전용 채팅 요청 처리 (scope: reservation)"""
    await auth_service.assert_authorized(request.session_id, "reservation")
    return await _handle_chat(request, agent_usecase)

async def _handle_chat(request: ChatRequest, agent_usecase: AgentChatUseCase) -> ChatResponse:
    """공통 채팅 처리 로직 — UseCase 위임 후 응답 매핑"""
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
