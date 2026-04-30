import asyncio
import structlog
import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings
from app.core.dependencies import (
    get_task_queue_service,
    get_supervisor_graph_execution_service,
    get_worker_execution_service
)
from app.domain.models import FrozenExecutionPlan
from app.domain.enums import ProcessStatus

# Configure Structured Logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)

logger = structlog.get_logger(__name__)

async def main():
    # Initialize services
    # Rationale (Why): Use get_worker_execution_service for clean dependency assembly 
    # outside of the FastAPI request context.
    worker_service = await get_worker_execution_service()
    
    logger.info("supervisor_worker_standalone_started")
    await worker_service.run_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
