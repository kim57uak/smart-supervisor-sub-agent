import structlog
from typing import Dict, Any
from ...ports.interfaces import OrchestrationEngine

logger = structlog.get_logger()

# ──────────────────────────────────────────────
# LangGraph 오케스트레이션 엔진 어댑터
# ──────────────────────────────────────────────
# OrchestrationEngine 포트의 LangGraph 구현체.
# WorkflowFactory가 생성한 StateGraph를 컴파일하여 보관하고,
# execute() 호출 시 ainvoke()로 그래프를 실행한다.
# BurrAdapter와 동일한 인터페이스로 동작하여 오케스트레이션 엔진 교체를 추상화한다.
class LangGraphAdapter(OrchestrationEngine):
    def __init__(self, graph_factory):
        self.graph_factory = graph_factory
        self.graph = self.graph_factory.create_graph()

    # LangGraph 그래프 실행
    # initial_state(dict)를 AgentState에 매핑하여 그래프에 전달하고 최종 상태를 반환한다.
    async def execute(self, 
                      session_id: str, 
                      task_id: str, 
                      initial_state: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("subagent_langgraph_execution_start", task_id=task_id)
        final_state = await self.graph.ainvoke(initial_state)
        logger.info("subagent_langgraph_execution_finished", task_id=task_id)
        return final_state
