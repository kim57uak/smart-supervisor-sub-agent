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

    async def plan(self, context: PlanningContext) -> List[ToolPlan]:
        prompts = settings.prompts
        agent_system = prompts.get("agent-system", "")
        tool_choice = prompts.get("tool-choice", "")
        template = prompts.get("tool-planning-prompt-template", "")
        
        system_prompt = template.format(
            agentSystem=agent_system,
            toolChoice=tool_choice,
            serverCatalog=str(context.available_tools),
            userMessage=context.history[-1].content if context.history else "",
            dateHints="N/A",
            executedTools="[]",
            latestResult="N/A"
        )
        
        messages = [
            SystemMessage(content=system_prompt),
            *[HumanMessage(content=m.content) if m.role == AgentRole.USER.value else SystemMessage(content=m.content) for m in context.history]
        ]
        
        try:
            response = await self.model.ainvoke(messages)
            raw_content = response.content
            
            if "```json" in raw_content:
                raw_content = raw_content.split("```json")[1].split("```")[0].strip()
            
            data = json.loads(raw_content)
            plans_data = data.get("plans", [])
            
            return [ToolPlan(
                tool_name=p.get("tool"),
                server_name=p.get("server"),
                arguments=p.get("arguments", {}),
                reasoning=p.get("reason", "")
            ) for p in plans_data]
            
        except Exception as e:
            logger.error("planning_failed", error=str(e))
            return []

class LlmComposer(Composer):
    """
    LLM implementation of the Composer port.
    """
    def __init__(self):
        self.model = LlmRuntime.get_chat_model()

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
            userMessage=context.history[-1].content if context.history else "",
            history=str([m.model_dump() for m in context.history]),
            toolResult=tool_results_str
        )
        
        messages = [
            SystemMessage(content=system_prompt)
        ]
        
        async for chunk in self.model.astream(messages):
            # Rationale (Why): Unifying internal results to AiChatChunk (Doc 18).
            yield AiChatChunk(content=chunk.content)
