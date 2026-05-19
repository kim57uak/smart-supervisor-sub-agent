import re
import structlog

logger = structlog.get_logger()

class PromptInjectionGuard:
    """
    Implements security guard rules as per doc 09 and 14.
    Multi-layer protection: regex patterns + heuristic scoring.
    """
    
    INJECTION_PATTERNS = [
        r"(?i)ignore\s+all\s+previous\s+instructions",
        r"(?i)forget\s+(all\s+)?(prior|previous)\s+(instructions|prompts|directions)",
        r"(?i)(reveal|show|output|print|display|leak|dump)\s+(the\s+)?(full|complete|entire|raw)\s+(prompt|instructions|system|configuration)",
        r"(?i)you\s+are\s+(now\s+)?an?\s+(admin|administrator|superuser|root|god)",
        r"(?i)bypass\s+(safety|security|restrictions|constraints|guidelines|rules)",
        r"(?i)(DAN|STAN|DUDE|jailbreak|prompt\s+inject)",
        r"(?i)act\s+as\s+(if\s+you\s+are|though\s+you\s+are)\s+(unrestricted|uncensored|unfiltered)",
        r"(?i)(remove|disable|override)\s+(all\s+)?(restrictions|constraints|limitations|filters)",
        r"(?i)(pretend|imagine|simulate)\s+(that\s+)?(you\s+are|you\'?re)\s+(not\s+)?(an?\s+)?(AI|assistant|bot)",
        r"(?i)do\s+not\s+(follow|obey|adhere\s+to)\s+(your\s+)?(rules|guidelines|instructions)",
        r"(?i)new\s+rule|new\s+prompt|updated\s+(instructions|guidelines)",
    ]

    SUSPICIOUS_PATTERNS = [
        r"(?i)(roleplay|role.play)\s+as",
        r"(?i)(hypothetical|fictional)\s+(scenario|situation)\s+where",
        r"(?i)this\s+is\s+(a\s+)?(test|experiment|simulation)",
        r"(?i)(base64|rot13|hex|binary|encoded)",
        r"(?i)(step.by.step|chain.of.thought)\s+(without\s+)?(restrictions|limits)",
    ]

    @staticmethod
    def sanitize(text: str) -> str:
        if not text:
            return text

        if not PromptInjectionGuard.is_safe(text):
            logger.warning("prompt_injection_detected_and_blocked", text=text[:100])
            raise ValueError("Prompt injection detected and blocked")

        suspicion_score = PromptInjectionGuard._suspicion_score(text)
        if suspicion_score >= 3:
            logger.warning("prompt_suspicion_high", text=text[:100], score=suspicion_score)
            raise ValueError("Prompt injection detected and blocked")

        return text

    @staticmethod
    def is_safe(text: str) -> bool:
        for pattern in PromptInjectionGuard.INJECTION_PATTERNS:
            if re.search(pattern, text):
                return False
        return True

    @staticmethod
    def _suspicion_score(text: str) -> int:
        score = 0
        for pattern in PromptInjectionGuard.SUSPICIOUS_PATTERNS:
            if re.search(pattern, text):
                score += 1
        return score
