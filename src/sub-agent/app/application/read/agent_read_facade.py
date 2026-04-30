from typing import Optional, Dict, Any
from ...ports.interfaces import Store
from ...domain.models import AgentTask

class AgentReader:
    """
    Read-only port implementation for agent task state and history.
    """
    def __init__(self, store: Store):
        self.store = store

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = await self.store.load_task(task_id)
        if not task:
            return None
        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "result": task.result.model_dump() if task.result else None
        }
