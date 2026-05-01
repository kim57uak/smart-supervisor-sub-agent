import structlog
from typing import Dict, Any, List, Tuple
from burr.core import Application, ApplicationBuilder, action, State, Action
from burr.core.action import SingleStepAction
from ...domain.enums import ProcessStatus, EventType, AgentRole
from ...ports.interfaces import Planner, ToolExecutor, Composer, ProgressPublisher
from ...domain.models import PlanningContext, Message, ToolPlan
from ...core.config import settings
from ..mcp.mcp_tool_registry import McpToolRegistry

logger = structlog.get_logger(__name__)

class BurrWorkflowFactory:
    """
    Factory for creating the Burr application for sub-agent.
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

    def create_application_builder(self, session_id: str, task_id: str, trace_id: str) -> ApplicationBuilder:
        # Rationale (Why): Return builder to allow state injection before building (Document 12/20).
        # We avoid capturing request-specific variables in closures by passing them in the initial state.
        
        @action(reads=["user_message", "session_id", "task_id", "trace_id"], writes=["history", "loop_count"])
        async def load_context(state: State) -> Tuple[dict, State]:
            current_session = state["session_id"]
            current_task = state["task_id"]
            current_trace = state["trace_id"]

            await self.publisher.publish(current_session, current_task, {
                "event_type": EventType.PROGRESS.value,
                "payload": {"stage": "load_context", "message": "실행 문맥 로드 중... (Burr)"}
            }, trace_id=current_trace)
            
            existing_history = state.get("history") or []
            new_history = existing_history if existing_history else [Message(role=AgentRole.USER.value, content=state["user_message"])]
            return {"history": new_history}, state.update(history=new_history, loop_count=0)

        @action(reads=["history", "loop_count", "session_id", "task_id", "trace_id"], writes=["plans", "loop_count"])
        async def select_tools(state: State) -> Tuple[dict, State]:
            current_session = state["session_id"]
            current_task = state["task_id"]
            current_trace = state["trace_id"]

            await self.publisher.publish(current_session, current_task, {
                "event_type": EventType.PLANNING.value,
                "payload": {"message": "도구 실행 계획 수립 중... (Burr)", "iteration": state["loop_count"] + 1}
            }, trace_id=current_trace)
            
            available_tools = self.registry.get_tool_schemas()
            context = PlanningContext(
                session_id=current_session, 
                history=state["history"],
                available_tools=available_tools
            )
            plans = await self.planner.plan(context)
            
            return {"plans": plans}, state.update(plans=plans, loop_count=state["loop_count"] + 1)

        @action(reads=["plans", "results", "session_id", "task_id", "trace_id"], writes=["results"])
        async def execute_tools(state: State) -> Tuple[dict, State]:
            current_session = state["session_id"]
            current_task = state["task_id"]
            current_trace = state["trace_id"]
            
            results = list(state.get("results", []))
            for plan in state["plans"]:
                await self.publisher.publish(current_session, current_task, {
                    "event_type": EventType.EXECUTING_TOOL.value,
                    "payload": {"tool": plan.tool_name, "message": f"도구 실행 중: {plan.tool_name}"}
                }, trace_id=current_trace)
                
                result = await self.executor.execute(
                    plan,
                    runtime_fields={
                        "session_id": current_session,
                        "trace_id": current_trace,
                        "task_id": current_task,
                    },
                )
                results.append(result)
                
                await self.publisher.publish(current_session, current_task, {
                    "event_type": EventType.TOOL_RESULT.value,
                    "payload": {"tool": plan.tool_name, "result": result}
                }, trace_id=current_trace)
                
            return {"results": results}, state.update(results=results)

        @action(reads=["history", "results", "session_id", "task_id", "trace_id"], writes=["history"])
        async def finalize_context(state: State) -> Tuple[dict, State]:
            current_session = state["session_id"]
            current_task = state["task_id"]
            current_trace = state["trace_id"]

            await self.publisher.publish(current_session, current_task, {
                "event_type": EventType.PROGRESS.value,
                "payload": {"stage": "finalize_context", "message": "실행 결과 정리 중..."}
            }, trace_id=current_trace)
            
            new_history = list(state["history"])
            for res in state.get("results", []):
                if res.get("status") == "success":
                    new_history.append(Message(role=AgentRole.TOOL.value, content=str(res.get("output"))))
            
            return {"history": new_history}, state.update(history=new_history)

        @action(reads=["history", "results", "session_id", "task_id", "trace_id"], writes=["final_answer", "status"])
        async def compose_response(state: State) -> Tuple[dict, State]:
            current_session = state["session_id"]
            current_task = state["task_id"]
            current_trace = state["trace_id"]

            await self.publisher.publish(current_session, current_task, {
                "event_type": EventType.COMPOSING.value,
                "payload": {"message": "최종 응답 생성 중..."}
            }, trace_id=current_trace)

            context = PlanningContext(
                session_id=current_session, 
                history=state["history"],
                tool_results=state.get("results", [])
            )

            final_answer = ""
            async for chunk in self.composer.stream_compose(context):
                final_answer += chunk.content
                await self.publisher.publish(current_session, current_task, {
                    "event_type": EventType.CHUNK.value,
                    "payload": {"answer": chunk.content}
                }, trace_id=current_trace)

            return {"final_answer": final_answer}, state.update(
                final_answer=final_answer, 
                status=ProcessStatus.COMPLETED
            )

        # Rationale (Why): In Burr 0.40.2, using expr() creates a valid Condition object for validation.
        from burr.core import when, default, expr

        return (
            ApplicationBuilder()
            .with_tracker(project="smart-supervisor-a2a")
            .with_identifiers(partition_key=session_id, app_id=task_id)
            .with_state(
                plans=[], 
                history=[], 
                results=[],
                loop_count=0,
                session_id=session_id,
                task_id=task_id,
                trace_id=trace_id
            )
            .with_actions(
                load_context=load_context,
                select_tools=select_tools,
                execute_tools=execute_tools,
                finalize_context=finalize_context,
                compose_response=compose_response
            )
            .with_transitions(
                ("load_context", "select_tools"),
                ("select_tools", "execute_tools", expr("len(plans) > 0")),
                ("select_tools", "compose_response", default),
                ("execute_tools", "finalize_context"),
                ("finalize_context", "compose_response")
            )
            .with_entrypoint("load_context")
        )











