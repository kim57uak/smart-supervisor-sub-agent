from typing import Dict, Any, List
from ...ports.orchestration_ports import SupervisorStateGraphFactory
from ...domain.models import FrozenExecutionPlan
from ..persistence.supervisor_execution_persistence_service import SupervisorExecutionPersistenceService
from ...ports.llm_ports import SupervisorResponseComposeService


from .supervisor_progress_publisher import SupervisorProgressPublisher
import structlog
logger = structlog.get_logger()

class SupervisorGraphExecutionService:
    def __init__(
        self, 
        graph_factory: SupervisorStateGraphFactory,
        persistence_facade: SupervisorExecutionPersistenceService,
        compose_service: SupervisorResponseComposeService,
        event_publisher: SupervisorProgressPublisher
    ):
        self.graph_factory = graph_factory
        self.persistence_facade = persistence_facade
        self.compose_service = compose_service
        self.event_publisher = event_publisher
        self.graph = self.graph_factory.create_graph()

    async def execute_plan(self, task_id: str, plan: FrozenExecutionPlan) -> Dict[str, Any]:
        initial_state = {
            "task_id": task_id,
            "plan": plan,
            "current_step_index": 0,
            "results": [],
            "final_answer": ""
        }
        
        try:
            final_state = await self.graph.ainvoke(initial_state)
            
            # Post-graph stream compose
            final_answer_parts = []
            async for event_type, token in self.compose_service.stream_compose(
                final_state["results"], 
                context={"task_id": task_id}
            ):
                if event_type == "reasoning":
                    await self.event_publisher.publish_reasoning(task_id, token)
                elif event_type == "a2ui":
                    import json
                    await self.event_publisher.publish_a2ui(task_id, json.loads(token))
                else:
                    # 'supervisor' key indicates the final aggregated answer
                    await self.event_publisher.publish_chunk(task_id, "supervisor", {"answer": token, "data": None})
                    final_answer_parts.append(token)
            
            final_answer = "".join(final_answer_parts)
            final_state["final_answer"] = final_answer
            
            # Persist completion
            await self.persistence_facade.persist_execution_completion(
                task_id, 
                {"results": final_state["results"], "final_answer": final_answer}
            )
            
            await self.event_publisher.publish_done(task_id, {
                "final_answer": final_answer,
                "results": final_state["results"]
            })
            
            return final_state
        except Exception as e:
            logger.error("graph_execution_failed", error=str(e), task_id=task_id)
            await self.event_publisher.publish_error(task_id, {"error": str(e)})
            return {"error": str(e)}
