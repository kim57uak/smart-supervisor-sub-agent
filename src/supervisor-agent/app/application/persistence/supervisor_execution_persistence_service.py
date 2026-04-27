from typing import Dict, Any
from .supervisor_persistence_strategy_factory import SupervisorPersistenceStrategyFactory
from ...domain.models import ReviewedExecutionSnapshot


class SupervisorExecutionPersistenceService:
    """
    Facade for all persistence operations as per doc 30.
    Single entrypoint for write scenarios.
    """
    def __init__(self, strategy_factory: SupervisorPersistenceStrategyFactory):
        self.strategy_factory = strategy_factory

    async def persist_review_open(self, task_id: str, snapshot: ReviewedExecutionSnapshot, ttl: int):
        strategy = self.strategy_factory.get_strategy("review_open")
        await strategy.execute(task_id, snapshot=snapshot, ttl=ttl)

    async def persist_approved_resume(self, task_id: str, expected_version: int) -> Dict[str, Any]:
        strategy = self.strategy_factory.get_strategy("approved_resume")
        return await strategy.execute(task_id, expected_version=expected_version)

    async def persist_execution_completion(self, task_id: str, result_data: Dict[str, Any]):
        strategy = self.strategy_factory.get_strategy("execution_completion")
        await strategy.execute(task_id, result_data=result_data)
