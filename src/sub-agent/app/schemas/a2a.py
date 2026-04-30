from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class AgentSkill(BaseModel):
    name: str
    description: str

class AgentEndpoints(BaseModel):
    message: str
    stream: Optional[str] = None

class AgentCard(BaseModel):
    name: str
    description: str
    version: str = "1.0.0"
    capabilities: List[str] = Field(default_factory=list)
    skills: List[AgentSkill] = Field(default_factory=list)
    streaming: bool = True
    endpoints: AgentEndpoints
