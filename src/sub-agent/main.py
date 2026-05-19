"""
[Sub-Agent] FastAPI 애플리케이션 메인 진입점
===============================================
책임: HTTP 서버 초기화, 라우팅 등록, 글로벌 예외 처리, A2A 엔드포인트 바인딩
아키텍처 위치: API Gateway Layer (최상위)
관련 문서: Document 03(Component Architecture), 08(A2A Protocol), 10(Exception Translator), 22(Discovery)

주요 흐름:
  1. create_app() → FastAPI 인스턴스 생성
  2. 각종 라우터 등록 (chat, discovery, stream, a2a)
  3. 글로벌 예외 핸들러가 도메인 예외 → A2A JSON-RPC 에러 변환
  4. /health 엔드포인트로 헬스 체크
"""

import uvicorn
import structlog
import json
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, status, Request, Depends
from fastapi.responses import JSONResponse

# .env 파일 로드 (환경 변수 설정)
load_dotenv()

from app.core.config import settings
from app.api.agent import chat
from app.api.a2a import discovery
from app.api.support import stream
from app.api.support.a2a_handler import JsonRpcRequest, handle_a2a_request, JsonRpcResponse
from app.core.dependencies import (
    get_agent_usecase,
    get_redis_adapter,
    get_agent_executor, 
    get_auth_service
)
from app.infrastructure.redis_client import RedisClient
from app.domain.exceptions import BaseAgentException
from app.domain.enums import JsonRpcErrorCode
from app.application.execution.executor import AgentExecutor
from app.services.agent_authorization_service import AgentAuthorizationService

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 애플리케이션 라이프사이클 관리자.
    - Startup: 공유 인프라 초기화 (필요시)
    - Shutdown: Redis 연결 종료 등 정리 작업
    """
    yield
    # 애플리케이션 종료 시 Redis 연결 해제
    await RedisClient.close()

def create_app():
    """
    FastAPI 애플리케이션 팩토리 함수.
    설정 → 로깅 → 라우터 등록 → 예외 핸들러 → 앱 반환 순서로 초기화.
    팩토리 패턴 사용 이유: 테스트 시 mock 주입이 가능하도록 하기 위함.
    """
    # structlog 설정 (ISO 타임스탬프 + JSON 포맷)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )

    app = FastAPI(
        title=settings.app_name, 
        version=settings.version,
        lifespan=lifespan
    )

    # [글로벌 예외 핸들러]
    # 목적: 도메인 예외(BaseAgentException)를 A2A JSON-RPC 규격 에러 응답으로 변환
    # 위치: 애플리케이션 진입점에서 모든 하위 레이어 예외를 일괄 처리
    @app.exception_handler(BaseAgentException)
    async def agent_exception_handler(request: Request, exc: BaseAgentException):
        return JSONResponse(
            status_code=400 if exc.code == "INVALID_PARAMS" else 500,
            content={
                "jsonrpc": "2.0",
                "error": {
                    "code": JsonRpcErrorCode.AGENT_BASE_ERROR.value, 
                    "message": exc.message,
                    "data": {"code": exc.code, "details": exc.details}
                },
                "id": None
            }
        )

    # 1. 사용자/슈퍼바이저용 Chat API (/api/v1/agent/chat)
    app.include_router(chat.router, prefix=f"{settings.api_prefix}/agent", tags=["agent"])

    # 2. A2A Discovery (/well-known/agent-card.json) — Agent Card 조회
    app.include_router(discovery.router, prefix="/.well-known", tags=["discovery"])

    # 3. SSE Streaming (/api/v1/stream/{task_id}) — 실시간 이벤트 스트리밍
    app.include_router(stream.router, prefix=f"{settings.api_prefix}/stream", tags=["stream"])

    # 4. A2A Agent-to-Agent 엔드포인트 (/a2a/{agent_type})
    # 각 POST 엔드포인트는 JSON-RPC 2.0 요청을 받아 특정 Agent로 라우팅
    # 응답은 202 Accepted (비동기) 또는 동기 완료 응답
    a2a_router = APIRouter()
    
    async def generic_a2a_handler(
        agent_key: str,
        request: JsonRpcRequest,
        executor: AgentExecutor,
        auth: AgentAuthorizationService
    ):
        """
        모든 A2A 에이전트의 공통 요청 처리기.
        - session_id 검증 (필수, UI에서 생성)
        - 권한 검사 (scope 기반)
        - A2A 요청 처리 후 응답 반환
        """
        logger.info("a2a_request_received", agent=agent_key, params_keys=list((request.params or {}).keys()))
        
        session_id = str((request.params or {}).get("session_id") or "")
        
        if not session_id:
            return JsonRpcResponse(
                jsonrpc="2.0",
                error={"code": JsonRpcErrorCode.INVALID_PARAMS.value, "message": "session_id is required"},
                id=request.id
            )
            
        request.params["session_id"] = session_id
        await auth.assert_authorized(session_id, agent_key)
        return await handle_a2a_request(agent_key, request, executor)

    @a2a_router.post("/product")
    async def product_agent(request: JsonRpcRequest, e=Depends(get_agent_executor), a=Depends(get_auth_service)):
        return await generic_a2a_handler("sale-product", request, e, a)

    @a2a_router.post("/reservation")
    async def reservation_agent(request: JsonRpcRequest, e=Depends(get_agent_executor), a=Depends(get_auth_service)):
        return await generic_a2a_handler("reservation", request, e, a)

    @a2a_router.post("/weather")
    async def weather_agent(request: JsonRpcRequest, e=Depends(get_agent_executor), a=Depends(get_auth_service)):
        return await generic_a2a_handler("weather", request, e, a)

    @a2a_router.post("/supply-cost")
    async def supply_cost_agent(request: JsonRpcRequest, e=Depends(get_agent_executor), a=Depends(get_auth_service)):
        return await generic_a2a_handler("supply-cost", request, e, a)

    app.include_router(a2a_router, prefix="/a2a", tags=["a2a"])

    @app.get("/health")
    async def health():
        return {"status": "ok", "app": settings.app_name, "version": settings.version}

    return app

app = create_app()

if __name__ == "__main__":
    # Supervisor(8081)와 동기화된 포트(8082)로 실행
    uvicorn.run(app, host="0.0.0.0", port=8082)
