from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from .read_queries import SnapshotVerificationQuery, TaskReadModelQuery
from ...ports.store_ports import A2ATaskStore, ReviewedExecutionSnapshotStore


class SupervisorReadQuery(ABC):
    @abstractmethod
    async def execute(self, task_id: str, **kwargs) -> Any:
        pass


class SupervisorReadQueryFactory:
    def __init__(self, task_store: A2ATaskStore, snapshot_store: ReviewedExecutionSnapshotStore):
        self.queries = {
            "snapshot_verification": SnapshotVerificationQuery(task_store, snapshot_store),
            "task_read_model": TaskReadModelQuery(task_store)
        }

    def get_query(self, query_type: str) -> SupervisorReadQuery:
        return self.queries.get(query_type)
