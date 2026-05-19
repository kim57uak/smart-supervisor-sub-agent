import asyncio
import structlog
from typing import Dict, Any, Optional
from ...ports.orchestration_ports import OrchestrationEngine, StateGraphFactory
from ...ports.store_ports import GraphCheckpointStore
from ...domain.models import FrozenExecutionPlan

logger = structlog.get_logger()


class LangGraphAdapter(OrchestrationEngine):
    """
    Adapter for LangGraph engine with checkpoint save/restore (M3).
    """
    def __init__(self, graph_factory: StateGraphFactory, checkpoint_store: Optional[GraphCheckpointStore] = None):
        self.graph_factory = graph_factory
        self.checkpoint_store = checkpoint_store
        self._graph = None

    @property
    def graph(self):
        if self._graph is None:
            self._graph = self.graph_factory.create_graph()
        return self._graph

    async def execute(
        self,
        session_id: str,
        task_id: str,
        plan: FrozenExecutionPlan,
        initial_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info("langgraph_execution_start", task_id=task_id)
        timeout_ms = plan.execution_constraints.invoke_timeout_ms

        # Restore checkpoint if available
        if self.checkpoint_store:
            checkpoint = await self.checkpoint_store.get_checkpoint(session_id, task_id)
            if checkpoint:
                initial_state.update(checkpoint)
                logger.info("checkpoint_restored", task_id=task_id)

        try:
            final_state = await asyncio.wait_for(
                self.graph.ainvoke(initial_state),
                timeout=timeout_ms / 1000
            )
            logger.info("langgraph_execution_finished", task_id=task_id)

            # Save post-execution checkpoint
            if self.checkpoint_store:
                await self.checkpoint_store.save_checkpoint(session_id, task_id, final_state)

            return final_state
        except asyncio.TimeoutError:
            logger.error("langgraph_execution_timeout", task_id=task_id, timeout_ms=timeout_ms)
            return {"error": f"Graph execution timed out after {timeout_ms}ms"}
