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

class LlmPlanner(Planner):
    """
    LLM implementation of the Planner port.
    """
    def __init__(self):
        self.model = LlmRuntime.get_chat_model()

    @staticmethod
    def _extract_user_message(context: PlanningContext) -> str:
        for m in reversed(context.history):
            if m.role == AgentRole.USER.value:
                return m.content
        return ""

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

class LlmComposer(Composer):
    """
    LLM implementation of the Composer port.
    """
    def __init__(self):
        self.model = LlmRuntime.get_chat_model()

    @staticmethod
    def _extract_user_message(context: PlanningContext) -> str:
        # Compose 단계는 history 전체를 전달하지 않고 사용자 메시지만 사용한다.
        for m in reversed(context.history):
            if m.role == AgentRole.USER.value:
                return m.content
        return ""

    async def stream_compose(self, context: PlanningContext) -> AsyncIterator[AiChatChunk]:
        """
        Yields AiChatChunk objects as per Document 18.
        """
        prompts = settings.prompts
        base_system = prompts.get("system", "")
        final_answer = prompts.get("final-answer", "")
        compose_rules = prompts.get("compose-rules", "")
        template = prompts.get("compose-prompt-template", "")

        # Rationale (Why): Composition requires actual tool execution results to provide a grounded answer.
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
            # Rationale (Why): Unifying internal results to AiChatChunk (Doc 18).
            yield AiChatChunk(content=chunk.content)
