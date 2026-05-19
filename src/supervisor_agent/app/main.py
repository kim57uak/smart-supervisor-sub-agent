from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import structlog
import os
from contextlib import asynccontextmanager
import asyncio
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

from .core.config import settings
from .api import supervisor
from .infrastructure.redis.redis_client import RedisClient

# Configure Structured Logging (Enterprise Standard)
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI Lifecycle Manager:
    Initializes and cleans up infrastructure during server startup and shutdown.
    """
    logger.info("startup_initiated", app=settings.app_name, version=settings.version)
    
    # 1. Initialize Redis
    await RedisClient.get_client()
    
    # 2. Pre-load A2A Agent Cards
    try:
        from .adapters.llm.llm_planning_service import LlmPlanningService
        await LlmPlanningService.load_agent_cards()
        logger.info("agent_cards_preloaded")
    except Exception as e:
        logger.error("agent_cards_preload_failed", error=str(e))
    
    # 3. Start Embedded Worker if enabled
    worker_task = None
    if settings.embedded_worker_enabled:
        from .core.dependencies import get_worker_execution_service
        worker_service = await get_worker_execution_service()
        worker_task = asyncio.create_task(worker_service.run_forever())
        logger.info("embedded_worker_started")
    
    yield
    
    # Graceful Shutdown
    logger.info("shutdown_initiated")
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    await RedisClient.close()

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    debug=settings.debug,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_hosts,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    supervisor.router, 
    prefix=settings.api_prefix,
    tags=["supervisor"]
)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"status": "ok", "message": "API is running."}

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": settings.version}
