from typing import Dict, Any, Optional
from .supervisor_read_query_factory import ReadQueryFactory
from ...domain.models import ReviewedExecutionSnapshot


class SupervisorReadFacade:
    """
    Facade for all read operations as per doc 30.
    Single entrypoint for read scenarios.
    """
    def __init__(self, query_factory: ReadQueryFactory):
        self.query_factory = query_factory

    async def verify_snapshot(self, session_id: str, task_id: str, request_params: Dict[str, Any]) -> Any:
        query = self.query_factory.get_query("snapshot_verification")
        return await query.execute(task_id, session_id=session_id, request_params=request_params)

    async def get_task_model(self, session_id: str, task_id: str) -> Optional[Dict[str, Any]]:
        query = self.query_factory.get_query("task_read_model")
        return await query.execute(task_id, session_id=session_id)

    async def get_snapshot(self, session_id: str, task_id: str) -> Optional[ReviewedExecutionSnapshot]:
        # Reuse snapshot_store from the verification query
        query = self.query_factory.get_query("snapshot_verification")
        return await query.snapshot_store.get_snapshot(session_id, task_id)
