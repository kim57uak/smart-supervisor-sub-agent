"""
[Sub-Agent] 도메인 예외 계층 — 구조화된 에러 처리
===================================================
책임: 모든 도메인/애플리케이션 예외를 code + message + details 구조로 통일
아키텍처 위치: Domain Layer (Port/Adapter 경계를 넘는 예외 표현)

계층 구조:
  BaseAgentException (Exception)
    ├── SecurityException    (code: UNAUTHORIZED)
    ├── ValidationException  (code: INVALID_PARAMS)
    ├── ExecutionException   (code: EXECUTION_FAILURE)
    └── InfrastructureException (code: INFRASTRUCTURE_ERROR)

모든 예외는 main.py의 글로벌 예외 핸들러가 A2A JSON-RPC 에러로 자동 변환.
"""

from typing import Optional, Any, Dict

class BaseAgentException(Exception):
    """
    모든 Agent 예외의 베이스 클래스.
    - code: 기계가 읽을 수 있는 에러 식별자 (enum 대응)
    - message: 사람이 읽을 수 있는 에러 메시지
    - details: 추가 컨텍스트 정보 (디버깅/로깅용)
    """
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

class SecurityException(BaseAgentException):
    """
    권한/인증 실패.
    발생 상황: scope 밖 접근, session_id 불일치, 토큰 만료 등
    """
    def __init__(self, message: str = "Unauthorized access", details: Optional[Dict[str, Any]] = None):
        super().__init__("UNAUTHORIZED", message, details)

class ValidationException(BaseAgentException):
    """
    요청 검증 실패.
    발생 상황: 필수 파라미터 누락, 타입 불일치, 스키마 위반
    """
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("INVALID_PARAMS", message, details)

class ExecutionException(BaseAgentException):
    """
    그래프 실행 중 오류.
    발생 상황: LLM Planning 실패, 도구 실행 실패, 상태 천이 오류
    """
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("EXECUTION_FAILURE", message, details)

class InfrastructureException(BaseAgentException):
    """
    외부 인프라 장애.
    발생 상황: Redis 연결 실패, LLM API 타임아웃, MCP 서버 다운
    """
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("INFRASTRUCTURE_ERROR", message, details)
