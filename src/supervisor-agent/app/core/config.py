import os
from typing import List, Optional, Dict, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class Settings(BaseSettings):
    app_name: str = "supervisor-agent"
    debug: bool = False
    version: str = "1.0.0"

    # API Configuration
    api_prefix: str = "/a2a/supervisor"
    allowed_hosts: List[str] = ["*"]

    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"
    redis_ttl_seconds: int = 1800  # 30 minutes as per doc 20

    # LLM Configuration
    llm_provider: str = "openai"  # or "gemini", etc.
    llm_model_name: str = "gpt-5-mini"

    # Security
    openai_api_key: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Lazy-loaded YAML Configs
    _yaml_config: Dict[str, Any] = {}

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        if filename in self._yaml_config:
            return self._yaml_config[filename]
        
        filepath = os.path.join(os.path.dirname(__file__), "..", "config", filename)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                self._yaml_config[filename] = data
                return data
        return {}

    @property
    def prompts(self) -> Dict[str, Any]:
        data = self._load_yaml("prompts.yml")
        return data.get("supervisor", {}).get("prompts", {})

    @property
    def supervisor_config(self) -> Dict[str, Any]:
        data = self._load_yaml("supervisor.yml")
        return data.get("host", {}).get("a2a", {})

    @property
    def hitl_messages(self) -> Dict[str, Any]:
        data = self._load_yaml("hitl_messages.yml")
        return data.get("host", {}).get("a2a", {}).get("hitl", {}).get("reason-messages", {})

    @property
    def llm_config(self) -> Dict[str, Any]:
        data = self._load_yaml("llm.yml")
        return data.get("llm", {})

settings = Settings()
