import structlog
from typing import Dict, Any, Optional
from ...ports.orchestration_ports import OrchestrationEngine
from ...ports.store_ports import GraphCheckpointStore
from ...domain.models import FrozenExecutionPlan
from .burr_factory import BurrWorkflowFactory

logger = structlog.get_logger()

class BurrAdapter(OrchestrationEngine):
    """
    Adapter for Burr engine with checkpoint save/restore (M3).
    """
    def __init__(self, factory: BurrWorkflowFactory, checkpoint_store: Optional[GraphCheckpointStore] = None):
        self.factory = factory
        self.checkpoint_store = checkpoint_store

    async def execute(self, 
                      session_id: str, 
                      task_id: str, 
                      plan: FrozenExecutionPlan, 
                      initial_state: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("burr_execution_start", task_id=task_id)

        # Restore checkpoint if available
        if self.checkpoint_store:
            checkpoint = await self.checkpoint_store.get_checkpoint(session_id, task_id)
            if checkpoint:
                initial_state.update(checkpoint)
                logger.info("checkpoint_restored", task_id=task_id)

        app = (
            self.factory.create_application_builder(session_id, task_id)
            .with_state(**initial_state)
            .build()
        )

        last_action, result, state = await app.arun(
            halt_after=["terminal"]
        )

        logger.info("burr_execution_finished", task_id=task_id, last_action=last_action)

        final_state = state.as_dict() if hasattr(state, "as_dict") else dict(state.items())

        # Save post-execution checkpoint
        if self.checkpoint_store:
            await self.checkpoint_store.save_checkpoint(session_id, task_id, final_state)

        return final_state
