import os
import yaml
import structlog
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger(__name__)

# --- 하위 설정 모델 정의 (Type Safety) ---

from ..domain.enums import RedisNamespace

class LlmProviderSettings(BaseModel):
    model: str = "gpt-4o-mini"
    temperature: float = 1.0

class LlmSettings(BaseModel):
    provider: str = "openai"
    providers: Dict[str, LlmProviderSettings] = {
        "openai": LlmProviderSettings(model="gpt-4o-mini"),
        "google": LlmProviderSettings(model="gemini-1.5-flash"),
        "anthropic": LlmProviderSettings(model="claude-3-haiku-20240307")
    }

class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379/0"
    prefix: str = RedisNamespace.GLOBAL_PREFIX.value
    ttl_seconds: int = 1800
    task_prefix: str = RedisNamespace.TASK.value
    queue_key: str = RedisNamespace.QUEUE.value

class RoutingAgentSettings(BaseModel):
    endpoint: str
    method: str = "message/send"
    timeout_ms: int = 120000

class A2aSettings(BaseModel):
    method_allowlist: List[str] = [
        "message/send", "SendMessage", "message/stream", "SendStreamingMessage",
        "tasks/get", "GetTask", "tasks/list", "ListTasks", "tasks/cancel", "CancelTask"
    ]
    routing: Dict[str, RoutingAgentSettings] = {
        "product": RoutingAgentSettings(endpoint="http://localhost:8082/a2a/product"),
        "reservation": RoutingAgentSettings(endpoint="http://localhost:8082/a2a/reservation")
    }
    max_concurrency: int = 2
    a2ui_enabled: bool = True
    max_handoff_hops: int = 3

# --- 메인 설정 클래스 ---

class Settings(BaseSettings):
    app_name: str = "supervisor-agent"
    debug: bool = False
    version: str = "1.0.0"
    embedded_worker_enabled: bool = True
    
    api_prefix: str = "/a2a/supervisor"
    allowed_hosts: List[str] = ["*"]
    
    # 계층형 설정 주입
    redis: RedisSettings = RedisSettings()
    llm: LlmSettings = LlmSettings()
    a2a: A2aSettings = A2aSettings()
    
    # 보안 (환경 변수 우선)
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_prefix="SUPERVISOR_",
        env_nested_delimiter="__",
        extra="ignore"
    )

    _yaml_cache: Dict[str, Any] = {}

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        if filename in self._yaml_cache:
            return self._yaml_cache[filename]
        
        filepath = os.path.join(os.path.dirname(__file__), "..", "config", filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    self._yaml_cache[filename] = data or {}
                    return self._yaml_cache[filename]
            except Exception as e:
                logger.error("failed_to_load_yaml", filename=filename, error=str(e))
        return {}

    @property
    def prompts(self) -> Dict[str, Any]:
        data = self._load_yaml("prompts.yml")
        return data.get("supervisor", {}).get("prompts", {})

    @property
    def hitl_messages(self) -> Dict[str, Any]:
        data = self._load_yaml("hitl_messages.yml")
        return data.get("host", {}).get("a2a", {}).get("hitl", {}).get("reason-messages", {})

    @property
    def supervisor_config(self) -> Dict[str, Any]:
        data = self._load_yaml("supervisor.yml")
        # Rationale (Why): supervisor.yml is the source of truth for A2A routing and policies.
        # We merge the YAML content with the Pydantic model defaults.
        yaml_config = data.get("host", {}).get("a2a", {})
        if not yaml_config:
            return self.a2a.model_dump()
            
        # Merge logic: YAML takes precedence over code defaults
        base = self.a2a.model_dump()
        base.update(yaml_config)
        return base

    @property
    def llm_config(self) -> Dict[str, Any]:
        return self.llm.model_dump()

    @property
    def redis_url(self) -> str: return self.redis.url
    @property
    def redis_prefix(self) -> str: return self.redis.prefix
    @property
    def redis_ttl_seconds(self) -> int: return self.redis.ttl_seconds

settings = Settings()
