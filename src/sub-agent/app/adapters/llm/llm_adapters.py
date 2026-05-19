import json
import structlog
from typing import List, AsyncIterator, Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from ...ports.interfaces import Planner, Composer
from ...domain.models import PlanningContext, ToolPlan, Message, AiChatChunk
from ...infrastructure.llm_runtime import LlmRuntime
from ...core.config import settings
from ...domain.enums import AgentRole

logger = structlog.get_logger(__name__)

# ──────────────────────────────────────────────
# LLM Planner — 도구 실행 계획 수립
# ──────────────────────────────────────────────
# Planner 포트의 LLM 기반 구현체.
# 사용자 메시지와 가용 MCP 도구 목록을 LLM에 전달하여 ToolPlan 목록을 생성한다.
# 출력 예: [{"tool": "reservation/createReservation", "server": "reservation", ...}]
class LlmPlanner(Planner):
    def __init__(self):
        self.model = LlmRuntime.get_chat_model()

    # PlanningContext.history에서 가장 최근 사용자 메시지 추출
    @staticmethod
    def _extract_user_message(context: PlanningContext) -> str:
        for m in reversed(context.history):
            if m.role == AgentRole.USER.value:
                return m.content
        return ""

    # LLM 계획 수립 실행
    # system_prompt에 도구 카탈로그(serverCatalog), 실행 이력, 사용자 메시지를 포함한다.
    # LLM 응답에서 JSON 객체({plans: [...]})를 파싱하여 ToolPlan 리스트로 변환한다.
    async def plan(self, context: PlanningContext) -> List[ToolPlan]:
        prompts = settings.prompts
        agent_system = prompts.get("agent-system", "")
        tool_choice = prompts.get("tool-choice", "")
        template = prompts.get("tool-planning-prompt-template", "")
        
        user_message = self._extract_user_message(context)
        system_prompt = template.format(
            agentSystem=agent_system,
            toolChoice=tool_choice,
            serverCatalog=json.dumps(context.available_tools, ensure_ascii=False),
            userMessage=user_message,
            dateHints="N/A",
            executedTools="[]",
            latestResult="N/A"
        )
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message) if user_message else HumanMessage(content="")
        ]
        
        logger.info("llm_planning_start", tool_count=len(context.available_tools), history_len=len(context.history))
        
        try:
            response = await self.model.ainvoke(messages)
            raw_content = response.content
            
            logger.debug("llm_planning_raw_response", content=raw_content)
            
            # ```json ... ``` 마크다운 코드 블록 제거
            if "```json" in raw_content:
                raw_content = raw_content.split("```json")[1].split("```")[0].strip()
            
            data = json.loads(raw_content)
            plans_data = data.get("plans", [])
            
            logger.info("llm_planning_success", plan_count=len(plans_data))
            
            tool_plans = []
            for p in plans_data:
                tool_name = p.get("tool")
                logger.info("tool_selected", tool=tool_name, reasoning=p.get("reason", ""))
                tool_plans.append(ToolPlan(
                    tool_name=tool_name,
                    server_name=p.get("server"),
                    arguments=p.get("arguments", {}),
                    reasoning=p.get("reason", "")
                ))
            
            return tool_plans
            
        except Exception as e:
            logger.error("planning_failed", error=str(e))
            return []

# ──────────────────────────────────────────────
# LLM Composer — 최종 응답 생성
# ──────────────────────────────────────────────
# Composer 포트의 LLM 기반 구현체.
# 도구 실행 결과(tool_results)를 바탕으로 최종 사용자 응답을 스트리밍 생성한다.
# AiChatChunk 단위로 스트리밍 출력한다.
class LlmComposer(Composer):
    def __init__(self):
        self.model = LlmRuntime.get_chat_model()

    @staticmethod
    def _extract_user_message(context: PlanningContext) -> str:
        # Compose 단계에서는 전체 history가 아닌 사용자 메시지만 사용한다.
        for m in reversed(context.history):
            if m.role == AgentRole.USER.value:
                return m.content
        return ""

    # 스트리밍 응답 생성
    # system_prompt에 baseSystem, composeRules, toolResult(실행 결과)를 포함하여 LLM에 전달한다.
    # astream()의 각 청크를 AiChatChunk로 변환하여 상위 계층(ProgressPublisher)으로 전달한다.
    async def stream_compose(self, context: PlanningContext) -> AsyncIterator[AiChatChunk]:
        prompts = settings.prompts
        base_system = prompts.get("system", "")
        final_answer = prompts.get("final-answer", "")
        compose_rules = prompts.get("compose-rules", "")
        template = prompts.get("compose-prompt-template", "")

        # 도구 실행 결과(tool_results)를 JSON 문자열로 변환하여 컨텍스트에 포함
        tool_results_str = json.dumps(context.tool_results, ensure_ascii=False) if context.tool_results else "N/A"

        system_prompt = template.format(
            baseSystem=base_system,
            finalAnswer=final_answer,
            composeRules=compose_rules,
            userMessage=self._extract_user_message(context),
            history="[]",
            toolResult=tool_results_str
        )
        
        messages = [
            SystemMessage(content=system_prompt)
        ]
        
        async for chunk in self.model.astream(messages):
            # 내부 LLM 청크 → 도메인 모델(AiChatChunk) 변환
            yield AiChatChunk(content=chunk.content)
