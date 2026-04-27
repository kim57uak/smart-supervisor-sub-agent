from typing import Dict, Any, Optional
from pydantic import BaseModel
from ...ports.orchestration_ports import HandoffPolicyService
from ...domain.models import FrozenRoutingStep


class HandoffValidationResult(BaseModel):
    allowed: bool
    reason: Optional[str] = None
    suggested_action: str = "CONTINUE"


class DefaultHandoffPolicyService(HandoffPolicyService):
    """
    Evaluates handoff safety and policy as per doc 20.
    """
    def __init__(self, max_depth: int = 5):
        self.max_depth = max_depth

    def evaluate(
        self, 
        current_step: FrozenRoutingStep, 
        context: Dict[str, Any]
    ) -> HandoffValidationResult:
        if current_step.handoff_depth > self.max_depth:
            return HandoffValidationResult(
                allowed=False,
                reason=f"Maximum handoff depth ({self.max_depth}) exceeded",
                suggested_action="BLOCK"
            )
            
        return HandoffValidationResult(allowed=True)
