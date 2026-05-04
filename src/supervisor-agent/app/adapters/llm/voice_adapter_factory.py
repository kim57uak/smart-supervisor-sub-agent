import structlog
from typing import Optional

from app.adapters.llm.voice_adapter_interface import VoiceAdapter
from app.adapters.llm.openai_realtime_adapter import OpenAiRealtimeAdapter
from app.core.config import settings

logger = structlog.get_logger(__name__)

class VoiceAdapterFactory:
    """
    설정에 따라 적절한 VoiceAdapter 구현체를 생성하는 팩토리 클래스.
    나중에 Gemini Live 등이 추가되면 이 팩토리에서 해당 어댑터를 생성하도록 확장합니다.
    """

    @staticmethod
    def create_adapter(provider: Optional[str] = None) -> VoiceAdapter:
        # Rationale (Why): 설정파일(settings) 기반으로 기본 공급자를 결정하되, 명시적 호출 시 오버라이드 가능.
        provider = (provider or settings.llm.provider).lower()
        
        logger.info("creating_voice_adapter", provider=provider)

        if provider == "openai":
            return OpenAiRealtimeAdapter()
        elif provider == "google":
            # Rationale (Why): Gemini Live 어댑터가 아직 구현되지 않았더라도 
            # 인터페이스가 동일하므로 나중에 이 분기만 활성화하면 됨.
            raise NotImplementedError("Gemini Live adapter is planned but not yet implemented.")
        else:
            # Fallback to OpenAI as default robust STT provider
            logger.warning("unsupported_voice_provider_falling_back_to_openai", provider=provider)
            return OpenAiRealtimeAdapter()
