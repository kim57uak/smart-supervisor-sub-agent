import structlog
from typing import Dict, Any
from app.core.config import settings
from app.domain.enums import ProcessStatus, EventType, AgentRole
from app.ports.interfaces import ProgressPublisher, OrchestrationEngine
from app.application.persistence.agent_persistence import AgentPersistence
from app.domain.models import AgentExecutionResult, Message

logger = structlog.get_logger(__name__)

class AgentExecutor:
    """
    Orchestrates the execution of sub-agent tasks using an abstract engine (LangGraph or Burr).
    Ensures mandatory Trace ID propagation (Document 02).
    """
    def __init__(
        self,
        engine: OrchestrationEngine,
        persistence: AgentPersistence,
        publisher: ProgressPublisher
    ):
        self.engine = engine
        self.persistence = persistence
        self.publisher = publisher

    async def execute(self, session_id: str, task_id: str, message: str, trace_id: str = "unknown"):
        log = logger.bind(trace_id=trace_id, task_id=task_id, session_id=session_id)
        log.info("execution_started", engine=settings.orchestration_engine)

        await self.persistence.store.save_message(
            session_id,
            {"role": AgentRole.USER.value, "content": message, "task_id": task_id},
        )
        raw_history = await self.persistence.store.get_messages(session_id, limit=20)
        history = [Message(role=h.get("role", AgentRole.USER.value), content=h.get("content", "")) for h in raw_history]

        # 1. Initialize State
        initial_state = {
            "task_id": task_id,
            "session_id": session_id,
            "trace_id": trace_id,
            "user_message": message,
            "history": history,
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

            # 3. Invoke Abstract Engine (LangGraph or Burr)
            # Rationale (Why): Abstraction allows framework flexibility (e.g., Burr's better state visualization).
            final_state = await self.engine.execute(session_id, task_id, initial_state)

            # 4. Finalize Task (Command via Persistence)
            execution_result = AgentExecutionResult(
                task_id=task_id,
                final_answer=final_state.get("final_answer", ""),
                raw_data={"results": final_state.get("results", [])}
            )

            await self.persistence.complete_task(task_id, execution_result)
            await self.persistence.store.save_message(
                session_id,
                {"role": AgentRole.ASSISTANT.value, "content": execution_result.final_answer, "task_id": task_id},
            )

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
