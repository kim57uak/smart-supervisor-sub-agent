import uvicorn
import structlog
import json
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
from app.core.config import settings

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
    from app.api.support.a2a_handler import JsonRpcResponse

    def extract_session_id(params: dict) -> str:
        sid = params.get("session_id")
        if sid:
            return str(sid)
        message = params.get("message")
        if isinstance(message, dict):
            metadata = message.get("metadata")
            if isinstance(metadata, dict):
                msid = metadata.get("session_id")
                if msid:
                    return str(msid)
            parts = message.get("parts", [])
            if isinstance(parts, list):
                for part in parts:
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text")
                    if not isinstance(text, str):
                        continue
                    try:
                        decoded = json.loads(text)
                        if isinstance(decoded, dict):
                            dsid = decoded.get("session_id")
                            if dsid:
                                return str(dsid)
                    except Exception:
                        continue
        return ""

    async def resolve_session_id(params: dict) -> str:
        sid = extract_session_id(params)
        if sid:
            return sid

        task_id = str((params or {}).get("task_id", "")).strip()
        if not task_id:
            return ""

        try:
            redis = await RedisClient.get_client()
            idx_key = f"{settings.redis_prefix}:supervisor:index:task_session:{task_id}"
            raw = await redis.get(idx_key)
            if isinstance(raw, bytes):
                raw = raw.decode()
            return str(raw or "")
        except Exception:
            return ""

    @a2a_router.post("/product", status_code=status.HTTP_200_OK)
    async def product_agent(
        request: JsonRpcRequest,
        executor: AgentExecutor = Depends(get_agent_executor),
        auth: AgentAuthorizationService = Depends(get_auth_service)
    ):
        # Rationale (Why): Security check is mandatory at the entry point.
        logger.info("a2a_product_request_received", params_keys=list((request.params or {}).keys()))
        session_id = await resolve_session_id(request.params or {})
        logger.info("a2a_product_session_resolved", resolved=bool(session_id), session_id=session_id or "")
        if not session_id:
            return JsonRpcResponse(
                jsonrpc="2.0",
                error={"code": -32602, "message": "session_id is required"},
                id=request.id
            )
        request.params["session_id"] = session_id
        await auth.assert_authorized(session_id, "sale-product")
        return await handle_a2a_request("sale-product", request, executor)

    @a2a_router.post("/reservation", status_code=status.HTTP_200_OK)
    async def reservation_agent(
        request: JsonRpcRequest,
        executor: AgentExecutor = Depends(get_agent_executor),
        auth: AgentAuthorizationService = Depends(get_auth_service)
    ):
        logger.info("a2a_reservation_request_received", params_keys=list((request.params or {}).keys()))
        session_id = await resolve_session_id(request.params or {})
        logger.info("a2a_reservation_session_resolved", resolved=bool(session_id), session_id=session_id or "")
        if not session_id:
            return JsonRpcResponse(
                jsonrpc="2.0",
                error={"code": -32602, "message": "session_id is required"},
                id=request.id
            )
        request.params["session_id"] = session_id
        await auth.assert_authorized(session_id, "reservation")
        return await handle_a2a_request("reservation", request, executor)

    @a2a_router.post("/weather", status_code=status.HTTP_200_OK)
    async def weather_agent(
        request: JsonRpcRequest,
        executor: AgentExecutor = Depends(get_agent_executor),
        auth: AgentAuthorizationService = Depends(get_auth_service)
    ):
        session_id = await resolve_session_id(request.params or {})
        if not session_id:
            return JsonRpcResponse(
                jsonrpc="2.0",
                error={"code": -32602, "message": "session_id is required"},
                id=request.id
            )
        request.params["session_id"] = session_id
        await auth.assert_authorized(session_id, "weather")
        return await handle_a2a_request("weather", request, executor)

    @a2a_router.post("/supply-cost", status_code=status.HTTP_200_OK)
    async def supply_cost_agent(
        request: JsonRpcRequest,
        executor: AgentExecutor = Depends(get_agent_executor),
        auth: AgentAuthorizationService = Depends(get_auth_service)
    ):
        session_id = await resolve_session_id(request.params or {})
        if not session_id:
            return JsonRpcResponse(
                jsonrpc="2.0",
                error={"code": -32602, "message": "session_id is required"},
                id=request.id
            )
        request.params["session_id"] = session_id
        await auth.assert_authorized(session_id, "supply-cost")
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
