from typing import Dict, Any, List, TypedDict, Optional
from langgraph.graph import StateGraph, END
from ...ports.orchestration_ports import StateGraphFactory, HandoffPolicyService
from ...domain.models import FrozenExecutionPlan, FrozenRoutingStep
from ...ports.integration_ports import A2AInvocationService
from ...application.execution.supervisor_progress_publisher import SupervisorProgressPublisher
from ...services.fact_governance_service import FactGovernanceService

import structlog
logger = structlog.get_logger()


class AgentState(TypedDict):
    task_id: str
    session_id: str
    plan: FrozenExecutionPlan
    current_step_index: int
    results: List[Dict[str, Any]]
    final_answer: str
    
    # Internal runtime state fields
    current_step: Optional[FrozenRoutingStep]
    last_result: Optional[Dict[str, Any]]
    handoff_step: Optional[FrozenRoutingStep]


class LangGraphStateGraphFactory(StateGraphFactory):
    """
    Adapter implementing the StateGraph generation using LangGraph.
    Aligns with Doc 05 (Orchestration) and Doc 11B (Runtime State Machine).
    """
    def __init__(
        self, 
        invocation_service: A2AInvocationService,
        handoff_service: HandoffPolicyService,
        progress_publisher: SupervisorProgressPublisher,
        fact_service: Optional[FactGovernanceService] = None
    ):
        self.invocation_service = invocation_service
        self.handoff_service = handoff_service
        self.progress_publisher = progress_publisher
        self.fact_service = fact_service

    def create_graph(self):
        workflow = StateGraph(AgentState)

        # 1. Define Nodes as per Doc 11B
        workflow.add_node("select", self._select_node)
        workflow.add_node("invoke", self._invoke_node)
        workflow.add_node("handoff_evaluate", self._handoff_evaluate_node)
        workflow.add_node("handoff_apply", self._handoff_apply_node)
        workflow.add_node("merge", self._merge_node)

        # 2. Define Edges and Conditional Logic
        workflow.set_entry_point("select")
        
        workflow.add_conditional_edges(
            "select",
            self._should_invoke,
            {
                "continue": "invoke",
                "end": END
            }
        )
        
        workflow.add_edge("invoke", "handoff_evaluate")
        
        workflow.add_conditional_edges(
            "handoff_evaluate",
            self._should_apply_handoff,
            {
                "apply": "handoff_apply",
                "skip": "merge"
            }
        )
        
        workflow.add_edge("handoff_apply", "merge")
        
        workflow.add_conditional_edges(
            "merge",
            self._should_loop_back,
            {
                "next": "select",
                "end": END
            }
        )

        return workflow.compile()

    # --- Node Implementations ---

    async def _select_node(self, state: AgentState):
        """
        ROUTING_SELECTED (Doc 05): Selects the next step from the queue.
        Ensures strict alignment with the frozen routing plan.
        """
        idx = state["current_step_index"]
        plan = state["plan"]
        
        # Doc 05: Selection Logic
        if idx < len(plan.routing_queue):
            state["current_step"] = plan.routing_queue[idx]
            logger.info("routing_step_selected", 
                        task_id=state["task_id"], 
                        agent=state["current_step"].agent_key,
                        step_index=idx)
        else:
            state["current_step"] = None
            logger.debug("no_more_routing_steps", task_id=state["task_id"])
            
        return state

    async def _invoke_node(self, state: AgentState):
        """
        A2A_CALLING: Invokes the downstream agent.
        Publishes progress events as per Doc 26.
        """
        step = state["current_step"]
        if not step:
            return state

        # Publish calling status for UI visibility
        await self.progress_publisher.publish_progress(
            state["session_id"],
            state["task_id"], 
            f"calling_{step.agent_key}", 
            {"order": step.order, "agent": step.agent_key, "method": step.method}
        )

        result = await self.invocation_service.invoke(
            step.agent_key,
            step.method,
            step.arguments
        )

        # Doc 26: RAW data channel must be replayed
        await self.progress_publisher.publish_chunk(
            state["session_id"],
            state["task_id"], 
            step.agent_key, 
            result.get("payload")
        )

        state["last_result"] = result
        return state

    async def _handoff_evaluate_node(self, state: AgentState):
        """HANDOFF_EVALUATING: Evaluates if a handoff is triggered by the result."""
        result = state["last_result"]
        step = state["current_step"]
        
        if not result or result.get("status") != "COMPLETED":
            state["handoff_step"] = None
            return state

        # Doc 05/11B: Evaluate via dedicated Handoff Policy Service
        context = {"result_payload": result.get("payload", {})}
        validation = self.handoff_service.evaluate(step, context)
        
        if validation.allowed and validation.handoff_step:
            logger.info("handoff_detected", 
                        task_id=state["task_id"], 
                        target=validation.handoff_step.agent_key)
            state["handoff_step"] = validation.handoff_step
        else:
            if validation.reason and validation.allowed is False:
                 logger.warning("handoff_blocked", 
                                task_id=state["task_id"], 
                                reason=validation.reason)
            state["handoff_step"] = None
            
        return state

    async def _handoff_apply_node(self, state: AgentState):
        """HANDOFF_APPLIED: Injects the handoff step into the routing queue."""
        new_step = state["handoff_step"]
        if new_step:
            # Doc 05: Insert step immediately to follow the chain
            idx = state["current_step_index"]
            state["plan"].routing_queue.insert(idx + 1, new_step)
            logger.info("handoff_step_applied", 
                        task_id=state["task_id"], 
                        agent=new_step.agent_key)
            
        return state

    async def _merge_node(self, state: AgentState):
        """
        A2A_RESULT_MERGED: Records the result and increments the counter.
        Also clears temporary runtime variables and updates Swarm Facts (Doc 03).
        """
        if state["last_result"]:
            state["results"].append({
                "agent": state["current_step"].agent_key if state.get("current_step") else "unknown",
                "result": state["last_result"]
            })
            
            # Update Swarm Facts
            if self.fact_service:
                await self.fact_service.update_facts(state["session_id"], state["last_result"])
            
        state["current_step_index"] += 1
        state["last_result"] = None
        state["handoff_step"] = None
        state["current_step"] = None
        
        return state

    # --- Conditional Edge Logic ---

    def _should_invoke(self, state: AgentState):
        if state.get("current_step"):
            return "continue"
        return "end"

    def _should_apply_handoff(self, state: AgentState):
        if state.get("handoff_step"):
            return "apply"
        return "skip"

    def _should_loop_back(self, state: AgentState):
        # Doc 05: Max Iteration Guard (prevent infinite handoffs)
        max_iterations = state["plan"].execution_constraints.max_handoff_depth + len(state["plan"].routing_queue)
        
        if state["current_step_index"] < len(state["plan"].routing_queue):
            if state["current_step_index"] > max_iterations: 
                logger.warning("max_iteration_guard_triggered", 
                               task_id=state["task_id"], 
                               current=state["current_step_index"],
                               limit=max_iterations)
                return "end"
            return "next"
        return "end"
