import structlog
from typing import Dict, Any, List, Annotated, TypedDict
from langgraph.graph import StateGraph, END
from ...domain.enums import ProcessStatus, EventType, AgentRole
from ...ports.interfaces import Planner, ToolExecutor, Composer, ProgressPublisher
from ...domain.models import PlanningContext, Message, ToolPlan
from ...core.config import settings
from ..mcp.mcp_tool_registry import McpToolRegistry

logger = structlog.get_logger(__name__)

# ──────────────────────────────────────────────
# LangGraph 상태 타입 정의
# ──────────────────────────────────────────────
# LangGraph StateGraph가 관리하는 전체 상태 구조.
# 각 노드는 이 상태의 일부를 읽고 쓰며 그래프를 따라 전파된다.
# loop_count는 반복 실행 횟수를 추적하여 max_tool_iterations 제한에 사용된다.
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

# ──────────────────────────────────────────────
# LangGraph 워크플로우 팩토리
# ──────────────────────────────────────────────
# Planner(도구 선택) → Executor(도구 실행) → Composer(응답 생성)로 이어지는
# 에이전트 실행 파이프라인을 StateGraph로 구축한다.
# 각 노드는 ProgressPublisher를 통해 실시간 진행 상태를 Redis Pub/Sub으로 발행한다.
class WorkflowFactory:
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

    # 5개 노드로 구성된 LangGraph StateGraph 생성
    #
    # load_context → select_tools ─┬─(continue)→ execute_tools → finalize_context → compose_response → END
    #                              └─(end)────→ compose_response → END
    #
    # select_tools에서 plans가 비어있거나 최대 반복 초과 시 compose_response로 바로 이동한다.
    def create_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)

        workflow.add_node("load_context", self._load_context)
        workflow.add_node("select_tools", self._select_tools)
        workflow.add_node("execute_tools", self._execute_tools)
        workflow.add_node("finalize_context", self._finalize_context)
        workflow.add_node("compose_response", self._compose_response)

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

    # 조건부 분기: plans 존재 + 반복 횟수 제한 검사
    def _should_continue(self, state: AgentState) -> str:
        if not state.get("plans") or state.get("loop_count", 0) >= self.max_iterations:
            return "end"
        return "continue"

    # [노드 ①] 실행 문맥 로드
    # 기존 history가 있으면 재사용, 없으면 user_message로 초기 Message 생성
    async def _load_context(self, state: AgentState) -> Dict[str, Any]:
        await self.publisher.publish(state["session_id"], state["task_id"], {
            "event_type": EventType.PROGRESS.value,
            "payload": {"stage": "load_context", "message": "실행 문맥 로드 중..."}
        }, trace_id=state["trace_id"])
        existing_history = state.get("history") or []
        if existing_history:
            return {"history": existing_history, "loop_count": 0}
        return {
            "history": [Message(role=AgentRole.USER.value, content=state["user_message"])],
            "loop_count": 0
        }

    # [노드 ②] 도구 선택 (Planner 호출)
    # McpToolRegistry에서 가용 도구 스키마를 조회하고 Planner.plan()을 호출한다.
    async def _select_tools(self, state: AgentState) -> Dict[str, Any]:
        await self.publisher.publish(state["session_id"], state["task_id"], {
            "event_type": EventType.PLANNING.value,
            "payload": {"message": "도구 실행 계획 수립 중...", "iteration": state.get("loop_count", 0) + 1}
        }, trace_id=state["trace_id"])
        
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

    # [노드 ③] 도구 실행 (Executor 호출)
    # 각 ToolPlan을 순차적으로 실행하고 결과를 results에 누적한다.
    # runtime_fields(session_id, trace_id, task_id)를 전달하여 Schema Guard의
    # 필드 주입(GUID, session_id 등)이 동작하도록 한다.
    async def _execute_tools(self, state: AgentState) -> Dict[str, Any]:
        results = list(state.get("results", []))
        for plan in state["plans"]:
            await self.publisher.publish(state["session_id"], state["task_id"], {
                "event_type": EventType.EXECUTING_TOOL.value,
                "payload": {"tool": plan.tool_name, "message": f"도구 실행 중: {plan.tool_name}"}
            }, trace_id=state["trace_id"])
            result = await self.executor.execute(
                plan,
                runtime_fields={
                    "session_id": state["session_id"],
                    "trace_id": state["trace_id"],
                    "task_id": state["task_id"],
                },
            )
            results.append(result)
            await self.publisher.publish(state["session_id"], state["task_id"], {
                "event_type": EventType.TOOL_RESULT.value,
                "payload": {"tool": plan.tool_name, "result": result}
            }, trace_id=state["trace_id"])
        return {"results": results}

    # [노드 ④] 실행 결과 정리
    # 성공한 도구 실행 결과를 history에 Message(TOOL role)로 추가한다.
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

    # [노드 ⑤] 최종 응답 생성 (Composer 호출)
    # Composer.stream_compose()를 호출하여 스트리밍 응답을 수집한다.
    # 각 청크는 실시간으로 ProgressPublisher를 통해 클라이언트에 전달된다.
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
