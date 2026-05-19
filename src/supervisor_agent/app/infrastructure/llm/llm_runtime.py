from typing import Optional, Any
import os
import structlog
from ...core.config import settings

logger = structlog.get_logger(__name__)

class LlmRuntime:
    """
    Initializes and provides LangChain chat models.
    Uses centralized Pydantic settings for configuration.
    """
    _instance: Optional[Any] = None
    _current_provider: Optional[str] = None

    @classmethod
    def get_chat_model(cls) -> Any:
        llm_settings = settings.llm
        provider = llm_settings.provider.lower()
        
        # Singleton logic: Recreate if provider changed or instance doesn't exist
        if cls._instance is None or cls._current_provider != provider:
            cls._current_provider = provider
            provider_config = llm_settings.providers.get(provider)
            
            if not provider_config:
                logger.warning("provider_config_not_found", provider=provider)
                # Use default fallback or first available
                provider_config = list(llm_settings.providers.values())[0]

            temperature = provider_config.temperature
            model_name = provider_config.model
            
            logger.info("initializing_llm_model", provider=provider, model=model_name)

            if provider == "openai":
                from langchain_openai import ChatOpenAI
                cls._instance = ChatOpenAI(
                    model=model_name,
                    temperature=temperature,
                    api_key=settings.openai_api_key or os.getenv("OPENAI_API_KEY")
                )
            elif provider == "anthropic":
                from langchain_anthropic import ChatAnthropic
                cls._instance = ChatAnthropic(
                    model=model_name,
                    temperature=temperature,
                    api_key=os.getenv("ANTHROPIC_API_KEY")
                )
            elif provider in ["google", "gemma"]:
                from langchain_google_genai import ChatGoogleGenerativeAI
                cls._instance = ChatGoogleGenerativeAI(
                    model=model_name,
                    temperature=temperature,
                    google_api_key=settings.google_api_key or os.getenv("GOOGLE_API_KEY")
                )
            else:
                # Default fallback
                from langchain_openai import ChatOpenAI
                cls._instance = ChatOpenAI(
                    model="gpt-4o-mini",
                    temperature=0
                )
        return cls._instance
