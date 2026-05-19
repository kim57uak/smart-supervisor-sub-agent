import uvicorn
import structlog
import os
import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Load environment variables from .env
load_dotenv()

from app.core.config import settings
from app.api import supervisor
from app.infrastructure.redis.redis_client import RedisClient
from app.adapters.llm.llm_planning_service import LlmPlanningService

logger = structlog.get_logger()

def create_app():
    # Configure Structured Logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: Pre-load agent cards (Discovery)
        # Rationale (Why): Self-healing discovery to ensure cards are ready for planning.
        try:
            asyncio.create_task(LlmPlanningService.load_agent_cards())
        except Exception as e:
            logger.error("discovery_initialization_failed", error=str(e))
        yield
        # Shutdown logic if any

    app = FastAPI(
        title=settings.app_name, 
        version=settings.version, 
        debug=settings.debug,
        lifespan=lifespan
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_hosts,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Router Inclusion
    app.include_router(
        supervisor.router, 
        prefix=settings.api_prefix,
        tags=["supervisor"]
    )

    # Static Files
    static_dir = os.path.join(os.path.dirname(__file__), "app", "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/health")
    async def health():
        return {"status": "ok", "app": settings.app_name, "version": settings.version}

    @app.get("/")
    async def root():
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"status": "ok", "message": "Supervisor API is running."}

    return app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
