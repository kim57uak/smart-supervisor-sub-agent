from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from ..domain.enums import Decision


class ReviewDecideRequest(BaseModel):
    task_id: str
    decision: Decision
    review_id: Optional[str] = None
    comment: Optional[str] = None
    client_request_id: Optional[str] = None
    session_id: Optional[str] = None
    request_params: Optional[Dict[str, Any]] = None


class ReviewApproveAck(BaseModel):
    task_id: str
    session_id: Optional[str] = None
    state_version: int
    execution_mode: str
    resume_accepted: bool = True
    stream_resume_required: bool = False
    stream_method: Optional[str] = None
    stream_endpoint: Optional[str] = None
    initial_cursor: Optional[str] = None
    a2ui_enabled: bool = False


class ReviewRejectResult(BaseModel):
    task_id: str
    resume_accepted: bool = False
    reason_code: str
    current_state: str
    state_version: int


class SendMessageParams(BaseModel):
    session_id: str
    message: str
    request_id: Optional[str] = None
    model: Optional[str] = None


class TaskEventsParams(BaseModel):
    task_id: str
    session_id: Optional[str] = None
    cursor: Optional[str] = None
    replay: bool = True
