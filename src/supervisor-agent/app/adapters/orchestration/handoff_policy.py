from typing import Dict, Any, Optional
from pydantic import BaseModel
from ...ports.orchestration_ports import HandoffPolicyService
from ...domain.models import FrozenRoutingStep
from ...domain.enums import ApiMethod


class HandoffValidationResult(BaseModel):
    allowed: bool
    reason: Optional[str] = None
    suggested_action: str = "CONTINUE"
    handoff_step: Optional[FrozenRoutingStep] = None


class DefaultHandoffPolicyService(HandoffPolicyService):
    """
    Evaluates handoff safety and policy as per doc 20 and doc 11B.
    Checks: feature flag, max depth, route allowlist, method allowlist.
    """
    def __init__(self, max_depth: int = 5):
        self.max_depth = max_depth

    def evaluate(
        self, 
        current_step: FrozenRoutingStep, 
        context: Dict[str, Any]
    ) -> HandoffValidationResult:
        from ...core.config import settings
        handoff_cfg = settings.supervisor_config.get("handoff", {})
        
        # 1. Feature flag check
        if not handoff_cfg.get("enabled", True):
            return HandoffValidationResult(
                allowed=False, 
                reason="Handoff feature is disabled in supervisor.yml",
                suggested_action="BLOCK"
            )

        # 2. Extract handoff directive from result payload if exists
        # In A2A, a handoff is usually indicated by a specific field in the payload
        result_payload = context.get("result_payload", {})
        handoff_directive = result_payload.get("handoff")
        
        if not handoff_directive:
            return HandoffValidationResult(allowed=False, reason="No handoff directive in result")

        target_agent = handoff_directive.get("agent_key")
        target_method = handoff_directive.get("method", ApiMethod.SEND_MESSAGE.value)
        
        if not target_agent:
            return HandoffValidationResult(allowed=False, reason="Handoff target agent_key missing")

        # 3. Depth check
        current_depth = current_step.handoff_depth
        if current_depth >= handoff_cfg.get("max-hops", self.max_depth):
            return HandoffValidationResult(
                allowed=False,
                reason=f"Maximum handoff depth ({self.max_depth}) exceeded",
                suggested_action="BLOCK"
            )

        # 4. Route allowlist check
        routing_cfg = settings.supervisor_config.get("routing", {})
        if target_agent not in routing_cfg:
            return HandoffValidationResult(
                allowed=False,
                reason=f"Handoff target agent '{target_agent}' not in supervisor routing allowlist",
                suggested_action="BLOCK"
            )

        # 5. Method allowlist check
        allowed_methods = handoff_cfg.get("allow-methods", [])
        if allowed_methods and target_method not in allowed_methods:
            return HandoffValidationResult(
                allowed=False,
                reason=f"Handoff method '{target_method}' not in allowlist",
                suggested_action="BLOCK"
            )
            
        # 6. Create the new handoff step
        new_step = FrozenRoutingStep(
            order=current_step.order, # Same order or increment? usually same logical step sequence
            agent_key=target_agent,
            method=target_method,
            source_type="HANDOFF",
            reason=f"Handoff from {current_step.agent_key}: {handoff_directive.get('reason', '')}",
            arguments=handoff_directive.get("arguments", {}),
            handoff_depth=current_depth + 1,
            parent_agent_key=current_step.agent_key
        )

        return HandoffValidationResult(
            allowed=True,
            handoff_step=new_step
        )
