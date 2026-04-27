from typing import Dict, Any, Optional
from ...domain.enums import EventType
# Assuming an event stream service exists, we will inject it or define a port for it.
from ..persistence.task_event_stream_service import TaskEventStreamService


class SupervisorProgressPublisher:
    """
    Handles publishing progress and chunk events during execution.
    """
    def __init__(self, event_service: TaskEventStreamService):
        self.event_service = event_service

    async def publish_progress(self, task_id: str, stage: str, details: Dict[str, Any] = None):
        payload = {"stage": stage}
        if details:
            payload.update(details)
            
        await self.event_service.append_event(
            task_id, 
            EventType.PROGRESS, 
            payload
        )

    async def publish_chunk(self, task_id: str, agent_key: str, data: Any):
        await self.event_service.append_event(
            task_id, 
            EventType.CHUNK, 
            {"agent": agent_key, "data": data}
        )

    async def publish_reasoning(self, task_id: str, token: str):
        await self.event_service.append_event(
            task_id, 
            EventType.REASONING, 
            {"token": token}
        )

    async def publish_error(self, task_id: str, details: Dict[str, Any]):
        await self.event_service.append_event(
            task_id, 
            EventType.ERROR, 
            details
        )

    async def publish_a2ui(self, task_id: str, payload: Any):
        await self.event_service.append_event(
            task_id,
            EventType.A2UI,
            payload
        )

    async def publish_done(self, task_id: str, result: Dict[str, Any]):
        await self.event_service.append_event(
            task_id, 
            EventType.DONE, 
            result
        )
