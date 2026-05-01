import json
import structlog
from typing import Dict, Any, List, Optional, AsyncIterator

from ...core.config import settings
from ...ports.orchestration_ports import OrchestrationEngine
from ...domain.models import FrozenExecutionPlan
from ..persistence.supervisor_execution_persistence_service import SupervisorExecutionPersistenceService
from ...ports.llm_ports import ResponseComposeService
from ...ports.store_ports import ConversationStore
from .supervisor_progress_publisher import SupervisorProgressPublisher
from ...domain.enums import ProcessStatus

logger = structlog.get_logger()


class SupervisorGraphExecutionService:
    """
    Orchestrates the execution of agent graphs and handles result composition.
    Uses an abstract OrchestrationEngine (Strategy Pattern) to support multiple frameworks.
    """

    def __init__(
        self,
        engine: OrchestrationEngine,
        persistence_facade: SupervisorExecutionPersistenceService,
        compose_service: ResponseComposeService,
        event_publisher: SupervisorProgressPublisher,
        conversation_store: ConversationStore,
    ):
        self.engine = engine
        self.persistence_facade = persistence_facade
        self.compose_service = compose_service
        self.event_publisher = event_publisher
        self.conversation_store = conversation_store

    async def execute_plan(self, session_id: str, task_id: str, plan: FrozenExecutionPlan) -> Dict[str, Any]:
        """
        Executes the agent graph with state restoration and result composition.
        """
        logger.info("supervisor_execution_started", engine=settings.orchestration_engine, task_id=task_id)
        # Rationale (Why): Agents in the swarm need to share context (e.g., accumulated facts).
        # We load the swarm_state from persistence to inject it into the graph's initial state.
        swarm_state = await self.persistence_facade.load_swarm_state(session_id)

        initial_state = {
            "task_id": task_id,
            "session_id": session_id,
            "plan": plan,
            "current_step_index": 0,
            "results": [],
            "final_answer": "",
            "current_step": None,
            "last_result": None,
            "handoff_step": None,
            "swarm_state": swarm_state,
        }

        try:
            # 1. Execute using the abstract engine (LangGraph or Burr)
            # Rationale (Why): Abstraction allows swapping the underlying framework without changing business logic.
            final_state = await self.engine.execute(session_id, task_id, plan, initial_state)

            # 2. Compose and Publish Results
            # Rationale (Why): Raw outputs from multiple agents might be disjointed.
            # The compose_service acts as a final synthesizer to present a coherent streaming response to the user.
            user_message = plan.planner_metadata.get("user_message", "")
            final_answer = await self._compose_and_publish_results(
                session_id, task_id, final_state["results"], 
                {
                    "swarm_state": final_state.get("swarm_state"),
                    "message": user_message,
                    "history": await self._load_recent_history(session_id),
                    "task_id": task_id
                }
            )
            await self.conversation_store.save_message(
                session_id,
                {"role": "assistant", "content": final_answer, "task_id": task_id},
            )

            # 3. Emit Routing Summary
            await self._emit_routing_summary(session_id, task_id, final_state["results"])

            # 4. Persist Completion
            # Rationale (Why): We must persist the final state and updated swarm_state to maintain consistency
            # for subsequent user requests in the same session.
            await self.persistence_facade.persist_execution_completion(
                session_id,
                task_id,
                {
                    "results": final_state["results"],
                    "final_answer": final_answer,
                    "swarm_state": final_state.get("swarm_state", {}),
                },
            )

            await self.event_publisher.publish_done(
                session_id, task_id, {"final_answer": final_answer, "results": final_state["results"]}
            )

            return final_state
        except Exception as e:
            logger.error("graph_execution_failed", task_id=task_id, error=str(e))
            await self.event_publisher.publish_error(session_id, task_id, {"error": str(e)})
            return {"error": str(e)}

    async def execute_direct_answer(self, session_id: str, task_id: str, payload: Dict[str, Any]) -> None:
        """
        Executes a direct LLM response shortcut.
        """
        message = payload.get("message", "")
        reasoning = payload.get("reasoning", "")
        
        log = logger.bind(session_id=session_id, task_id=task_id)

        try:
            log.info("execute_direct_answer_start", message=message[:50], reasoning=reasoning[:50])
            
            if reasoning:
                await self.event_publisher.publish_reasoning(session_id, task_id, reasoning)

            await self.event_publisher.publish_progress(
                session_id, task_id, "composing", {"message": "LLM 응답 생성 중..."}
            )

            final_answer = await self._compose_and_publish_results(
                session_id, task_id, [], {
                    "message": message, 
                    "history": await self._load_recent_history(session_id),
                    "task_id": task_id
                }
            )
            await self.conversation_store.save_message(
                session_id,
                {"role": "assistant", "content": final_answer, "task_id": task_id},
            )
            
            log.info("execute_direct_answer_composition_finished", answer_len=len(final_answer))

            # Persist Completion
            await self.persistence_facade.persist_execution_completion(
                session_id, task_id, {"results": [], "final_answer": final_answer}
            )

            await self.event_publisher.publish_done(
                session_id, task_id, {"status": ProcessStatus.COMPLETED.value, "final_answer": final_answer}
            )
            
            log.info("execute_direct_answer_done_published")

        except Exception as e:
            log.error("direct_answer_failed", task_id=task_id, error=str(e))
            try:
                await self.event_publisher.publish_error(session_id, task_id, {"error": str(e)})
            except Exception as e2:
                log.error("failed_to_publish_error_event", error=str(e2))

    async def _compose_and_publish_results(
        self, session_id: str, task_id: str, results: List[Dict[str, Any]], context: Dict[str, Any]
    ) -> str:
        """
        Composes tokens using the compose service and publishes them to the event stream.
        """
        final_answer_parts = []
        async for event_type, token in self.compose_service.stream_compose(results, context=context):
            if event_type == "reasoning":
                await self.event_publisher.publish_reasoning(session_id, task_id, token)
            elif event_type == "a2ui":
                await self.event_publisher.publish_a2ui(session_id, task_id, json.loads(token))
            else:
                await self.event_publisher.publish_chunk(
                    session_id, task_id, "supervisor", {"answer": token, "data": None}
                )
                final_answer_parts.append(token)
        return "".join(final_answer_parts)

    async def _load_recent_history(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Loads recent conversation history for compose-time grounding.
        """
        try:
            history_cfg = settings.supervisor_config.get("history", {})
            max_turns = history_cfg.get("max-turns", 5)
            # Keep upstream load bounded and aligned with planner behavior.
            load_limit = max(20, max_turns * 2)
            return await self.conversation_store.get_messages(session_id, limit=load_limit)
        except Exception as e:
            logger.warning("history_load_failed_for_compose", session_id=session_id, error=str(e))
            return []

    async def _emit_routing_summary(self, session_id: str, task_id: str, results: List[Dict[str, Any]]) -> None:
        summary = [
            {"order": i, "agent": r.get("agent_key"), "status": r.get("status")}
            for i, r in enumerate(results)
        ]
        await self.event_publisher.publish_progress(session_id, task_id, "routing_summary", {"steps": summary})
        logger.info("routing_summary_emitted", task_id=task_id, steps=len(summary))
