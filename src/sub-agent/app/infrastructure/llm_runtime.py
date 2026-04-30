import os
from typing import Optional, Any
from ..core.config import settings

class LlmRuntime:
    """
    Independent LLM Runtime for Sub-agent.
    Uses centralized Pydantic settings.
    """
    _instance: Optional[Any] = None
    
    @classmethod
    def get_chat_model(cls) -> Any:
        llm_config = settings.llm
        provider = llm_config.provider.lower()
        
        if cls._instance is None or getattr(cls, "_current_provider", None) != provider:
            cls._current_provider = provider
            provider_config = llm_config.providers.get(provider)
            
            if not provider_config:
                # Fallback to first available or a default
                provider_config = list(llm_config.providers.values())[0]

            temperature = provider_config.temperature
            model_name = provider_config.model
            
            if provider == "google":
                from langchain_google_genai import ChatGoogleGenerativeAI
                cls._instance = ChatGoogleGenerativeAI(
                    model=model_name,
                    temperature=temperature,
                    google_api_key=os.getenv("GOOGLE_API_KEY")
                )
            elif provider == "openai":
                from langchain_openai import ChatOpenAI
                cls._instance = ChatOpenAI(
                    model=model_name,
                    temperature=temperature,
                    api_key=os.getenv("OPENAI_API_KEY")
                )
            else:
                from langchain_openai import ChatOpenAI
                cls._instance = ChatOpenAI(model="gpt-4o-mini", temperature=0)
                
        return cls._instance
