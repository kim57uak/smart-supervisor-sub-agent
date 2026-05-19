from typing import Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
import uuid
import asyncio
import structlog

from ...domain.models import (
    FrozenExecutionPlan, 
    ReviewedExecutionSnapshot, 
    FrozenRoutingStep, 
    ExecutionConstraintSet
)
from ...domain.enums import ExecutionMode
from ...ports.llm_ports import PlanningService
from ...ports.store_ports import ConversationStore
from ..persistence.supervisor_execution_persistence_service import SupervisorExecutionPersistenceService
from ...common.utils.canonical_json import PlanHashCalculator
from ...services.prompt_injection_guard import PromptInjectionGuard
from ...core.config import settings

logger = structlog.get_logger()


class HitlGateService:
    """
    Handles HITL (Human-In-The-Loop) evaluation and plan generation.
    """

    def __init__(
        self,
        planning_service: PlanningService,
        persistence_facade: SupervisorExecutionPersistenceService,
        conversation_store: ConversationStore,
    ):
        self.planning_service = planning_service
        self.persistence_facade = persistence_facade
        self.conversation_store = conversation_store

    async def evaluate_and_open_review(
        self, task_id: str, session_id: str, request_id: str, input_data: Dict[str, Any]
    ) -> Tuple[bool, FrozenExecutionPlan]:
        """
        Evaluates the user input, generates an execution plan, and opens a review if required.
        """
        # Rationale (Why): Security is paramount. We must sanitize the raw input from the user 
        # to prevent prompt injection attacks before passing it to the planning LLM.
        # 1. Prepare Context
        raw_history = await self.conversation_store.get_messages(session_id, limit=20)
        # Filter out any unsafe messages from history
        history = []
        for msg in raw_history:
            content = msg.get("content", "")
            if PromptInjectionGuard.is_safe(content):
                history.append(msg)
            else:
                logger.warning("unsafe_message_filtered", content=content)
        raw_message = input_data.get("message", "")
        sanitized_message = PromptInjectionGuard.sanitize(raw_message)

        # Rationale (Why): We combine routing planning and HITL policy evaluation in one service call 
        # to ensure that the HITL decision is based on the exact same context and proposed routing plan,
        # avoiding drift between the plan and the safety review.
        # 2. Call Planner with retry and fallback
        max_retries = 3
        retry_delay = 1  # seconds
        last_error = None

        for attempt in range(max_retries):
            try:
                review_required, plan_data = await self.planning_service.plan(
                    user_input=sanitized_message,
                    context={"session_id": session_id, "history": history}
                )
                break  # Success
            except Exception as e:
                last_error = e
                logger.warning("planning_service_failed", attempt=attempt, error=str(e))
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
        else:
            # Fallback: Create a minimal plan with default constraints
            logger.error("planning_service_failed_after_retries", error=str(last_error))
            review_required = True  # Force review for safety
            plan_data = {
                "routing_queue": [],
                "execution_constraints": {
                    "stream_allowed": False,
                    "max_handoff_depth": 1,
                    "max_steps": 5
                },
                "planner_metadata": {
                    "review_reason": "Planning service unavailable - using fallback plan"
                }
            }

        # 3. Build Frozen Plan
        plan = self._build_execution_plan(
            task_id, session_id, request_id, sanitized_message, plan_data
        )

        # 4. Handle Review Path
        if review_required:
            await self._open_review_session(task_id, session_id, request_id, input_data, plan)

        return review_required, plan

    def _build_execution_plan(
        self, task_id: str, session_id: str, request_id: str, sanitized_message: str, plan_data: Dict[str, Any]
    ) -> FrozenExecutionPlan:
        # Calculate Hashes
        request_hash = PlanHashCalculator.calculate_request_hash({
            "message": sanitized_message,
            "request_id": request_id,
            "session_id": session_id
        })
        
        # Calculate hash using the same format as verification
        routing_steps_dict = [FrozenRoutingStep(**step).model_dump() for step in plan_data["routing_queue"]]
        execution_constraints_dict = ExecutionConstraintSet(**plan_data.get("execution_constraints", {})).model_dump()

        frozen_plan_hash = PlanHashCalculator.calculate_frozen_plan_hash({
            "schema_version": 1,
            "canonicalization_version": 1,
            "task_id": task_id,
            "session_id": session_id,
            "request_id": request_id,
            "routing_queue": routing_steps_dict,
            "execution_constraints": execution_constraints_dict,
            "planner_metadata": plan_data.get("planner_metadata", {})
        })

        return FrozenExecutionPlan(
            task_id=task_id,
            session_id=session_id,
            request_id=request_id,
            trace_id=str(uuid.uuid4()),
            state_version=0,
            execution_mode=ExecutionMode.STREAM,
            request_hash=request_hash,
            frozen_plan_hash=frozen_plan_hash,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
            routing_queue=[FrozenRoutingStep(**step) for step in plan_data["routing_queue"]],
            planner_metadata=plan_data.get("planner_metadata", {}),
            execution_constraints=ExecutionConstraintSet(**plan_data["execution_constraints"]),
            review_reason=plan_data.get("planner_metadata", {}).get("review_reason")
        )

    async def _open_review_session(
        self, task_id: str, session_id: str, request_id: str, input_data: Dict[str, Any], plan: FrozenExecutionPlan
    ) -> None:
        # Rationale (Why): If a review is required, we must persist a "frozen" snapshot of the plan
        # and the exact input. This prevents tampering between the time the review is requested
        # and when the human actually approves it.
        review_reason = plan.review_reason or settings.hitl_messages.get("default", "사용자 승인이 필요합니다.")

        raw_message = input_data.get("message", "")
        try:
            sanitized_message = PromptInjectionGuard.sanitize(raw_message)
        except ValueError:
            sanitized_message = "[INJECTION_BLOCKED]"

        normalized_input = {
            "message": sanitized_message,
            "request_id": request_id,
            "session_id": session_id
        }

        snapshot = ReviewedExecutionSnapshot(
            task_id=task_id,
            session_id=session_id,
            request_id=request_id,
            trace_id=plan.trace_id,
            state_version=0,
            resume_token=str(uuid.uuid4()),
            request_hash=plan.request_hash,
            frozen_plan_hash=plan.frozen_plan_hash,
            review_reason=review_reason,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
            sanitized_input={"message": sanitized_message, "request_id": request_id, "session_id": session_id},
            normalized_input=normalized_input,
            frozen_plan=plan
        )
        
        await self.persistence_facade.persist_review_open(session_id, task_id, snapshot, ttl=86400)
        logger.info("hitl_review_opened", task_id=task_id, reason=review_reason)


class PreHitlA2uiService:
    """
    Identifies if a special input form should be shown before downstream execution (Doc 26).
    """

    def build_pre_hitl_form(self, plan: FrozenExecutionPlan) -> Optional[Dict[str, Any]]:
        if not plan.routing_queue:
            return None

        # Check the first step for pre-HITL A2UI requirements
        first_step = plan.routing_queue[0]
        if first_step.pre_hitl_a2ui:
            return self._get_a2ui_envelope(first_step.pre_hitl_a2ui)

        return None

    def _get_a2ui_envelope(self, form_key: str) -> Dict[str, Any]:
        return {
            "a2ui": {
                "specification": "https://a2ui.org/specification/v0_8/standard_catalog_definition.json",
                "messages": [
                    {
                        "beginRendering": {
                            "surfaceId": "pre-hitl-form",
                            "root": form_key
                        }
                    }
                ]
            }
        }
