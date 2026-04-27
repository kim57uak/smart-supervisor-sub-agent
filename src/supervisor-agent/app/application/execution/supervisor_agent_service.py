from typing import Dict, Any, Tuple
import uuid
import asyncio
from .hitl_gate_service import HitlGateService
from .supervisor_graph_execution_service import SupervisorGraphExecutionService
from ..read.supervisor_read_facade import SupervisorReadFacade
from ..persistence.supervisor_execution_persistence_service import SupervisorExecutionPersistenceService
from ...domain.enums import ReasonCode


class SupervisorAgentService:
    """
    Main Application Service acting as Use Case brancher as per doc 30.
    """
    def __init__(
        self,
        hitl_gate: HitlGateService,
        graph_execution: SupervisorGraphExecutionService,
        read_facade: SupervisorReadFacade,
        persistence_facade: SupervisorExecutionPersistenceService
    ):
        self.hitl_gate = hitl_gate
        self.graph_execution = graph_execution
        self.read_facade = read_facade
        self.persistence_facade = persistence_facade

    async def execute_task(self, session_id: str, message: str) -> Dict[str, Any]:
        task_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        
        # 1. HITL Gate Decision
        review_required, plan = await self.hitl_gate.evaluate_and_open_review(
            task_id, session_id, request_id, {"message": message, "session_id": session_id}
        )
        
        if review_required:
            return {
                "task_id": task_id,
                "status": "WAITING_REVIEW",
                "review_id": plan.trace_id,
                "review_reason": getattr(plan, '_review_reason', '사용자 승인이 필요합니다.')
            }
        
        # 2. Check if this is a direct_answer case (no downstream agents needed)
        is_direct = plan.planner_metadata.get("direct_answer", False)
        if is_direct or not plan.routing_queue:
            # Fire & forget: stream LLM answer token-by-token via SSE
            planner_reasoning = plan.planner_metadata.get("reasoning", "")
            asyncio.create_task(self._stream_direct_answer(task_id, message, planner_reasoning))
            
            return {
                "task_id": task_id,
                "status": "STREAMING",
                "stream_endpoint": f"/a2a/supervisor/stream"
            }
            
        # 3. Downstream Execution (Fire & Forget via asyncio task for STREAM mode)
        asyncio.create_task(self.graph_execution.execute_plan(task_id, plan))
        
        from ...core.config import settings
        a2ui_enabled = settings.supervisor_config.get("a2ui", {}).get("enabled", False)
        
        return {
            "task_id": task_id,
            "status": "STREAMING",
            "stream_endpoint": f"/a2a/supervisor/stream",
            "a2ui_enabled": a2ui_enabled
        }

    async def _stream_direct_answer(self, task_id: str, message: str, planner_reasoning: str = ""):
        """Background task: stream LLM direct answer via event publisher"""
        event_publisher = self.graph_execution.event_publisher
        compose_service = self.graph_execution.compose_service
        
        try:
            # 1. Publish planner reasoning as reasoning event
            if planner_reasoning:
                await event_publisher.publish_reasoning(task_id, planner_reasoning)
            
            await event_publisher.publish_progress(task_id, "composing", {"message": "LLM 응답 생성 중..."})
            
            # 2. Stream token by token
            async for event_type, token in compose_service.stream_compose(
                [], context={"task_id": task_id, "message": message}
            ):
                if event_type == "reasoning":
                    await event_publisher.publish_reasoning(task_id, token)
                else:
                    await event_publisher.publish_chunk(task_id, "supervisor", {"answer": token, "data": None})
            
            await event_publisher.publish_done(task_id, {"status": "completed"})
            
        except Exception as e:
            await event_publisher.publish_error(task_id, {"error": str(e)})

    async def handle_review_decision(self, request: Any) -> Tuple[bool, Any, Any]:
        """
        Handles Review Decide Request.
        """
        # 1. Verify Snapshot via Read Facade
        verification_result = await self.read_facade.verify_snapshot(request.task_id, {})
        
        if not verification_result.is_allowed:
            return False, verification_result.reason_code, None

        if request.decision.value == "CANCEL":
            # Simplified cancel logic
            return True, ReasonCode.SUCCESS, None

        if request.decision.value == "APPROVE":
            # 2. Persist Approved Resume via Persistence Facade (CAS logic)
            snapshot = await self.read_facade.query_factory.get_query("snapshot_verification").snapshot_store.get_snapshot(request.task_id)
            expected_version = snapshot.state_version
            
            resume_result = await self.persistence_facade.persist_approved_resume(request.task_id, expected_version)
            
            if not resume_result["success"]:
                return False, resume_result["reason_code"], None

            # 3. Resume Graph Execution asynchronously
            asyncio.create_task(self.graph_execution.execute_plan(request.task_id, snapshot.frozen_plan))
            
            from ...core.config import settings
            a2ui_enabled = settings.supervisor_config.get("a2ui", {}).get("enabled", False)
            resume_result["a2ui_enabled"] = a2ui_enabled
            
            return True, ReasonCode.SUCCESS, resume_result
