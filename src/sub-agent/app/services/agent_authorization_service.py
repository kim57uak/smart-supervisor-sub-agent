"""
[Sub-Agent] Scope 기반 권한 인증 서비스
========================================
책임: A2A 요청이 특정 Agent Scope에 접근할 권한이 있는지 검증
아키텍처 위치: Services Layer (도메인 서비스)
원칙: 모든 외부 요청 진입점(API, A2A)에서 첫 번째 게이트로 동작

현재 구현: 단순 Allowlist 매칭
  - allowed_scopes에 포함된 scope만 접근 허용
  - 설정: settings.a2a.scopes (DefaultConfig.A2A_SCOPES)
  - 확장 포인트: session_id 기반 세밀한 권한 검증 추가 가능

보안 원칙:
  - 실패 시 기본 거부(Default-Deny)
  - 승인/거부 모두 로깅
  - 거부 시 SecurityException throw → 글로벌 핸들러가 JSON-RPC 에러 변환
"""

import structlog
from typing import Optional, List
from app.ports.interfaces import Store
from app.domain.exceptions import SecurityException

logger = structlog.get_logger(__name__)

class AgentAuthorizationService:
    """
    Scope 기반 권한 게이트.
    assert_authorized() 통과 못하면 SecurityException → 401/403 응답.
    """
    def __init__(self, allowed_scopes: List[str]):
        self.allowed_scopes = allowed_scopes

    async def assert_authorized(self, session_id: str, scope: str) -> None:
        """
        session_id가 특정 scope에 접근 가능한지 검증.
        현재: 단순 scope allowlist 검사.
        확장: Redis에서 session별 권한 조회 가능.
        """
        if scope not in self.allowed_scopes:
            logger.warning("unauthorized_scope_access", session_id=session_id, scope=scope)
            raise SecurityException(
                message=f"Scope '{scope}' is not allowed for this agent.",
                details={"allowed_scopes": self.allowed_scopes, "requested_scope": scope}
            )
            
        logger.info("authorization_successful", session_id=session_id, scope=scope)
