import structlog
from typing import Dict, Any
from app.domain.enums import ProcessStatus, EventType, AgentRole
from app.ports.interfaces import ProgressPublisher
from app.adapters.orchestration.langgraph_factory import WorkflowFactory
from app.application.persistence.agent_persistence import AgentPersistence
from app.domain.models import AgentExecutionResult

logger = structlog.get_logger(__name__)

class AgentExecutor:
    """
    Orchestrates the execution of sub-agent tasks using LangGraph.
    Ensures mandatory Trace ID propagation (Document 02).
    """
    def __init__(
        self,
        factory: WorkflowFactory,
        persistence: AgentPersistence,
        publisher: ProgressPublisher
    ):
        self.graph = factory.create_graph()
        self.persistence = persistence
        self.publisher = publisher

    async def execute(self, session_id: str, task_id: str, message: str, trace_id: str = "unknown"):
        log = logger.bind(trace_id=trace_id, task_id=task_id, session_id=session_id)
        log.info("execution_started")

        # 1. Initialize State
        initial_state = {
            "task_id": task_id,
            "session_id": session_id,
            "trace_id": trace_id,
            "user_message": message,
            "history": [],
            "plans": [],
            "results": [],
            "final_answer": "",
            "status": ProcessStatus.RUNNING
        }

        try:
            # 2. Update status to RUNNING (Command via Persistence)
            await self.persistence.update_status(task_id, ProcessStatus.RUNNING)
            
            await self.publisher.publish(session_id, task_id, {
                "event_type": EventType.PROGRESS.value,
                "payload": {"status": ProcessStatus.RUNNING.value}
            }, trace_id=trace_id)

            # 3. Invoke LangGraph
            final_state = await self.graph.ainvoke(initial_state)

            # 4. Finalize Task (Command via Persistence)
            execution_result = AgentExecutionResult(
                task_id=task_id,
                final_answer=final_state.get("final_answer", ""),
                raw_data={"results": final_state.get("results", [])}
            )

            await self.persistence.complete_task(task_id, execution_result)

            await self.publisher.publish(session_id, task_id, {
                "event_type": EventType.DONE.value,
                "payload": {
                    "status": ProcessStatus.COMPLETED.value,
                    "final_answer": final_state.get("final_answer")
                }
            }, trace_id=trace_id)
            
            log.info("execution_completed")
            return final_state

        except Exception as e:
            log.error("execution_failed", error=str(e))
            await self.publisher.publish(session_id, task_id, {
                "event_type": EventType.ERROR.value,
                "payload": {"error": str(e)}
            }, trace_id=trace_id)
            raise
