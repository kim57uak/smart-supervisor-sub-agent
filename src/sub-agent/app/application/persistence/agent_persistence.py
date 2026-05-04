from typing import Dict, Any, Optional
from ...ports.interfaces import Store
from ...domain.models import AgentTask, AgentExecutionResult
from ...domain.enums import ProcessStatus
from .execution_consistency_coordinator import ExecutionConsistencyCoordinator

class AgentPersistence:
    """
    Handles atomic state updates and session persistence.
    """
    def __init__(self, store: Store):
        self.store = store
        self.state = ExecutionConsistencyCoordinator(store)

    async def complete_task(self, task_id: str, result: AgentExecutionResult) -> bool:
        # Rationale (Why): Using atomic_transition to ensure no race conditions during completion.
        def update_result(task: AgentTask):
            task.result = result
            
        return await self.state.atomic_transition(
            task_id, 
            ProcessStatus.COMPLETED, 
            update_fn=update_result
        )
            
    async def update_status(self, task_id: str, status: ProcessStatus) -> bool:
        return await self.state.atomic_transition(task_id, status)
