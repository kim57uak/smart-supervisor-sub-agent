"""
[Sub-Agent] A2A(Agent-to-Agent) 프로토콜 스키마
=================================================
책임: A2A 표준에 따른 Agent Card / Discovery 응답 스키마 정의
아키텍처 위치: Schemas Layer (API Contract)

에이전트 카드 구조:
  AgentCard (에이전트 메타정보)
    ├── capabilities: 에이전트가 제공하는 기능 목록
    ├── skills: 상세 도구/스킬 설명
    └── endpoints: A2A 통신 엔드포인트

사용처:
  - discovery.py: /.well-known/agent-card.json
  - Supervisor Agent: sub-agent discovery 및 라우팅
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class AgentSkill(BaseModel):
    """개별 스킬/도구 메타데이터"""
    name: str
    description: str

class AgentEndpoints(BaseModel):
    """A2A 통신 엔드포인트 — message(기본) + stream(옵션)"""
    message: str
    stream: Optional[str] = None

class AgentCard(BaseModel):
    """
    A2A Agent Card — 에이전트 검색/라우팅용 메타데이터.
    /.well-known/agent-card.json 엔드포인트에서 반환.
    """
    name: str
    description: str
    version: str = "1.0.0"
    capabilities: List[str] = Field(default_factory=list)
    skills: List[AgentSkill] = Field(default_factory=list)
    streaming: bool = True
    endpoints: AgentEndpoints
