from typing import Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
import uuid
import structlog
from ...domain.models import FrozenExecutionPlan, ReviewedExecutionSnapshot, FrozenRoutingStep, ExecutionConstraintSet
from ...domain.enums import ExecutionMode
from ...ports.llm_ports import SupervisorPlanningService
from ..persistence.supervisor_execution_persistence_service import SupervisorExecutionPersistenceService
from ...common.utils.canonical_json import PlanHashCalculator
from ...core.config import settings

logger = structlog.get_logger()


class HitlGateService:
    def __init__(
        self, 
        planning_service: SupervisorPlanningService,
        persistence_facade: SupervisorExecutionPersistenceService
    ):
        self.planning_service = planning_service
        self.persistence_facade = persistence_facade

    async def evaluate_and_open_review(
        self, 
        task_id: str, 
        session_id: str, 
        request_id: str, 
        input_data: Dict[str, Any]
    ) -> Tuple[bool, FrozenExecutionPlan]:
        
        # 1. Call planner
        review_required, plan_data = await self.planning_service.plan(
            user_input=input_data.get("message", ""),
            context={"session_id": session_id}
        )
        
        # 2. Build Plan
        routing_steps = [FrozenRoutingStep(**step) for step in plan_data["routing_queue"]]
        constraints = ExecutionConstraintSet(**plan_data["execution_constraints"])
        
        request_hash = PlanHashCalculator.calculate_request_hash(input_data)
        frozen_plan_hash = PlanHashCalculator.calculate_frozen_plan_hash(plan_data["routing_queue"])
        
        plan = FrozenExecutionPlan(
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
            routing_queue=routing_steps,
            planner_metadata=plan_data.get("planner_metadata", {}),
            execution_constraints=constraints
        )

        if review_required:
            # 2. Map HITL review_reason
            review_reason = settings.hitl_messages.get("default", "사용자 승인이 필요합니다.")

            snapshot = ReviewedExecutionSnapshot(
                task_id=task_id,
                session_id=session_id,
                request_id=request_id,
                trace_id=plan.trace_id,
                state_version=0,
                resume_token=str(uuid.uuid4()),
                request_hash=request_hash,
                frozen_plan_hash=frozen_plan_hash,
                review_reason=review_reason,
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(hours=24),
                sanitized_input=input_data,
                frozen_plan=plan
            )
            await self.persistence_facade.persist_review_open(task_id, snapshot, ttl=86400)
            
        return review_required, plan
