from typing import Optional, Any, Dict

class BaseAgentException(Exception):
    """Base exception for all agent-related errors. Implements Document 10."""
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

class SecurityException(BaseAgentException):
    """Raised when security or authorization fails. Implements Document 11."""
    def __init__(self, message: str = "Unauthorized access", details: Optional[Dict[str, Any]] = None):
        super().__init__("UNAUTHORIZED", message, details)

class ValidationException(BaseAgentException):
    """Raised when request validation fails."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("INVALID_PARAMS", message, details)

class ExecutionException(BaseAgentException):
    """Raised during graph execution (planning/tool calls)."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("EXECUTION_FAILURE", message, details)

class InfrastructureException(BaseAgentException):
    """Raised when external infrastructure (Redis/LLM) is down."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("INFRASTRUCTURE_ERROR", message, details)
