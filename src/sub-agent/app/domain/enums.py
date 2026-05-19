"""
[Sub-Agent] 도메인 열거형 — 시스템 전역 상수 정의
==================================================
책임: 서브에이전트 전반에서 사용되는 enum 타입을 중앙 정의
아키텍처 위치: Domain Layer — 가장 순수한 계층, 외부 의존성 없음

포함:
  - OrchestrationEngineType: LangGraph / Burr 엔진 선택
  - ProcessStatus: 태스크 상태 기계
  - EventType: SSE 이벤트 타입
  - AgentRole: 메시지 발신자 역할 (user/assistant/system/tool)
  - RedisNamespace: Redis 키 충돌 방지
  - JsonRpcErrorCode: JSON-RPC 2.0 표준 + 커스텀 에러 코드
"""

from enum import Enum

class OrchestrationEngineType(Enum):
    """
    오케스트레이션 엔진 선택.
    LangGraph(LangChain) / Burr 중 설정(orchestration_engine)으로 선택.
    """
    LANGGRAPH = "LANGGRAPH"
    BURR = "BURR"


class ProcessStatus(Enum):
    """
    태스크 상태 기계 (단방향: ACCEPTED → RUNNING → COMPLETED/FAILED).
    WAITING_REVIEW: Supervisor의 HITL(Human-In-The-Loop) 승인 대기.
    """
    ACCEPTED = "ACCEPTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    WAITING_REVIEW = "WAITING_REVIEW"

class ReasonCode(Enum):
    """완료/실패 사유 코드 — 로깅 및 감사 추적용"""
    SUCCESS = "SUCCESS"
    IDEMPOTENCY_HIT = "IDEMPOTENCY_HIT"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    SNAPSHOT_NOT_FOUND = "SNAPSHOT_NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"

class EventType(Enum):
    """
    SSE 스트리밍 이벤트 타입.
    Workflow 실행 단계별로 발행되어 Supervisor/UI에 실시간 전달.
    """
    PLANNING = "PLANNING"
    EXECUTING_TOOL = "EXECUTING_TOOL"
    TOOL_RESULT = "TOOL_RESULT"
    COMPOSING = "COMPOSING"
    CHUNK = "CHUNK"
    PROGRESS = "PROGRESS"
    DONE = "DONE"
    ERROR = "ERROR"

class AgentRole(Enum):
    """대화 메시지 발신자 역할 (OpenAI/Anthropic 메시지 포맷 호환)"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

class RedisNamespace(Enum):
    """
    Redis 키 Prefix — 충돌 방지를 위한 전역 네임스페이스.
    모든 키는 "package:subagent:..." 패턴 사용.
    """
    GLOBAL_PREFIX = "package"
    TASK = "subagent:task"
    IDEMPOTENCY = "subagent:idempotency"
    EVENTS = "subagent:events"
    QUEUE = "subagent:task_queue"

class JsonRpcErrorCode(Enum):
    """
    JSON-RPC 2.0 표준 에러 코드 + 커스텀 Agent 에러.
    -32700 ~ -32000: 표준 예약 범위
    -32000 ~      : 애플리케이션 커스텀 범위
    """
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    
    AGENT_BASE_ERROR = -32000
    UNAUTHORIZED = -32001
