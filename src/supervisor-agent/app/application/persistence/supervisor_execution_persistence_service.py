from typing import Dict, Any, Optional
from .supervisor_persistence_strategy_factory import PersistenceStrategyFactory
from ...domain.models import ReviewedExecutionSnapshot


class SupervisorExecutionPersistenceService:
    """
    Facade for all persistence operations as per doc 30.
    Single entrypoint for write scenarios.
    """
    def __init__(self, strategy_factory: PersistenceStrategyFactory):
        self.strategy_factory = strategy_factory

    async def persist_review_open(self, session_id: str, task_id: str, snapshot: ReviewedExecutionSnapshot, ttl: int):
        strategy = self.strategy_factory.get_strategy("review_open")
        await strategy.execute(task_id, session_id=session_id, snapshot=snapshot, ttl=ttl)

    async def persist_approved_resume(self, session_id: str, task_id: str, expected_version: int) -> Dict[str, Any]:
        strategy = self.strategy_factory.get_strategy("approved_resume")
        return await strategy.execute(task_id, session_id=session_id, expected_version=expected_version)

    async def persist_execution_completion(self, session_id: str, task_id: str, result_data: Dict[str, Any]):
        strategy = self.strategy_factory.get_strategy("execution_completion")
        await strategy.execute(task_id, session_id=session_id, result_data=result_data)

    async def load_swarm_state(self, session_id: str) -> Dict[str, Any]:
        """
        Loads agent shared state for the session (Doc 03).
        """
        return await self.strategy_factory.coordinator.load_swarm_state(session_id)
