import structlog
from typing import Dict, Any, List, Annotated, TypedDict
from langgraph.graph import StateGraph, END
from ...domain.enums import ProcessStatus, EventType, AgentRole
from ...ports.interfaces import Planner, ToolExecutor, Composer, ProgressPublisher
from ...domain.models import PlanningContext, Message, ToolPlan
from ...core.config import settings
from ..mcp.mcp_tool_registry import McpToolRegistry

logger = structlog.get_logger(__name__)

class AgentState(TypedDict):
    task_id: str
    session_id: str
    trace_id: str
    user_message: str
    history: List[Message]
    plans: List[ToolPlan]
    results: List[Dict[str, Any]]
    final_answer: str
    status: ProcessStatus
    loop_count: int

class WorkflowFactory:
    """
    Factory for creating the LangGraph state machine for sub-agent.
    Implements the Workflow creation logic.
    """
    def __init__(
        self,
        planner: Planner,
        executor: ToolExecutor,
        composer: Composer,
        publisher: ProgressPublisher,
        registry: McpToolRegistry
    ):
        self.planner = planner
        self.executor = executor
        self.composer = composer
        self.publisher = publisher
        self.registry = registry
        self.max_iterations = settings.agent.graph.max_tool_iterations

    def create_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)

        # 1. Define Nodes
        workflow.add_node("load_context", self._load_context)
        workflow.add_node("select_tools", self._select_tools)
        workflow.add_node("execute_tools", self._execute_tools)
        workflow.add_node("finalize_context", self._finalize_context)
        workflow.add_node("compose_response", self._compose_response)

        # 2. Define Edges
        workflow.set_entry_point("load_context")
        workflow.add_edge("load_context", "select_tools")
        
        workflow.add_conditional_edges(
            "select_tools",
            self._should_continue,
            {
                "continue": "execute_tools",
                "end": "compose_response"
            }
        )
        
        workflow.add_edge("execute_tools", "finalize_context")
        workflow.add_edge("finalize_context", "compose_response")
        workflow.add_edge("compose_response", END)

        return workflow.compile()

    def _should_continue(self, state: AgentState) -> str:
        if not state.get("plans") or state.get("loop_count", 0) >= self.max_iterations:
            return "end"
        return "continue"

    async def _load_context(self, state: AgentState) -> Dict[str, Any]:
        await self.publisher.publish(state["session_id"], state["task_id"], {
            "event_type": EventType.PROGRESS.value,
            "payload": {"stage": "load_context", "message": "실행 문맥 로드 중..."}
        }, trace_id=state["trace_id"])
        return {
            "history": [Message(role=AgentRole.USER.value, content=state["user_message"])],
            "loop_count": 0
        }

    async def _select_tools(self, state: AgentState) -> Dict[str, Any]:
        await self.publisher.publish(state["session_id"], state["task_id"], {
            "event_type": EventType.PLANNING.value,
            "payload": {"message": "도구 실행 계획 수립 중...", "iteration": state.get("loop_count", 0) + 1}
        }, trace_id=state["trace_id"])
        
        # Rationale (Why): Planner must know about available tools to make a decision.
        available_tools = self.registry.get_tool_schemas()
        context = PlanningContext(
            session_id=state["session_id"], 
            history=state["history"],
            available_tools=available_tools
        )
        plans = await self.planner.plan(context)
        
        return {
            "plans": plans,
            "loop_count": state.get("loop_count", 0) + 1
        }

    async def _execute_tools(self, state: AgentState) -> Dict[str, Any]:
        results = list(state.get("results", []))
        for plan in state["plans"]:
            await self.publisher.publish(state["session_id"], state["task_id"], {
                "event_type": EventType.EXECUTING_TOOL.value,
                "payload": {"tool": plan.tool_name, "message": f"도구 실행 중: {plan.tool_name}"}
            }, trace_id=state["trace_id"])
            # Rationale (Why): execute() implementation only expects 'plan'.
            result = await self.executor.execute(plan)
            results.append(result)
            await self.publisher.publish(state["session_id"], state["task_id"], {
                "event_type": EventType.TOOL_RESULT.value,
                "payload": {"tool": plan.tool_name, "result": result}
            }, trace_id=state["trace_id"])
        return {"results": results}

    async def _finalize_context(self, state: AgentState) -> Dict[str, Any]:
        await self.publisher.publish(state["session_id"], state["task_id"], {
            "event_type": EventType.PROGRESS.value,
            "payload": {"stage": "finalize_context", "message": "실행 결과 정리 중..."}
        }, trace_id=state["trace_id"])
        
        new_history = list(state["history"])
        for res in state.get("results", []):
            if res.get("status") == "success":
                new_history.append(Message(role=AgentRole.TOOL.value, content=str(res.get("output"))))
        
        return {"history": new_history}

    async def _compose_response(self, state: AgentState) -> Dict[str, Any]:
        await self.publisher.publish(state["session_id"], state["task_id"], {
            "event_type": EventType.COMPOSING.value,
            "payload": {"message": "최종 응답 생성 중..."}
        }, trace_id=state["trace_id"])

        context = PlanningContext(
            session_id=state["session_id"], 
            history=state["history"],
            tool_results=state.get("results", [])
        )

        final_answer = ""
        async for chunk in self.composer.stream_compose(context):
            final_answer += chunk.content
            await self.publisher.publish(state["session_id"], state["task_id"], {
                "event_type": EventType.CHUNK.value,
                "payload": {"answer": chunk.content}
            }, trace_id=state["trace_id"])

        return {"final_answer": final_answer, "status": ProcessStatus.COMPLETED}

