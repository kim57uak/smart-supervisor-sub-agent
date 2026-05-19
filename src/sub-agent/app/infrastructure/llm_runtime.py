"""
[Sub-Agent] LLM 런타임 — 제공자별 ChatModel 싱글톤
====================================================
책임: 설정에 따라 OpenAI/Google(LangChain ChatModel) 인스턴스를 생성/캐싱
아키텍처 위치: Infrastructure Layer — LLM Integration

제공자 전환:
  - settings.llm.provider가 변경되면 새 인스턴스 생성
  - 제공자별 API 키는 .env → os.getenv()로 조회
  - OpenAI 기본 모델: gpt-4o-mini (temperature=0)

주의:
  - 싱글톤 _instance는 프로세스 레벨 공유
  - ASGI 멀티워커에서는 각 워커가 독립적 인스턴스 가짐
  - LangChain ChatModel은 thread-safe하지만 lazy init의 race condition 주의
"""

import os
from typing import Optional, Any
from ..core.config import settings

class LlmRuntime:
    """
    LLM 제공자별 ChatModel 싱글톤 런타임.
    provider가 변경되면 기존 인스턴스 폐기 후 새로 생성.
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
