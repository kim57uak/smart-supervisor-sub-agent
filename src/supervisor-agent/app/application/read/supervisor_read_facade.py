from typing import Dict, Any, Optional
from .supervisor_read_query_factory import SupervisorReadQueryFactory


class SupervisorReadFacade:
    """
    Facade for all read operations as per doc 30.
    Single entrypoint for read scenarios.
    """
    def __init__(self, query_factory: SupervisorReadQueryFactory):
        self.query_factory = query_factory

    async def verify_snapshot(self, task_id: str, request_params: Dict[str, Any]) -> Any:
        query = self.query_factory.get_query("snapshot_verification")
        return await query.execute(task_id, request_params=request_params)

    async def get_task_model(self, task_id: str) -> Optional[Dict[str, Any]]:
        query = self.query_factory.get_query("task_read_model")
        return await query.execute(task_id)
