from typing import Protocol, Dict, Any, Optional, List
from ..domain.models import ReviewedExecutionSnapshot

class ConversationStore(Protocol):
    async def save_message(self, session_id: str, message: Dict[str, Any]):
        ...

    async def get_messages(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        ...

class GraphCheckpointStore(Protocol):
    async def save_checkpoint(self, session_id: str, task_id: str, checkpoint_data: Dict[str, Any]):
        ...

class ReviewStore(Protocol):
    async def save_review(self, session_id: str, task_id: str, review_data: Dict[str, Any]):
        ...

class TaskStore(Protocol):
    async def get_task(self, session_id: str, task_id: str) -> Optional[Dict[str, Any]]:
        ...
        
    async def save_task(self, session_id: str, task_id: str, task_data: Dict[str, Any]):
        ...

class ExecutionSnapshotStore(Protocol):
    async def save_snapshot(self, session_id: str, task_id: str, snapshot: ReviewedExecutionSnapshot, ttl: int):
        ...
        
    async def get_snapshot(self, session_id: str, task_id: str) -> Optional[ReviewedExecutionSnapshot]:
        ...

class SwarmStateStore(Protocol):
    async def save_swarm_state(self, session_id: str, swarm_state: Dict[str, Any]):
        ...

    async def get_swarm_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        ...
