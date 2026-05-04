import uvicorn
import structlog
import json
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, status, Request, Depends
from fastapi.responses import JSONResponse

# Load environment variables from .env
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
    # Startup: Initialize shared infrastructure
    yield
    # Shutdown: Close connections
    await RedisClient.close()

def create_app():
    # Configure logging
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

    # Global Exception Handler (Document 10: Exception Translator)
    @app.exception_handler(BaseAgentException)
    async def agent_exception_handler(request: Request, exc: BaseAgentException):
        # Rationale (Why): Internal exceptions must be translated to standard A2A error formats.
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

    # 1. User-facing chat endpoint
    app.include_router(chat.router, prefix=f"{settings.api_prefix}/agent", tags=["agent"])

    # 2. A2A Discovery endpoint (Canonical path: Document 22)
    app.include_router(discovery.router, prefix="/.well-known", tags=["discovery"])

    # 3. Streaming endpoint (Document 09)
    app.include_router(stream.router, prefix=f"{settings.api_prefix}/stream", tags=["stream"])

    # 4. A2A Agent endpoints (Doc 08: 202 Accepted expected)
    a2a_router = APIRouter()
    
    async def generic_a2a_handler(
        agent_key: str,
        request: JsonRpcRequest,
        executor: AgentExecutor,
        auth: AgentAuthorizationService
    ):
        """
        Generic handler for A2A requests to reduce code duplication (DRY).
        Rationale (Why): Centralizing the session resolution and auth logic ensures consistent security across all agents.
        """
        logger.info("a2a_request_received", agent=agent_key, params_keys=list((request.params or {}).keys()))
        
        # Rationale (Why): session_id is mandatory and must be UI-provided.
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
    # Rationale (Why): Synchronized with Supervisor's routing config (8082).
    uvicorn.run(app, host="0.0.0.0", port=8082)
