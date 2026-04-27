from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import structlog
import os

from .core.config import settings
from .api import supervisor
from .infrastructure.redis.redis_client import RedisClient

# Configure logging
structlog.configure()
logger = structlog.get_logger()

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    debug=settings.debug
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_hosts,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(
    supervisor.router, 
    prefix=settings.api_prefix,
    tags=["supervisor"]
)

# Mount Static Files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"status": "ok", "message": "API is running. UI not found."}


@app.on_event("startup")
async def startup_event():
    logger.info("Starting up supervisor agent...")
    # Initialize Redis
    await RedisClient.get_client()
    
    # A2A Standard: Load downstream agent cards at startup
    try:
        from .adapters.llm.llm_planning_service import LlmSupervisorPlanningService
        await LlmSupervisorPlanningService.load_agent_cards()
        logger.info("A2A agent cards pre-loaded successfully")
    except Exception as e:
        logger.error("Failed to pre-load agent cards", error=str(e))


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down supervisor agent...")
    await RedisClient.close()


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": settings.version}
