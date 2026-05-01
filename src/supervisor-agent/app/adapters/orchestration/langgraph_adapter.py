import structlog
from typing import Dict, Any
from ...ports.orchestration_ports import OrchestrationEngine, StateGraphFactory
from ...domain.models import FrozenExecutionPlan

logger = structlog.get_logger()

class LangGraphAdapter(OrchestrationEngine):
    """
    Adapter for LangGraph engine.
    Encapsulates LangGraph-specific orchestration logic.
    """
    def __init__(self, graph_factory: StateGraphFactory):
        self.graph_factory = graph_factory
        self.graph = self.graph_factory.create_graph()

    async def execute(self, 
                      session_id: str, 
                      task_id: str, 
                      plan: FrozenExecutionPlan, 
                      initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the LangGraph compiled graph.
        """
        logger.info("langgraph_execution_start", task_id=task_id)
        final_state = await self.graph.ainvoke(initial_state)
        logger.info("langgraph_execution_finished", task_id=task_id)
        return final_state
