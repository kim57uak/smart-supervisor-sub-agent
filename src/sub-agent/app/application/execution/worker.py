"""
[Sub-Agent] 백그라운드 워커 실행 서비스
=========================================
책임: Redis 작업 큐를 폴링하여 태스크를 순차 실행 (At-Least-Once Delivery)
아키텍처 위치: Application Layer — Execution (Decoupled Worker 패턴)

처리 루프:
  1. TaskQueue.dequeue() — BRPOPLPUSH로 태스크 조회
  2. _process_task() — AgentExecutor.execute() 호출
  3. 성공 → TaskQueue.ack() — processing queue에서 제거
  4. 실패 → TaskQueue.nack() — processing → main queue 재등록 (재시도)

Reliable Queue 패턴:
  - dequeue가 태스크를 'main queue' → 'processing queue'로 원자적 이동
  - ack: 성공 시 processing queue에서 제거
  - nack: 실패 시 processing queue → main queue 재등록
  - Worker 크래시 시 processing queue의 태스크는 TTL 후 재처리 가능
"""

import asyncio
import structlog
from typing import Dict, Any
from .executor import AgentExecutor
from ...ports.interfaces import ProgressPublisher, TaskQueue

logger = structlog.get_logger(__name__)

class WorkerExecutionService:
    """
    서브에이전트 백그라운드 워커.
    BRPOPLPUSH → execute → ACK/NACK 무한 루프.
    """
    def __init__(
        self,
        task_queue: TaskQueue,
        executor: AgentExecutor,
        publisher: ProgressPublisher
    ):
        self.task_queue = task_queue
        self.executor = executor
        self.publisher = publisher

    async def run_forever(self):
        """워커 메인 루프 — 중단 없이 실행"""
        logger.info("subagent_worker_started")
        while True:
            task_msg = None
            try:
                task_msg = await self.task_queue.dequeue(timeout=5)
                if not task_msg:
                    continue

                await self._process_task(task_msg)
                await self.task_queue.ack(task_msg)
                
            except Exception as e:
                logger.error("worker_loop_error", error=str(e))
                if task_msg:
                    await self.task_queue.nack(task_msg)
                await asyncio.sleep(1)

    async def _process_task(self, task_msg: Dict[str, Any]):
        """개별 태스크 처리. 예외 발생 시 바깥 루프에서 NACK 처리."""
        session_id = task_msg.get("session_id")
        task_id = task_msg.get("task_id")
        message = task_msg.get("message")
        trace_id = task_msg.get("trace_id", "unknown")
        
        logger.info("processing_task", task_id=task_id, session_id=session_id, trace_id=trace_id)
        
        await self.executor.execute(session_id, task_id, message, trace_id=trace_id)
