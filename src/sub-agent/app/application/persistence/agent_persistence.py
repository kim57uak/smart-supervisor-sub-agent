"""
[Sub-Agent] 영속성 서비스 — 원자적 상태 전이 관리
==================================================
책임: 태스크 상태 변경을 원자적으로 처리 (낙관적 락 기반)
아키텍처 위치: Application Layer — Persistence

상태 전이 규칙:
  ACCEPTED → RUNNING → COMPLETED  (정상)
  ACCEPTED → RUNNING → FAILED     (실패)
  ACCEPTED → RUNNING → WAITING_REVIEW (HITL)

완료(complete_task) 시 result 업데이트 + COMPLETED 천이를 하나의 원자 연산으로 처리.
"""

from typing import Dict, Any, Optional
from ...ports.interfaces import Store
from ...domain.models import AgentTask, AgentExecutionResult
from ...domain.enums import ProcessStatus
from .execution_consistency_coordinator import ExecutionConsistencyCoordinator

class AgentPersistence:
    """
    태스크 영속성 + 원자적 상태 전이.
    Store(Redis Adapter) 위에 상태 전이 규칙을 레이어링.
    """
    def __init__(self, store: Store):
        self.store = store
        self.state = ExecutionConsistencyCoordinator(store)

    async def complete_task(self, task_id: str, result: AgentExecutionResult) -> bool:
        """완료 처리: 상태 이동 + 결과 저장을 원자적으로 수행"""
        def update_result(task: AgentTask):
            task.result = result
            
        return await self.state.atomic_transition(
            task_id, 
            ProcessStatus.COMPLETED, 
            update_fn=update_result
        )
            
    async def update_status(self, task_id: str, status: ProcessStatus) -> bool:
        """상태 변경만 수행"""
        return await self.state.atomic_transition(task_id, status)
