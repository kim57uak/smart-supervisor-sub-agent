import uuid
import asyncio
import structlog
from typing import Dict, Any, Tuple, Optional

from .hitl_gate_service import HitlGateService
from .supervisor_graph_execution_service import SupervisorGraphExecutionService
from .task_queue_service import TaskQueueService
from ..read.supervisor_read_facade import SupervisorReadFacade
from ..persistence.supervisor_execution_persistence_service import SupervisorExecutionPersistenceService
from ...ports.store_ports import ConversationStore
from ...domain.enums import ReasonCode, ProcessStatus, TaskState
from ...core.config import settings

logger = structlog.get_logger(__name__)

class SupervisorAgentService:
    """
    Main Application Service for Supervisor Agent.
    Orchestrates the lifecycle of task execution using Decoupled Worker pattern.
    """

    def __init__(
        self,
        hitl_gate: HitlGateService,
        graph_execution: SupervisorGraphExecutionService,
        read_facade: SupervisorReadFacade,
        persistence_facade: SupervisorExecutionPersistenceService,
        task_queue: TaskQueueService,
        conversation_store: ConversationStore,
        pre_hitl_a2ui: Any = None,
    ):
        self.hitl_gate = hitl_gate
        self.graph_execution = graph_execution
        self.read_facade = read_facade
        self.persistence_facade = persistence_facade
        self.task_queue = task_queue
        self.conversation_store = conversation_store
        self.pre_hitl_a2ui = pre_hitl_a2ui

    async def execute_task(
        self, session_id: str, message: str, request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Entry point for new task execution.
        Flow: Idempotency -> HITL Check -> (Direct Answer / WAITING_REVIEW / Queue)
        """
        request_id = request_id or str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        
        # Contextual logging
        log = logger.bind(session_id=session_id, request_id=request_id)

        # 1. Idempotency Check
        is_new, effective_task_id = await self.persistence_facade.strategy_factory.coordinator.check_and_reserve_request(
            session_id, request_id, task_id
        )
        if not is_new:
            log.info("duplicate_request_detected", task_id=effective_task_id)
            return await self._get_duplicate_response(session_id, effective_task_id)

        task_id = effective_task_id
        log = log.bind(task_id=task_id)

        # Persist user turn so next request can load it from history.
        await self.conversation_store.save_message(
            session_id,
            {"role": "user", "content": message, "request_id": request_id},
        )

        # 2. HITL (Human-In-The-Loop) Decision
        review_required, plan = await self.hitl_gate.evaluate_and_open_review(
            task_id, session_id, request_id, {"message": message, "session_id": session_id}
        )

        # 3. Process result paths
        if review_required:
            log.info("task_state_transition", to_state=ProcessStatus.WAITING_REVIEW.value)
            
            # Check for pre-HITL A2UI form
            a2ui_form = None
            if self.pre_hitl_a2ui:
                a2ui_form = self.pre_hitl_a2ui.build_pre_hitl_form(plan)
            
            return {
                "task_id": task_id,
                "status": ProcessStatus.WAITING_REVIEW.value,
                "review_reason": getattr(plan, "review_reason", "사용자 승인이 필요합니다."),
                "a2ui": a2ui_form
            }

        if self._is_direct_answer(plan):
            log.info("task_state_transition", mode="direct_answer_shortcut")
            await self.persistence_facade.persist_task_start(session_id, task_id)
            asyncio.create_task(
                self.graph_execution.execute_direct_answer(
                    session_id, task_id, {"message": message, "reasoning": plan.planner_metadata.get("reasoning", "")}
                )
            )
            return self._build_accepted_response(session_id, task_id)

        # 4. Default: Async Execution via Worker
        log.info("task_state_transition", to_state=TaskState.RUNNING.value)
        await self.persistence_facade.persist_task_start(session_id, task_id)
        plan_data = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else plan
        await self.task_queue.enqueue_task(session_id, task_id, plan_data)
        
        return self._build_accepted_response(session_id, task_id)

    async def handle_review_decision(self, request: Any) -> Tuple[bool, ReasonCode, Any]:
        """Processes human review decisions (APPROVE/CANCEL)."""
        session_id = await self._resolve_session_id_for_review(request)
        task_id = request.task_id
        request.session_id = session_id
        log = logger.bind(session_id=session_id, task_id=task_id)

        verification = await self.read_facade.verify_snapshot(
            session_id, task_id, request.model_dump() if hasattr(request, "model_dump") else {}
        )
        if not verification.is_allowed:
            log.warning("snapshot_verification_failed", reason=verification.reason_code)
            return False, verification.reason_code, None

        if request.decision.value == "CANCEL":
            log.info("review_cancelled")
            await self.persistence_facade.cancel_task(session_id, task_id)
            return True, ReasonCode.SUCCESS, None

        return await self._process_approval(session_id, task_id, log)

    async def _resolve_session_id_for_review(self, request: Any) -> str:
        """
        Resolves session_id for HITL review decisions.
        Priority:
        1) explicit request.session_id
        2) request.request_params.session_id
        3) Redis task-session index (task_id -> session_id)
        """
        explicit = getattr(request, "session_id", None)
        if explicit:
            return str(explicit)

        nested = getattr(request, "request_params", None)
        if isinstance(nested, dict):
            nested_sid = nested.get("session_id")
            if nested_sid:
                return str(nested_sid)

        task_id = getattr(request, "task_id", "")
        if not task_id:
            return "unknown"

        try:
            coordinator = self.persistence_facade.strategy_factory.coordinator
            idx_key = f"{settings.redis_prefix}:supervisor:index:task_session:{task_id}"
            raw = await coordinator.redis.get(idx_key)
            if isinstance(raw, bytes):
                raw = raw.decode()
            if raw:
                logger.info("review_session_resolved_from_index", task_id=task_id, session_id=raw)
                return str(raw)
        except Exception as e:
            logger.warning("review_session_resolve_failed", task_id=task_id, error=str(e))

        return "unknown"

    async def cancel_task(self, session_id: str, task_id: str) -> bool:
        """Explicitly cancel a task."""
        log = logger.bind(session_id=session_id, task_id=task_id)
        success = await self.persistence_facade.cancel_task(session_id, task_id)
        if success:
            log.info("task_cancelled_successfully")
        else:
            log.warning("task_cancel_failed_or_already_terminal")
        return success

    async def clear_session(self, session_id: str) -> bool:
        """Clears all session data (conversation and swarm state) for a fixed session ID."""
        log = logger.bind(session_id=session_id)
        try:
            # 1. Clear Conversation History
            from ...core.dependencies import get_conversation_store
            conv_store = await get_conversation_store()
            await conv_store.delete_messages(session_id)
            
            # 2. Clear Swarm State
            from ...core.dependencies import get_swarm_state_store
            swarm_store = await get_swarm_state_store()
            await swarm_store.delete_swarm_state(session_id)
            
            log.info("session_cleared_successfully")
            return True
        except Exception as e:
            log.error("session_clear_failed", error=str(e))
            return False

    def _is_direct_answer(self, plan: Any) -> bool:
        return plan.planner_metadata.get("direct_answer", False) or not plan.routing_queue

    def _build_accepted_response(self, session_id: str, task_id: str) -> Dict[str, Any]:
        return {
            "task_id": task_id,
            "session_id": session_id,
            "status": ProcessStatus.STREAMING.value,
            "stream_endpoint": f"{settings.api_prefix}/stream",
            "a2ui_enabled": settings.a2a.a2ui_enabled,
        }

    async def _get_duplicate_response(self, session_id: str, task_id: str) -> Dict[str, Any]:
        task_model = await self.read_facade.get_task_model(session_id, task_id)
        if not task_model:
            return self._build_accepted_response(session_id, task_id)
        return {
            "task_id": task_id,
            "session_id": session_id,
            "status": task_model.get("state", ProcessStatus.STREAMING.value),
            "stream_endpoint": f"{settings.api_prefix}/stream",
            "a2ui_enabled": settings.a2a.a2ui_enabled,
        }

    async def _process_approval(self, session_id: str, task_id: str, log: Any) -> Tuple[bool, ReasonCode, Any]:
        snapshot = await self.read_facade.get_snapshot(session_id, task_id)
        if not snapshot:
            return False, ReasonCode.SNAPSHOT_NOT_FOUND, None

        resume_result = await self.persistence_facade.persist_approved_resume(
            session_id, task_id, snapshot.state_version
        )
        
        if not resume_result.get("success"):
            reason = resume_result.get("reason_code", ReasonCode.EXECUTION_FAILURE)
            if reason in [ReasonCode.DUPLICATE_DECISION, ReasonCode.DUPLICATE_DECISION.value]:
                return True, ReasonCode.SUCCESS, resume_result
            return False, reason, None

        # Resume execution
        plan_data = snapshot.frozen_plan.model_dump(mode="json") if hasattr(snapshot.frozen_plan, "model_dump") else snapshot.frozen_plan
        await self.task_queue.enqueue_task(session_id, task_id, plan_data)
        
        log.info("review_approved_execution_resumed")
        resume_result["a2ui_enabled"] = settings.a2a.a2ui_enabled
        return True, ReasonCode.SUCCESS, resume_result
