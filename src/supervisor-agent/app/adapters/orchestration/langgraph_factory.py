from typing import Dict, Any, List, TypedDict
from langgraph.graph import StateGraph, END
from ...ports.orchestration_ports import SupervisorStateGraphFactory
from ...domain.models import FrozenExecutionPlan, FrozenRoutingStep
from ...ports.integration_ports import A2AInvocationService
# Assuming we will define an event publisher port or use a service
from ...application.execution.supervisor_progress_publisher import SupervisorProgressPublisher


class AgentState(TypedDict):
    task_id: str
    plan: FrozenExecutionPlan
    current_step_index: int
    results: List[Dict[str, Any]]
    final_answer: str


class LangGraphSupervisorStateGraphFactory(SupervisorStateGraphFactory):
    """
    Adapter implementing the StateGraph generation using LangGraph.
    """
    def __init__(
        self, 
        invocation_service: A2AInvocationService,
        progress_publisher: SupervisorProgressPublisher
    ):
        self.invocation_service = invocation_service
        self.progress_publisher = progress_publisher

    def create_graph(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("invoke_agent", self._invoke_agent_node)
        workflow.add_node("finalize", self._finalize_node)

        workflow.set_entry_point("invoke_agent")
        workflow.add_conditional_edges(
            "invoke_agent",
            self._should_continue,
            {
                "continue": "invoke_agent",
                "end": "finalize"
            }
        )
        workflow.add_edge("finalize", END)

        return workflow.compile()

    async def _invoke_agent_node(self, state: AgentState):
        idx = state["current_step_index"]
        plan = state["plan"]
        step: FrozenRoutingStep = plan.routing_queue[idx]
        
        await self.progress_publisher.publish_progress(
            state["task_id"], 
            f"calling_{step.agent_key}", 
            {"order": step.order}
        )

        # invocation_service.invoke() 내부에서 streaming method 정규화가 수행됨
        result = await self.invocation_service.invoke(
            step.agent_key,
            step.method,
            step.arguments
        )

        await self.progress_publisher.publish_chunk(
            state["task_id"], 
            step.agent_key, 
            result.get("payload")
        )

        state["results"].append(result)
        state["current_step_index"] += 1
        return state

    def _should_continue(self, state: AgentState):
        if state["current_step_index"] < len(state["plan"].routing_queue):
            return "continue"
        return "end"

    async def _finalize_node(self, state: AgentState):
        return state
