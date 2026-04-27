from typing import Optional, Any
from ...core.config import settings
import os

class LlmRuntime:
    """
    Initializes and provides LangChain chat models based on llm.yml settings.
    """
    _instance: Optional[Any] = None

    @classmethod
    def get_chat_model(cls) -> Any:
        llm_config = settings.llm_config
        provider = llm_config.get("provider", "openai").lower()
        
        # Singleton logic: Recreate if provider changed or instance doesn't exist
        if cls._instance is None or getattr(cls, "_current_provider", None) != provider:
            cls._current_provider = provider
            providers_config = llm_config.get("providers", {})
            provider_config = providers_config.get(provider, {})
            temperature = provider_config.get("temperature", 0.0)
            
            if provider == "openai":
                from langchain_openai import ChatOpenAI
                model = provider_config.get("model", "gpt-5.4-mini")
                cls._instance = ChatOpenAI(
                    model=model,
                    temperature=temperature,
                    api_key=settings.openai_api_key or os.getenv("OPENAI_API_KEY")
                )
            elif provider == "anthropic":
                from langchain_anthropic import ChatAnthropic
                model = provider_config.get("model", "claude-3-haiku-20240307")
                cls._instance = ChatAnthropic(
                    model=model,
                    temperature=temperature,
                    api_key=os.getenv("ANTHROPIC_API_KEY")
                )
            elif provider in ["google", "gemma"]:
                from langchain_google_genai import ChatGoogleGenerativeAI
                model = provider_config.get("model")
                if not model:
                    model = "gemini-3-flash" if provider == "google" else "gemma-4-9b-it"
                    
                cls._instance = ChatGoogleGenerativeAI(
                    model=model,
                    temperature=temperature,
                    google_api_key=os.getenv("GOOGLE_API_KEY")
                )
            elif provider == "groq":
                from langchain_groq import ChatGroq
                model = provider_config.get("model", "gemma-4-9b-it")
                cls._instance = ChatGroq(
                    model=model,
                    temperature=temperature,
                    groq_api_key=os.getenv("GROQ_API_KEY")
                )
            else:
                # Default fallback
                from langchain_openai import ChatOpenAI
                cls._instance = ChatOpenAI(
                    model="gpt-4o-mini",
                    temperature=0,
                    api_key=settings.openai_api_key or os.getenv("OPENAI_API_KEY")
                )
        return cls._instance

