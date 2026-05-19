import structlog
from typing import Optional

from app.adapters.llm.voice_adapter_interface import VoiceAdapter
from app.adapters.llm.openai_realtime_adapter import OpenAiRealtimeAdapter
from app.adapters.llm.google_realtime_adapter import GoogleRealtimeAdapter
from app.core.config import settings

logger = structlog.get_logger(__name__)

class VoiceAdapterFactory:
    """
    설정에 따라 적절한 VoiceAdapter 구현체를 생성하는 팩토리 클래스.
    """

    @staticmethod
    def create_adapter(provider: Optional[str] = None) -> VoiceAdapter:
        # Rationale (Why): Separating voice and chat providers. 
        # Defaults to settings.llm.voice_provider (Google).
        provider = (provider or settings.llm.voice_provider).lower()
        
        logger.info("creating_voice_adapter", provider=provider)

        if provider == "openai":
            return OpenAiRealtimeAdapter()
        elif provider == "google":
            return GoogleRealtimeAdapter()
        else:
            # Fallback to OpenAI as default robust STT provider
            logger.warning("unsupported_voice_provider_falling_back_to_openai", provider=provider)
            return OpenAiRealtimeAdapter()
