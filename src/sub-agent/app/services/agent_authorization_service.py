import structlog
from typing import Optional, List
from app.ports.interfaces import Store
from app.domain.exceptions import SecurityException

logger = structlog.get_logger(__name__)

class AgentAuthorizationService:
    """
    Enforces scope-based authorization for agent requests.
    Implements Document 11 (Security Model) and 19 (Runtime Sequence).
    """
    def __init__(self, allowed_scopes: List[str]):
        self.allowed_scopes = allowed_scopes

    async def assert_authorized(self, session_id: str, scope: str) -> None:
        """
        Validates if the session is allowed to access the requested scope.
        """
        # Rationale (Why): Security must be enforced at the entry point (Doc 11).
        # For now, we perform simple scope allowlist validation.
        
        if scope not in self.allowed_scopes:
            logger.warning("unauthorized_scope_access", session_id=session_id, scope=scope)
            raise SecurityException(
                message=f"Scope '{scope}' is not allowed for this agent.",
                details={"allowed_scopes": self.allowed_scopes, "requested_scope": scope}
            )
            
        logger.info("authorization_successful", session_id=session_id, scope=scope)
