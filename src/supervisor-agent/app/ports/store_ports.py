from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ..domain.models import ReviewedExecutionSnapshot


class ConversationStore(ABC):
    @abstractmethod
    async def save_message(self, session_id: str, message: Dict[str, Any]):
        pass


class GraphCheckpointStore(ABC):
    @abstractmethod
    async def save_checkpoint(self, task_id: str, checkpoint_data: Dict[str, Any]):
        pass


class SupervisorReviewStore(ABC):
    @abstractmethod
    async def save_review(self, task_id: str, review_data: Dict[str, Any]):
        pass


class A2ATaskStore(ABC):
    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        pass
        
    @abstractmethod
    async def save_task(self, task_id: str, task_data: Dict[str, Any]):
        pass


class ReviewedExecutionSnapshotStore(ABC):
    @abstractmethod
    async def save_snapshot(self, task_id: str, snapshot: ReviewedExecutionSnapshot, ttl: int):
        pass
        
    @abstractmethod
    async def get_snapshot(self, task_id: str) -> Optional[ReviewedExecutionSnapshot]:
        pass
