from typing import Dict, Any, Optional, Protocol
from .read_queries import SnapshotVerificationQuery, TaskReadModelQuery
from ...ports.store_ports import TaskStore, ExecutionSnapshotStore
from ...ports.llm_ports import AgentRegistry

class ReadQuery(Protocol):
    """
    Structural interface for read queries.
    """
    async def execute(self, task_id: str, **kwargs) -> Any:
        ...

class ReadQueryFactory:
    def __init__(self, task_store: TaskStore, snapshot_store: ExecutionSnapshotStore, agent_registry: Optional[AgentRegistry] = None):
        self.queries: Dict[str, ReadQuery] = {
            "snapshot_verification": SnapshotVerificationQuery(task_store, snapshot_store, agent_registry),
            "task_read_model": TaskReadModelQuery(task_store)
        }

    def get_query(self, query_type: str) -> ReadQuery:
        return self.queries.get(query_type)
