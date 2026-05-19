"""
[Sub-Agent] 태스크 읽기 전용 파사드
====================================
책임: 태스크 상태/결과를 조회하는 읽기 전용 인터페이스 제공
아키텍처 위치: Application Layer — Read (CQRS의 Read Model)

CQRS 원칙:
  - 쓰기: AgentPersistence (Command)
  - 읽기: AgentReader (Query)
  - 동일한 Store를 사용하지만 의도적으로 인터페이스 분리
"""

from typing import Optional, Dict, Any
from ...ports.interfaces import Store
from ...domain.models import AgentTask

class AgentReader:
    """
    태스크 상태/결과 읽기 전용 파사드.
    Supervisor/API가 태스크 진행 상태를 조회할 때 사용.
    """
    def __init__(self, store: Store):
        self.store = store

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """태스크 상태 + 결과 조회"""
        task = await self.store.load_task(task_id)
        if not task:
            return None
        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "result": task.result.model_dump() if task.result else None
        }
