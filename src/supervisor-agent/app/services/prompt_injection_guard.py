import re
import structlog

logger = structlog.get_logger()

class PromptInjectionGuard:
    """
    Implements security guard rules as per doc 09 and 14.
    Protects against common prompt injection patterns.
    """
    
    # Simple patterns for injection detection
    INJECTION_PATTERNS = [
        r"(?i)ignore\s+all\s+previous\s+instructions",
        r"(?i)system\s+prompt",
        r"(?i)you\s+are\s+now\s+an\s+admin",
        r"(?i)output\s+the\s+full\s+prompt",
        r"(?i)bypass\s+safety",
        r"(?i)DAN\s+mode"
    ]

    @staticmethod
    def sanitize(text: str) -> str:
        """
        Basic sanitization. In a production environment, 
        this would call an external ML model or a more robust library.
        """
        if not text:
            return text
            
        detected = False
        for pattern in PromptInjectionGuard.INJECTION_PATTERNS:
            if re.search(pattern, text):
                logger.warning("prompt_injection_attempt_detected", pattern=pattern)
                detected = True
                # Basic defense: wrap or tag
                text = f"[POTENTIAL_INJECTION_BLOCKED] {text}"
                break
                
        return text

    @staticmethod
    def is_safe(text: str) -> bool:
        """Returns False if any dangerous patterns are detected."""
        for pattern in PromptInjectionGuard.INJECTION_PATTERNS:
            if re.search(pattern, text):
                return False
        return True
