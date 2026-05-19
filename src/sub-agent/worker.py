"""
[Sub-Agent] 백그라운드 워커 프로세스
======================================
책임: Redis 작업 큐를 폴링하여 에이전트 태스크를 비동기 실행
아키텍처 위치: Application Layer — Decoupled Worker
실행 방식: main.py(FastAPI)와 별도 프로세스로 동작. start.sh에서 다중 워커 기동.

워커 생명주기:
  1. resolve_worker_service() → DI로 전체 의존성 wiring
  2. run_forever() → Redis BRPOPLPUSH로 태스크 폴링
  3. 각 태스크 → AgentExecutor.execute() 위임
  4. 성공 → ACK(processing → 제거), 실패 → NACK(processing → queue 재등록)
"""

import asyncio
import structlog
import os
from dotenv import load_dotenv

load_dotenv()

from app.core.dependencies import resolve_worker_service
from app.infrastructure.redis_client import RedisClient

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)

logger = structlog.get_logger(__name__)

async def main():
    """워커 메인: DI 컨테이너 초기화 → 무한 폴링 루프 진입"""
    logger.info("initializing_subagent_worker")
    
    try:
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
