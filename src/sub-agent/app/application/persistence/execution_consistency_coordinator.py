"""
[Sub-Agent] 실행 일관성 코디네이터 — 낙관적 락 기반 원자적 상태 전이
===================================================================
책임: Redis CAS(Check-And-Set) 패턴으로 태스크 상태 변경의 원자성 보장
아키텍처 위치: Application Layer — Persistence (Store 위의 일관성 계층)

낙관적 락 동작:
  1. load_task() — 최신 상태 조회 + 현재 state_version 확인
  2. 메모리 상에서 status 변경 + update_fn 적용
  3. state_version +1 증가
  4. save_task() — Store 내부에서 WATCH/MULTI/EXEC로 CAS 수행
  5. version 충돌 시 재시도 (RedisAdapter.save_task의 retry loop)

멱등성(Idempotency):
  - 이미 target_status인 경우 → true 반환 (저장 생략)
  - version이 서버의 현재 version보다 낮으면 → ValueError 발생 → 재시도
"""

import asyncio
import structlog
from typing import Optional, Dict, Any, Callable, Awaitable
from app.ports.interfaces import Store
from app.domain.models import AgentTask
from app.domain.enums import ProcessStatus

logger = structlog.get_logger(__name__)

class ExecutionConsistencyCoordinator:
    """
    Redis CAS(WATCH/MULTI/EXEC) 기반 원자적 상태 전이.
    동시성 충돌을 감지하고 재시도하는 일관성 계층.
    """
    def __init__(self, store: Store):
        self.store = store

    async def atomic_transition(
        self, 
        task_id: str, 
        target_status: ProcessStatus,
        update_fn: Optional[Callable[[AgentTask], None]] = None
    ) -> bool:
        """
        낙관적 락 업데이트 수행.
        Load → Modify(callback) → Save(CAS) → 완료/재시도
        """
        task = await self.store.load_task(task_id)
        if not task:
            logger.error("task_not_found_for_transition", task_id=task_id)
            return False

        if task.status == target_status:
            logger.info("task_already_in_target_status", task_id=task_id, status=target_status.value)
            return True

        task.status = target_status
        if update_fn:
            update_fn(task)
        
        task.state_version += 1
        
        try:
            await self.store.save_task(task)
            logger.info("atomic_transition_success", task_id=task_id, to_status=target_status.value)
            return True
        except Exception as e:
            logger.error("atomic_transition_failed", task_id=task_id, error=str(e))
            return False
