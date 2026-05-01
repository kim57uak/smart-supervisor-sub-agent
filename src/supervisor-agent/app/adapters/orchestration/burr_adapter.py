import structlog
from typing import Dict, Any
from ...ports.orchestration_ports import OrchestrationEngine
from ...domain.models import FrozenExecutionPlan
from .burr_factory import BurrWorkflowFactory

logger = structlog.get_logger()

class BurrAdapter(OrchestrationEngine):
    """
    Adapter for Burr engine.
    Implements real orchestration logic using Burr framework.
    """
    def __init__(self, factory: BurrWorkflowFactory):
        self.factory = factory

    async def execute(self, 
                      session_id: str, 
                      task_id: str, 
                      plan: FrozenExecutionPlan, 
                      initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the Burr application logic.
        """
        logger.info("burr_execution_start", task_id=task_id)
        
        # Rationale (Why): Build and run the Burr application using the factory.
        app = (
            self.factory.create_application_builder(session_id, task_id)
            .with_state(**initial_state)
            .build()
        )
        
        # Burr's arun() returns the last action, result, and final state.
        last_action, result, state = await app.arun(
            halt_after=["terminal"]
        )
        
        logger.info("burr_execution_finished", task_id=task_id, last_action=last_action)
        
        # Rationale (Why): Return final state dictionary for the service.
        return state.as_dict() if hasattr(state, "as_dict") else dict(state.items())
