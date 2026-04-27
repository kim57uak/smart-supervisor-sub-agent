from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
from ...domain.models import ReviewedExecutionSnapshot
from .execution_consistency_coordinator import ExecutionConsistencyCoordinator


class SupervisorPersistenceStrategy(ABC):
    @abstractmethod
    async def execute(self, task_id: str, **kwargs) -> Any:
        pass


class ReviewOpenStrategy(SupervisorPersistenceStrategy):
    def __init__(self, coordinator: ExecutionConsistencyCoordinator):
        self.coordinator = coordinator

    async def execute(self, task_id: str, **kwargs) -> Any:
        snapshot = kwargs.get("snapshot")
        ttl = kwargs.get("ttl")
        await self.coordinator.persist_snapshot(task_id, snapshot, ttl)
        await self.coordinator.transition_to_waiting_review(task_id, snapshot.session_id)


class ApprovedResumeStrategy(SupervisorPersistenceStrategy):
    def __init__(self, coordinator: ExecutionConsistencyCoordinator, event_service):
        self.coordinator = coordinator
        self.event_service = event_service

    async def execute(self, task_id: str, **kwargs) -> Dict[str, Any]:
        expected_version = kwargs.get("expected_version")
        success, reason, version = await self.coordinator.start_approved_resume(task_id, expected_version)
        
        initial_cursor = None
        if success:
            initial_cursor = await self.event_service.get_initial_cursor(task_id)
            
        return {
            "success": success,
            "reason_code": reason,
            "state_version": version,
            "initial_cursor": initial_cursor
        }


class ExecutionCompletionStrategy(SupervisorPersistenceStrategy):
    def __init__(self, coordinator: ExecutionConsistencyCoordinator):
        self.coordinator = coordinator

    async def execute(self, task_id: str, **kwargs) -> Any:
        result_data = kwargs.get("result_data")
        await self.coordinator.complete_execution(task_id, result_data)


class SupervisorPersistenceStrategyFactory:
    def __init__(self, coordinator: ExecutionConsistencyCoordinator, event_service):
        self.strategies = {
            "review_open": ReviewOpenStrategy(coordinator),
            "approved_resume": ApprovedResumeStrategy(coordinator, event_service),
            "execution_completion": ExecutionCompletionStrategy(coordinator)
        }

    def get_strategy(self, strategy_type: str) -> SupervisorPersistenceStrategy:
        return self.strategies.get(strategy_type)
