from typing import Dict, Any, Tuple, List, Optional
from pydantic import BaseModel, Field
import json
from ...ports.llm_ports import SupervisorPlanningService
from ...infrastructure.llm.llm_runtime import LlmRuntime
from ...core.config import settings
import structlog

logger = structlog.get_logger()


# ─── prompts.yml [출력 계약]과 1:1 매칭 ───

class PlanItem(BaseModel):
    """prompts.yml plans[*] 출력 계약"""
    agentKey: str
    method: str = "message/send"
    reason: str = ""
    priority: int = 0
    preHitlA2ui: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=lambda: {})


class PlannerDecision(BaseModel):
    """
    prompts.yml [출력 계약] 정합:
    - complete: boolean
    - plans: array<object>
    추론, 설명, 마크다운은 금지 → reasoning 필드 없음
    review_required는 hitl-policy 프롬프트에서 별도 평가
    """
    complete: bool
    plans: List[PlanItem] = []


class HitlPolicyDecision(BaseModel):
    """
    prompts.yml hitl-policy [작성 규칙] 정합:
    - intentType: "read_only" | "data_mutation" | "unknown"
    - reviewRequired: boolean
    - reviewReason: string
    - riskScore: float (0~1)
    """
    intentType: str = "read_only"
    reviewRequired: bool = False
    reviewReason: str = ""
    riskScore: float = 0.0


class LlmSupervisorPlanningService(SupervisorPlanningService):
    # Global cache for agent cards (loaded at startup via A2A standard discovery)
    _agent_card_cache: Dict[str, Any] = {}

    def __init__(self):
        self.llm = LlmRuntime.get_chat_model()

    @classmethod
    async def load_agent_cards(cls):
        """
        A2A Standard Discovery: GET /.well-known/agent.json
        supervisor.yml routing 설정에서 호스트를 추출하여 에이전트 카드를 로딩한다.
        """
        import httpx
        from urllib.parse import urlparse
        
        routing_config = settings.supervisor_config.get("routing", {})
        
        host_roots = set()
        for info in routing_config.values():
            endpoint = info.get("endpoint", "")
            if endpoint:
                parsed = urlparse(endpoint)
                host_roots.add(f"{parsed.scheme}://{parsed.netloc}")
        
        for root in host_roots:
            discovery_url = f"{root}/.well-known/agent.json"
            logger.info("a2a_discovery_started", url=discovery_url)
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(discovery_url)
                    if resp.status_code == 200:
                        agents_data = resp.json()
                        if isinstance(agents_data, list):
                            for agent in agents_data:
                                name = agent.get("name", "")
                                cls._agent_card_cache[name] = agent
                                logger.info("agent_card_loaded", name=name)
                        elif isinstance(agents_data, dict):
                            name = agents_data.get("name", "unknown")
                            cls._agent_card_cache[name] = agents_data
                            logger.info("agent_card_loaded", name=name)
            except Exception as e:
                logger.warning("a2a_discovery_failed", url=discovery_url, error=str(e))

    def _build_agent_cards_str(self, allowed_agents_list: List[str]) -> str:
        """에이전트 카드 캐시에서 플래닝 프롬프트용 요약 문자열을 생성한다."""
        lines = []
        for agent_key in allowed_agents_list:
            card = next(
                (v for k, v in self._agent_card_cache.items() if agent_key.lower() in k.lower()),
                None
            )
            if card:
                desc = card.get("description", "")
                skills = card.get("skills", [])
                skills_str = ", ".join([s.get("description", s.get("name", "")) for s in skills])
                caps = card.get("capabilities", {})
                streaming = caps.get("streaming", False) if isinstance(caps, dict) else False
                lines.append(
                    f"- {agent_key}:\n"
                    f"  설명: {desc}\n"
                    f"  보유 스킬: {skills_str}\n"
                    f"  streaming: {streaming}"
                )
            else:
                lines.append(f"- {agent_key}:\n  설명: {agent_key} 하위 에이전트\n  기능: 일반 기능")
        return "\n".join(lines)

    async def plan(self, user_input: str, context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        1단계: prompts.yml planning-* 프롬프트로 라우팅 결정 (complete + plans)
        2단계: prompts.yml hitl-policy-* 프롬프트로 HITL 판정 (reviewRequired)
        """
        # ── 1단계: 라우팅 플래닝 ──
        system_prompt = settings.prompts["planning-system"]
        planning_template = settings.prompts["planning-template"]
        
        exec_config = settings.supervisor_config.get("execution", {})
        handoff_config = settings.supervisor_config.get("handoff", {})
        routing_config = settings.supervisor_config.get("routing", {})
        
        if not self._agent_card_cache:
            await self.load_agent_cards()
            
        allowed_agents_list = list(routing_config.keys())
        allowed_agents_str = ", ".join(allowed_agents_list)
        agent_cards_str = self._build_agent_cards_str(allowed_agents_list)
        
        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # 히스토리 로딩 (supervisor.yml 정책 반영)
        history_config = settings.supervisor_config.get("history", {})
        max_turns = history_config.get("max-turns", 5)
        raw_history = context.get("history", [])
        
        # 최근 N턴 추출 (user+assistant 쌍 기준이므로 2*max_turns)
        recent_history = raw_history[-(max_turns * 2):] if raw_history else []
        history_str = ""
        if recent_history:
            for msg in recent_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                history_str += f"{role.upper()}: {content}\n"

        user_prompt = planning_template.format(
            planningSystem="",
            today=today_str,
            allowedAgents=allowed_agents_str,
            agentCards=agent_cards_str,
            userMessage=user_input,
            history=history_str
        )
        
        try:
            # raw JSON 파싱 (with_structured_output 사용하지 않음 - prompts.yml 출력 계약 존중)
            response = await self.llm.ainvoke([
                ("system", system_prompt),
                ("user", user_prompt)
            ])
            
            raw_text = response.content.strip()
            decision = self._parse_planner_output(raw_text)
            
            if decision is None:
                # 파싱 실패 → planning-repair-template 사용
                decision = await self._repair_planner_output(raw_text)
            
            if decision is None:
                # repair도 실패 → direct answer fallback
                logger.error("planner_parse_and_repair_failed", raw=raw_text[:200])
                return False, self._build_direct_answer_plan(exec_config, handoff_config, "Planner output parse failed")
            
            logger.info("planner_decision",
                        complete=decision.complete,
                        plans_count=len(decision.plans))
            
            # 계약 검증: complete=false이면 plans 필수
            if not decision.complete and not decision.plans:
                logger.warning("planner_contract_violation", detail="complete=false but plans empty")
                return False, self._build_direct_answer_plan(exec_config, handoff_config, "Contract violation: no plans")
            
            # Direct answer: complete=true, plans=[]
            if decision.complete:
                return False, self._build_direct_answer_plan(exec_config, handoff_config, "LLM direct answer")
            
            # ── 2단계: HITL 정책 판정 (downstream 호출이 필요한 경우에만) ──
            review_required = await self._evaluate_hitl_policy(user_input, today_str)
            
            # Build routing_queue from plans
            routing_queue = []
            for idx, plan_item in enumerate(decision.plans):
                agent_routing = routing_config.get(plan_item.agentKey, {})
                default_method = agent_routing.get("method", "message/send")
                
                routing_queue.append({
                    "order": idx,
                    "agent_key": plan_item.agentKey,
                    "method": plan_item.method or default_method,
                    "source_type": "PLANNER",
                    "reason": plan_item.reason,
                    "priority": plan_item.priority,
                    "pre_hitl_a2ui": plan_item.preHitlA2ui,
                    "arguments": plan_item.arguments if plan_item.arguments else {"message": user_input},
                    "handoff_depth": 0
                })
            
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
                    "plans_summary": [{"agentKey": p.agentKey, "reason": p.reason} for p in decision.plans]
                }
            }
            
            return review_required, plan_data
            
        except Exception as e:
            logger.error("planner_error", error=str(e))
            return False, self._build_direct_answer_plan(exec_config, handoff_config, f"Planner error: {str(e)}")

    def _parse_planner_output(self, raw_text: str) -> Optional[PlannerDecision]:
        """prompts.yml 출력 계약에 따라 raw JSON을 파싱한다."""
        try:
            # Remove markdown code fences if present
            text = raw_text
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
            
            data = json.loads(text)
            return PlannerDecision(**data)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("planner_output_parse_error", error=str(e), raw=raw_text[:200])
            return None

    async def _repair_planner_output(self, invalid_output: str) -> Optional[PlannerDecision]:
        """prompts.yml planning-repair-template을 사용하여 계약 위반 출력을 교정한다."""
        try:
            repair_template = settings.prompts["planning-repair-template"]
        except KeyError:
            logger.warning("planning_repair_template_missing_in_prompts_yml")
            return None
            
        repair_prompt = repair_template.format(invalidOutput=invalid_output)
        
        try:
            response = await self.llm.ainvoke([
                ("system", settings.prompts["planning-system"]),
                ("user", repair_prompt)
            ])
            return self._parse_planner_output(response.content.strip())
        except Exception as e:
            logger.error("planner_repair_failed", error=str(e))
            return None

    async def _evaluate_hitl_policy(self, user_input: str, today_str: str) -> bool:
        """
        prompts.yml hitl-policy-system / hitl-policy-template을 사용하여
        현재 요청의 HITL review 필요 여부를 별도 평가한다.
        """
        try:
            hitl_system = settings.prompts["hitl-policy-system"]
            hitl_template = settings.prompts["hitl-policy-template"]
            
            hitl_prompt = hitl_template.format(
                hitlPolicySystem="",
                today=today_str,
                userMessage=user_input
            )
            
            response = await self.llm.ainvoke([
                ("system", hitl_system),
                ("user", hitl_prompt)
            ])
            
            raw = response.content.strip()
            # Parse HITL policy JSON
            text = raw
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
            
            data = json.loads(text)
            hitl_decision = HitlPolicyDecision(**data)
            
            logger.info("hitl_policy_decision",
                        intentType=hitl_decision.intentType,
                        reviewRequired=hitl_decision.reviewRequired,
                        riskScore=hitl_decision.riskScore)
            
            return hitl_decision.reviewRequired
            
        except Exception as e:
            logger.warning("hitl_policy_evaluation_failed", error=str(e))
            # fail-closed: 판정 실패 시 review 불필요로 처리 (read_only 기본)
            return False

    def _build_direct_answer_plan(self, exec_config: dict, handoff_config: dict, reasoning: str) -> Dict[str, Any]:
        """직접 답변 모드용 plan_data를 생성한다."""
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
