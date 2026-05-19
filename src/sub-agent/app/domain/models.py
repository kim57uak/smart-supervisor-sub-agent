"""
[Sub-Agent] 도메인 모델 — 핵심 비즈니스 객체 정의
===================================================
책임: 서브에이전트의 핵심 도메인 객체(Pydantic Model) 정의
아키텍처 위치: Domain Layer — 가장 내부 계층, infrastructure 의존성 없음

모델 관계:
  AgentTask (1) ──→ (1) AgentExecutionResult
  PlanningContext → List[Message] + List[ToolPlan] + tool_results
  ToolPlan → MCP 도구 실행 단위 (server_name으로 라우팅)

Pydantic v2 사용:
  - model_validate_json() / model_dump_json()으로 직렬화
  - Field(default_factory=)로 가변 기본값 처리
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from .enums import ProcessStatus

class Message(BaseModel):
    """대화 메시지 단위. role=user/assistant/system/tool"""
    role: str
    content: str

class ToolPlan(BaseModel):
    """
    MCP 도구 실행 계획.
    - tool_name: 실행할 도구 이름 (e.g. "getWeatherForecastByLocation")
    - server_name: 도구를 호스팅하는 MCP 서버 식별자 (라우팅 필수)
    - arguments: inputSchema에 맞춘 도구 파라미터
    - reasoning: LLM이 도구를 선택한 이유 (로깅용)
    """
    tool_name: str
    server_name: str
    arguments: Dict[str, Any]
    reasoning: str

class AiChatChunk(BaseModel):
    """
    SSE 스트리밍 청크.
    stream_compose()에서 청크 단위로 생성되어 실시간 UI 업데이트에 사용.
    - content: 생성 중인 텍스트 조각
    - metadata: 추가 메타데이터 (token count 등)
    """
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class PlanningContext(BaseModel):
    """
    Planning/Composition 단계의 컨텍스트.
    Planner와 Composer 포트 사이를 전달하는 데이터 객체.
    - history: 대화 이력
    - available_tools: LLM이 선택 가능한 도구 목록
    - tool_results: 실행된 도구의 결과 집합
    """
    session_id: str
    history: List[Message] = Field(default_factory=list)
    available_tools: List[Dict[str, Any]] = Field(default_factory=list)
    current_plan: Optional[ToolPlan] = None
    tool_results: List[Dict[str, Any]] = Field(default_factory=list)

class AgentExecutionResult(BaseModel):
    """에이전트 실행 완료 결과"""
    task_id: str
    final_answer: str
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    usage_metadata: Dict[str, int] = Field(default_factory=dict)

class AgentTask(BaseModel):
    """
    실행 중인 에이전트 태스크.
    - state_version: 낙관적 락을 위한 버전 필드 (CAS 패턴)
      읽을 때 0, 저장 시점에 ExecutionConsistencyCoordinator가 +1
    - status: ProcessStatus 상태 기계에 따른 현재 상태
    """
    task_id: str
    session_id: str
    request_id: str
    status: ProcessStatus
    result: Optional[AgentExecutionResult] = None
    state_version: int = 0
