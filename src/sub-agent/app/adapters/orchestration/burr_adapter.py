import structlog
from typing import Dict, Any
from ...ports.interfaces import OrchestrationEngine

logger = structlog.get_logger()

from .burr_factory import BurrWorkflowFactory

class BurrAdapter(OrchestrationEngine):
    """
    Adapter for Burr engine in Sub-Agent.
    """
    def __init__(self, factory: BurrWorkflowFactory):
        self.factory = factory

    async def execute(self, 
                      session_id: str, 
                      task_id: str, 
                      initial_state: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("subagent_burr_execution_start", task_id=task_id)
        
        # Rationale (Why): trace_id is essential for cross-agent tracking.
        trace_id = initial_state.get("trace_id", "unknown")
        
        # Rationale (Why): We merge defaults with initial_state to ensure keys exist without duplicates.
        state_to_inject = {
            "plans": [],
            "history": [],
            "loop_count": 0,
            **initial_state
        }
        
        app = (
            self.factory.create_application_builder(session_id, task_id, trace_id)
            .with_state(**state_to_inject)
            .build()
        )


        


        
        # Rationale (Why): Burr's arun() returns the final result and state.
        last_action, result, state = await app.arun(
            halt_after=["compose_response"]
        )
        
        logger.info("subagent_burr_execution_finished", task_id=task_id, last_action=last_action)
        
        # Rationale (Why): Burr State can be converted to a dictionary using .get_all().
        return state.as_dict() if hasattr(state, "as_dict") else dict(state.items())



