from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from .enums import ProcessStatus

class Message(BaseModel):
    role: str
    content: str

class ToolPlan(BaseModel):
    tool_name: str
    server_name: str  # Mandatory for MCP routing
    arguments: Dict[str, Any]
    reasoning: str

class AiChatChunk(BaseModel):
    """
    Standard chunk for streaming responses (Document 18).
    """
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class PlanningContext(BaseModel):
    session_id: str
    history: List[Message] = Field(default_factory=list)
    available_tools: List[Dict[str, Any]] = Field(default_factory=list)
    current_plan: Optional[ToolPlan] = None
    tool_results: List[Dict[str, Any]] = Field(default_factory=list)

class AgentExecutionResult(BaseModel):
    task_id: str
    final_answer: str
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    usage_metadata: Dict[str, int] = Field(default_factory=dict)

class AgentTask(BaseModel):
    task_id: str
    session_id: str
    request_id: str
    status: ProcessStatus
    result: Optional[AgentExecutionResult] = None
    state_version: int = 0
