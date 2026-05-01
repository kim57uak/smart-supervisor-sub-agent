import structlog
from typing import Dict, Any
from ...ports.interfaces import OrchestrationEngine

logger = structlog.get_logger()

class LangGraphAdapter(OrchestrationEngine):
    """
    Adapter for LangGraph engine in Sub-Agent.
    """
    def __init__(self, graph_factory):
        self.graph_factory = graph_factory
        self.graph = self.graph_factory.create_graph()

    async def execute(self, 
                      session_id: str, 
                      task_id: str, 
                      initial_state: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("subagent_langgraph_execution_start", task_id=task_id)
        final_state = await self.graph.ainvoke(initial_state)
        logger.info("subagent_langgraph_execution_finished", task_id=task_id)
        return final_state
