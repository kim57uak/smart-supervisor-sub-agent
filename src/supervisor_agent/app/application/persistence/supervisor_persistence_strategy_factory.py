from typing import Dict, Any, Optional, Protocol
from ...domain.models import ReviewedExecutionSnapshot
from ...domain.enums import ReasonCode
from .execution_consistency_coordinator import ExecutionConsistencyCoordinator

class PersistenceStrategy(Protocol):
    """
    Structural interface for persistence strategies.
    """
    async def execute(self, task_id: str, **kwargs) -> Any:
        ...

class ReviewOpenStrategy:
    def __init__(self, coordinator: ExecutionConsistencyCoordinator):
        self.coordinator = coordinator

    async def execute(self, task_id: str, **kwargs) -> Any:
        snapshot = kwargs.get("snapshot")
        ttl = kwargs.get("ttl")
        session_id = kwargs.get("session_id") or snapshot.session_id
        await self.coordinator.persist_snapshot(session_id, task_id, snapshot, ttl)
        await self.coordinator.transition_to_waiting_review(session_id, task_id)

class ApprovedResumeStrategy:
    def __init__(self, coordinator: ExecutionConsistencyCoordinator, event_service):
        self.coordinator = coordinator
        self.event_service = event_service

    async def execute(self, task_id: str, **kwargs) -> Dict[str, Any]:
        expected_version = kwargs.get("expected_version")
        session_id = kwargs.get("session_id", "unknown")
        success, reason, version = await self.coordinator.start_approved_resume(session_id, task_id, expected_version)
        
        initial_cursor = None
        if success or reason == ReasonCode.DUPLICATE_DECISION:
            initial_cursor = await self.event_service.get_initial_cursor(session_id, task_id)
            
        return {
            "success": success,
            "reason_code": reason,
            "state_version": version,
            "initial_cursor": initial_cursor
        }

class ExecutionCompletionStrategy:
    def __init__(self, coordinator: ExecutionConsistencyCoordinator):
        self.coordinator = coordinator

    async def execute(self, task_id: str, **kwargs) -> Any:
        result_data = kwargs.get("result_data")
        session_id = kwargs.get("session_id", "unknown")
        await self.coordinator.complete_execution(session_id, task_id, result_data)

class PersistenceStrategyFactory:
    def __init__(self, coordinator: ExecutionConsistencyCoordinator, event_service):
        self.coordinator = coordinator
        self.strategies: Dict[str, PersistenceStrategy] = {
            "review_open": ReviewOpenStrategy(coordinator),
            "approved_resume": ApprovedResumeStrategy(coordinator, event_service),
            "execution_completion": ExecutionCompletionStrategy(coordinator)
        }

    def get_strategy(self, strategy_type: str) -> PersistenceStrategy:
        return self.strategies.get(strategy_type)
