import json
import httpx
import structlog
from datetime import datetime
from urllib.parse import urlparse
from typing import Dict, Any, Tuple, List, Optional
from pydantic import BaseModel, Field

from ...ports.llm_ports import PlanningService
from ...infrastructure.llm.llm_runtime import LlmRuntime
from ...core.config import settings
from ...domain.enums import ApiMethod, AgentRole, EventType

logger = structlog.get_logger()


class PlanItem(BaseModel):
    """Execution step for a sub-agent."""
    agentKey: str
    method: str = ApiMethod.SEND_MESSAGE.value
    reason: str = ""
    priority: int = 0
    preHitlA2ui: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)


class PlannerDecision(BaseModel):
    """Output contract from the planning LLM."""
    complete: bool
    plans: List[PlanItem] = []


class HitlPolicyDecision(BaseModel):
    """Output contract from the HITL policy evaluation LLM."""
    intentType: str = "read_only"
    reviewRequired: bool = False
    reviewReason: str = ""
    riskScore: float = 0.0


class LlmPlanningService(PlanningService):
    """
    Orchestrates 2-step planning:
    1. Routing Plan: Decide which sub-agents to invoke.
    2. HITL Policy: Evaluate if human review is required.
    """
    
    # Class-level cache for sub-agent discovery
    _agent_card_cache: Dict[str, Any] = {}

    def __init__(self):
        self.llm = LlmRuntime.get_chat_model()

    @classmethod
    def get_cached_agent_cards(cls) -> Dict[str, Any]:
        """Returns the current cache of sub-agent cards."""
        return cls._agent_card_cache

    @classmethod
    async def load_agent_cards(cls):
        """Discovers sub-agents using the A2A standard /.well-known/agent-card.json."""
        routing_config = settings.supervisor_config.get("routing", {})
        host_roots = {
            f"{urlparse(info['endpoint']).scheme}://{urlparse(info['endpoint']).netloc}"
            for info in routing_config.values() if info.get("endpoint")
        }
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            for root in host_roots:
                discovery_url = f"{root}/.well-known/agent-card.json"
                
                # Rationale (Why): Adding retry logic to handle race conditions where sub-agents 
                # might still be booting up when the supervisor starts.
                max_discovery_retries = 3
                for attempt in range(max_discovery_retries):
                    try:
                        resp = await client.get(discovery_url)
                        if resp.status_code == 200:
                            data = resp.json()
                            agents = data if isinstance(data, list) else [data]
                            for agent in agents:
                                name = agent.get("name")
                                if name:
                                    cls._agent_card_cache[name] = agent
                                    logger.info("agent_card_loaded", name=name, url=discovery_url)
                            break # Success, move to next root
                        else:
                            logger.warning("a2a_discovery_http_error", url=discovery_url, status=resp.status_code, attempt=attempt+1)
                    except Exception as e:
                        if attempt == max_discovery_retries - 1:
                            logger.warning("a2a_discovery_failed_all_attempts", url=discovery_url, error=str(e))
                        else:
                            import asyncio
                            await asyncio.sleep(1.0 * (attempt + 1))

    async def plan(self, user_input: str, context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        routing_config = settings.supervisor_config.get("routing", {})
        allowed_agents = list(routing_config.keys())
        
        # Rationale (Why): Ensure we have cards for all allowed agents. 
        # If any card is missing, try to reload to catch late-starting agents.
        missing_cards = [key for key in allowed_agents if not any(key.lower() in k.lower() for k in LlmPlanningService._agent_card_cache)]
        
        if not LlmPlanningService._agent_card_cache or missing_cards:
            try:
                logger.info("reloading_agent_cards", missing=missing_cards)
                await self.load_agent_cards()
            except Exception as e:
                logger.error("discovery_reload_failed", error=str(e))

        # 1. Routing Planning
        decision = await self._get_routing_decision(user_input, context)
        
        exec_config = settings.supervisor_config.get("execution", {})
        handoff_config = settings.supervisor_config.get("handoff", {})

        if not decision:
            return False, self._build_direct_answer_plan(exec_config, handoff_config, "Planning failed")
            
        if decision.complete:
            return False, self._build_direct_answer_plan(exec_config, handoff_config, "Direct answer")

        # 2. HITL Policy Evaluation
        hitl = await self._evaluate_hitl_policy(user_input)
        
        # 3. Assemble Plan Data
        routing_config = settings.supervisor_config.get("routing", {})
        routing_queue = []
        for idx, item in enumerate(decision.plans):
            agent_routing = routing_config.get(item.agentKey, {})
            routing_queue.append({
                "order": idx,
                "agent_key": item.agentKey,
                "method": item.method or agent_routing.get("method", ApiMethod.SEND_MESSAGE.value),
                "source_type": "PLANNER",
                "reason": item.reason,
                "priority": item.priority,
                "pre_hitl_a2ui": item.preHitlA2ui,
                "arguments": item.arguments or {"message": user_input},
                "handoff_depth": 0
            })
            logger.info("planner_step_added", agent=item.agentKey, reason=item.reason)
            
        plan_data = {
            "routing_queue": routing_queue,
            "execution_constraints": {
                "max_concurrency": exec_config.get("max-concurrency", 1),
                "stream_allowed": True,
                "invoke_timeout_ms": settings.supervisor_config.get("stream", {}).get("timeout-ms", 120000),
                "max_handoff_depth": handoff_config.get("max-hops", 3),
                "a2ui_allowed": settings.supervisor_config.get("a2ui", {}).get("enabled", False)
            },
            "planner_metadata": {
                "user_message": user_input,
                "review_reason": hitl.reviewReason if hitl.reviewRequired else None,
                "plans_summary": [{"agent": p.agentKey, "reason": p.reason} for p in decision.plans]
            }
        }
        
        return hitl.reviewRequired, plan_data

    async def _get_routing_decision(self, user_input: str, context: Dict[str, Any]) -> Optional[PlannerDecision]:
        system_prompt = settings.prompts["planning-system"]
        template = settings.prompts["planning-template"]
        routing_config = settings.supervisor_config.get("routing", {})
        
        allowed_agents = list(routing_config.keys())
        agent_cards_str = self._build_agent_cards_str(allowed_agents)
        history_str = self._format_history(context.get("history", []))

        user_prompt = template.format(
            planningSystem="",
            today=datetime.now().strftime("%Y-%m-%d"),
            allowedAgents=", ".join(allowed_agents),
            agentCards=agent_cards_str,
            userMessage=user_input,
            history=history_str
        )
        
        try:
            response = await self.llm.ainvoke([("system", system_prompt), ("user", user_prompt)])
            decision = self._safe_parse_json(response.content, PlannerDecision)
            
            if not decision:
                decision = await self._repair_planner_output(response.content)
            return decision
        except Exception as e:
            logger.error("planner_execution_failed", error=str(e))
            return None

    async def _evaluate_hitl_policy(self, user_input: str) -> HitlPolicyDecision:
        try:
            hitl_prompt = settings.prompts["hitl-policy-template"].format(
                hitlPolicySystem="",
                today=datetime.now().strftime("%Y-%m-%d"),
                userMessage=user_input
            )
            
            response = await self.llm.ainvoke([
                ("system", settings.prompts["hitl-policy-system"]),
                ("user", hitl_prompt)
            ])
            return self._safe_parse_json(response.content, HitlPolicyDecision) or HitlPolicyDecision()
        except Exception as e:
            logger.warning("hitl_policy_failed", error=str(e))
            return HitlPolicyDecision()

    def _safe_parse_json(self, text: str, model: Any) -> Optional[Any]:
        try:
            cleaned = text.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
            return model(**json.loads(cleaned))
        except Exception:
            return None

    def _format_history(self, history: List[Dict[str, Any]]) -> str:
        max_turns = settings.supervisor_config.get("history", {}).get("max-turns", 5)
        recent = history[-(max_turns * 2):]
        return "\n".join([f"{m.get('role', AgentRole.USER.value).upper()}: {m.get('content', '')}" for m in recent])

    def _build_agent_cards_str(self, agent_keys: List[str]) -> str:
        lines = []
        cache = LlmPlanningService._agent_card_cache
        for key in agent_keys:
            card = next((v for k, v in cache.items() if key.lower() in k.lower()), None)
            if card:
                skills = ", ".join([s.get("description", s.get("name", "")) for s in card.get("skills", [])])
                lines.append(f"- {key}: {card.get('description', '')} (Skills: {skills})")
            else:
                lines.append(f"- {key}: General purpose sub-agent")
        return "\n".join(lines)

    async def _repair_planner_output(self, invalid_output: str) -> Optional[PlannerDecision]:
        try:
            repair_prompt = settings.prompts["planning-repair-template"].format(invalidOutput=invalid_output)
            response = await self.llm.ainvoke([
                ("system", settings.prompts["planning-system"]),
                ("user", repair_prompt)
            ])
            return self._safe_parse_json(response.content, PlannerDecision)
        except Exception:
            return None

    def _build_direct_answer_plan(self, exec_config: dict, handoff_config: dict, reasoning: str) -> Dict[str, Any]:
        return {
            "routing_queue": [],
            "execution_constraints": {
                "max_concurrency": exec_config.get("max-concurrency", 1),
                "stream_allowed": True,
                "invoke_timeout_ms": settings.supervisor_config.get("stream", {}).get("timeout-ms", 120000),
                "max_handoff_depth": handoff_config.get("max-hops", 3),
                "a2ui_allowed": settings.supervisor_config.get("a2ui", {}).get("enabled", False)
            },
            "planner_metadata": {"reasoning": reasoning, "direct_answer": True}
        }
