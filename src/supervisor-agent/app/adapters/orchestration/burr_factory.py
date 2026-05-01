import structlog
from typing import Dict, Any, List, Tuple, Optional
from burr.core import Application, ApplicationBuilder, action, State
from ...domain.models import FrozenExecutionPlan, FrozenRoutingStep
from ...ports.integration_ports import A2AInvocationService
from ...ports.orchestration_ports import HandoffPolicyService
from ...application.execution.supervisor_progress_publisher import SupervisorProgressPublisher
from ...services.fact_governance_service import FactGovernanceService
from ...domain.enums import TaskState

logger = structlog.get_logger(__name__)

class BurrWorkflowFactory:
    """
    Factory for creating the Burr application for supervisor agent.
    Mirrors the LangGraph logic in Burr's action-based architecture.
    """
    def __init__(
        self,
        invocation_service: A2AInvocationService,
        handoff_service: HandoffPolicyService,
        progress_publisher: SupervisorProgressPublisher,
        fact_service: Optional[FactGovernanceService] = None,
        task_store: Any = None
    ):
        self.invocation_service = invocation_service
        self.handoff_service = handoff_service
        self.progress_publisher = progress_publisher
        self.fact_service = fact_service
        self.task_store = task_store

    def create_application_builder(self, session_id: str, task_id: str) -> ApplicationBuilder:
        
        @action(reads=["task_id", "session_id", "plan", "current_step_index"], 
                writes=["current_step"])
        async def select_step(state: State) -> Tuple[dict, State]:
            idx = state["current_step_index"]
            plan_raw = state["plan"]
            
            # Rationale (Why): Defensive check to ensure 'plan' is a Pydantic model. 
            # If the state was restored from a dictionary, we must reconstruct the model 
            # to access its attributes correctly.
            if isinstance(plan_raw, dict):
                plan = FrozenExecutionPlan(**plan_raw)
            else:
                plan = plan_raw
            
            if idx < len(plan.routing_queue):
                current_step = plan.routing_queue[idx]
                logger.info("routing_step_selected (Burr)", 
                            task_id=state["task_id"], 
                            agent=current_step.agent_key,
                            step_index=idx)
                return {"current_step": current_step}, state.update(current_step=current_step)
            else:
                logger.debug("no_more_routing_steps (Burr)", task_id=state["task_id"])
                return {"current_step": None}, state.update(current_step=None)

        @action(reads=["task_id", "session_id", "current_step"], 
                writes=["last_result", "current_step"])
        async def invoke_agent(state: State) -> Tuple[dict, State]:
            # Rationale (Why): External cancellation check.
            if self.task_store:
                task_data = await self.task_store.get_task(state["session_id"], state["task_id"])
                if task_data and task_data.get("state") == TaskState.CANCELED.value:
                    logger.info("task_execution_aborted_due_to_cancellation (Burr)", task_id=state["task_id"])
                    return {"last_result": None}, state.update(current_step=None, last_result=None)

            step: FrozenRoutingStep = state["current_step"]
            if not step:
                return {"last_result": None}, state

            await self.progress_publisher.publish_progress(
                state["session_id"],
                state["task_id"], 
                f"calling_{step.agent_key}", 
                {"order": step.order, "agent": step.agent_key, "method": step.method}
            )

            result = await self.invocation_service.invoke(
                step.agent_key,
                step.method,
                {
                    **step.arguments,
                    "session_id": state["session_id"],
                    "task_id": state["task_id"],
                }
            )

            await self.progress_publisher.publish_chunk(
                state["session_id"],
                state["task_id"], 
                step.agent_key, 
                result.get("payload")
            )

            return {"last_result": result}, state.update(last_result=result)

        @action(reads=["task_id", "last_result", "current_step"], 
                writes=["handoff_step"])
        async def evaluate_handoff(state: State) -> Tuple[dict, State]:
            result = state["last_result"]
            step = state["current_step"]
            
            if not result or result.get("status") != "COMPLETED":
                return {"handoff_step": None}, state.update(handoff_step=None)

            context = {"result_payload": result.get("payload", {})}
            validation = self.handoff_service.evaluate(step, context)
            
            if validation.allowed and validation.handoff_step:
                logger.info("handoff_detected (Burr)", 
                            task_id=state["task_id"], 
                            target=validation.handoff_step.agent_key)
                return {"handoff_step": validation.handoff_step}, state.update(handoff_step=validation.handoff_step)
            
            return {"handoff_step": None}, state.update(handoff_step=None)

        @action(reads=["task_id", "handoff_step", "plan", "current_step_index"], 
                writes=["plan"])
        async def apply_handoff(state: State) -> Tuple[dict, State]:
            new_step = state["handoff_step"]
            plan = state["plan"]
            if new_step:
                idx = state["current_step_index"]
                plan.routing_queue.insert(idx + 1, new_step)
                logger.info("handoff_step_applied (Burr)", 
                            task_id=state["task_id"], 
                            agent=new_step.agent_key)
            
            return {"plan": plan}, state.update(plan=plan)

        @action(reads=["session_id", "current_step", "last_result", "results", "current_step_index"], 
                writes=["results", "current_step_index", "last_result", "handoff_step", "current_step"])
        async def merge_result(state: State) -> Tuple[dict, State]:
            results = list(state["results"])
            if state["last_result"]:
                results.append(state["last_result"])
                
                if self.fact_service:
                    await self.fact_service.update_facts(state["session_id"], state["last_result"])
            
            return {"results": results}, state.update(
                results=results,
                current_step_index=state["current_step_index"] + 1,
                last_result=None,
                handoff_step=None,
                current_step=None
            )

        @action(reads=["results", "current_step_index", "task_id"], writes=[])
        async def terminal(state: State) -> Tuple[dict, State]:
            logger.info("burr_execution_terminal", task_id=state["task_id"])
            return {"status": "completed"}, state

        from burr.core import when, default, expr

        return (
            ApplicationBuilder()
            .with_tracker(project="smart-supervisor-a2a")
            .with_identifiers(partition_key=session_id, app_id=task_id)
            .with_actions(
                select=select_step,
                invoke=invoke_agent,
                handoff_evaluate=evaluate_handoff,
                handoff_apply=apply_handoff,
                merge=merge_result,
                terminal=terminal
            )
            .with_transitions(
                ("select", "invoke", expr("current_step is not None")),
                ("select", "terminal", default),
                ("invoke", "handoff_evaluate"),
                ("handoff_evaluate", "handoff_apply", expr("handoff_step is not None")),
                ("handoff_evaluate", "merge", default),
                ("handoff_apply", "merge"),
                ("merge", "select")
            )
            .with_entrypoint("select")
        )
