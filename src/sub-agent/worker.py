import asyncio
import structlog
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

from app.core.dependencies import resolve_worker_service
from app.infrastructure.redis_client import RedisClient

# Configure structlog
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)

logger = structlog.get_logger(__name__)

async def main():
    logger.info("initializing_subagent_worker")
    
    try:
        # Use dependency injection to resolve the worker service
        # This ensures all adapters and services are correctly wired as per Document 03
        worker = await resolve_worker_service()
        
        await worker.run_forever()
        
    except Exception as e:
        logger.error("worker_initialization_failed", error=str(e))
    finally:
        await RedisClient.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
