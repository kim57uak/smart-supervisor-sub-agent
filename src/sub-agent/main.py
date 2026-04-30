import uvicorn
import structlog
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, status, Request, Depends
from fastapi.responses import JSONResponse

# Load environment variables from .env
load_dotenv()

from app.api.agent import chat
from app.api.a2a import discovery
from app.api.support import stream
from app.api.support.a2a_handler import JsonRpcRequest, handle_a2a_request
from app.core.config import settings
from app.core.dependencies import (
    get_agent_usecase,
    get_redis_adapter
)
from app.infrastructure.redis_client import RedisClient
from app.domain.exceptions import BaseAgentException

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
                    "code": -32000, # Base agent error code
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
    
    from app.core.dependencies import get_agent_executor, get_auth_service
    from app.application.execution.executor import AgentExecutor
    from app.services.agent_authorization_service import AgentAuthorizationService

    @a2a_router.post("/product", status_code=status.HTTP_200_OK)
    async def product_agent(
        request: JsonRpcRequest,
        executor: AgentExecutor = Depends(get_agent_executor),
        auth: AgentAuthorizationService = Depends(get_auth_service)
    ):
        # Rationale (Why): Security check is mandatory at the entry point.
        await auth.assert_authorized(request.params.get("session_id", "default"), "sale-product")
        return await handle_a2a_request("sale-product", request, executor)

    @a2a_router.post("/reservation", status_code=status.HTTP_200_OK)
    async def reservation_agent(
        request: JsonRpcRequest,
        executor: AgentExecutor = Depends(get_agent_executor),
        auth: AgentAuthorizationService = Depends(get_auth_service)
    ):
        await auth.assert_authorized(request.params.get("session_id", "default"), "reservation")
        return await handle_a2a_request("reservation", request, executor)

    @a2a_router.post("/weather", status_code=status.HTTP_200_OK)
    async def weather_agent(
        request: JsonRpcRequest,
        executor: AgentExecutor = Depends(get_agent_executor),
        auth: AgentAuthorizationService = Depends(get_auth_service)
    ):
        await auth.assert_authorized(request.params.get("session_id", "default"), "weather")
        return await handle_a2a_request("weather", request, executor)

    @a2a_router.post("/supply-cost", status_code=status.HTTP_200_OK)
    async def supply_cost_agent(
        request: JsonRpcRequest,
        executor: AgentExecutor = Depends(get_agent_executor),
        auth: AgentAuthorizationService = Depends(get_auth_service)
    ):
        await auth.assert_authorized(request.params.get("session_id", "default"), "supply-cost")
        return await handle_a2a_request("supply-cost", request, executor)

    app.include_router(a2a_router, prefix="/a2a", tags=["a2a"])

    @app.get("/health")
    async def health():
        return {"status": "ok", "app": settings.app_name, "version": settings.version}

    return app

app = create_app()

if __name__ == "__main__":
    # Rationale (Why): Synchronized with Supervisor's routing config (8082).
    uvicorn.run(app, host="0.0.0.0", port=8082)
