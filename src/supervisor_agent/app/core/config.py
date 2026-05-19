import os
import yaml
import structlog
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, AliasGenerator, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger(__name__)

def to_dash(string: str) -> str:
    """Rationale (Why): Converts snake_case to dash-case for YAML compatibility."""
    return string.replace("_", "-")

from ..domain.enums import RedisNamespace, OrchestrationEngineType

# --- 코드성 데이터 상수화 (Constants & Enums) ---

class A2aMethod:
    MESSAGE_SEND = "message/send"
    SEND_MESSAGE = "SendMessage"
    MESSAGE_STREAM = "message/stream"
    SEND_STREAMING_MESSAGE = "SendStreamingMessage"
    TASKS_GET = "tasks/get"
    GET_TASK = "GetTask"
    TASKS_LIST = "tasks/list"
    LIST_TASKS = "ListTasks"
    TASKS_CANCEL = "tasks/cancel"
    CANCEL_TASK = "CancelTask"
    TASKS_EVENTS = "tasks/events"
    TASK_EVENTS = "TaskEvents"
    REVIEW_GET = "tasks/review/get"
    REVIEW_DECIDE = "tasks/review/decide"
    AGENT_CARD = "agent/card"
    SESSION_CLEAR = "session/clear"
    CLEAR_SESSION = "ClearSession"

class DefaultConfig:
    # App
    API_PREFIX = "/a2a/supervisor"
    
    # Method Allowlist
    ALLOWLIST = [
        A2aMethod.MESSAGE_SEND, A2aMethod.SEND_MESSAGE,
        A2aMethod.MESSAGE_STREAM, A2aMethod.SEND_STREAMING_MESSAGE,
        A2aMethod.TASKS_GET, A2aMethod.GET_TASK,
        A2aMethod.TASKS_LIST, A2aMethod.LIST_TASKS,
        A2aMethod.TASKS_CANCEL, A2aMethod.CANCEL_TASK,
        A2aMethod.TASKS_EVENTS, A2aMethod.TASK_EVENTS,
        A2aMethod.REVIEW_GET, A2aMethod.REVIEW_DECIDE,
        A2aMethod.AGENT_CARD, A2aMethod.SESSION_CLEAR, A2aMethod.CLEAR_SESSION
    ]
    
    # Routing Defaults
    ROUTING = {
        "product": "http://127.0.0.1:8082/a2a/product",
        "reservation": "http://127.0.0.1:8082/a2a/reservation",
        "supply-cost": "http://127.0.0.1:8082/a2a/supply-cost",
        "weather": "http://127.0.0.1:8082/a2a/weather"
    }
    
    # Defaults
    ENGINE = OrchestrationEngineType.LANGGRAPH
    TIMEOUT_MS = 120000
    REDIS_URL = "redis://localhost:6379/0"

# --- 하위 설정 모델 정의 (Type Safety) ---

class LlmProviderSettings(BaseModel):
    model: str = "gpt-4o-mini"
    temperature: float = 1.0

class LlmSettings(BaseModel):
    provider: str = "openai"
    voice_provider: str = "google"
    providers: Dict[str, LlmProviderSettings] = {
        "openai": LlmProviderSettings(model="gpt-4o-mini"),
        "google": LlmProviderSettings(model="gemini-1.5-flash"),
        "anthropic": LlmProviderSettings(model="claude-3-haiku-20240307")
    }

class RedisSettings(BaseModel):
    url: str = DefaultConfig.REDIS_URL
    prefix: str = RedisNamespace.GLOBAL_PREFIX.value
    ttl_seconds: int = 1800
    task_prefix: str = RedisNamespace.TASK.value
    queue_key: str = RedisNamespace.QUEUE.value

class RoutingAgentSettings(BaseModel):
    endpoint: str
    method: str = A2aMethod.MESSAGE_SEND
    timeout_ms: int = DefaultConfig.TIMEOUT_MS

class HitlSettings(BaseModel):
    model_config = ConfigDict(alias_generator=AliasGenerator(validation_alias=to_dash))
    reason_messages: Dict[str, str] = {}

class A2aSettings(BaseModel):
    model_config = ConfigDict(alias_generator=AliasGenerator(validation_alias=to_dash))
    
    method_allowlist: List[str] = DefaultConfig.ALLOWLIST
    routing: Dict[str, RoutingAgentSettings] = {
        k: RoutingAgentSettings(endpoint=v) for k, v in DefaultConfig.ROUTING.items()
    }
    max_concurrency: int = 2
    a2ui_enabled: bool = True
    max_handoff_hops: int = 3
    hitl: HitlSettings = HitlSettings()

# --- 메인 설정 클래스 ---

class Settings(BaseSettings):
    app_name: str = "supervisor-agent"
    debug: bool = False
    version: str = "1.0.0"
    embedded_worker_enabled: bool = True
    
    # API Configuration
    api_prefix: str = DefaultConfig.API_PREFIX
    orchestration_engine: OrchestrationEngineType = DefaultConfig.ENGINE
    allowed_hosts: List[str] = ["*"]
    
    # Redis Configuration
    redis_url: str = DefaultConfig.REDIS_URL
    
    # API Keys
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")
    
    # OpenAI Realtime Configuration (Centralized Management)
    openai_realtime_model: str = "gpt-4o-mini-realtime-preview"
    openai_realtime_url: str = "wss://api.openai.com/v1/realtime"
    openai_realtime_stt_model: str = "whisper-1"
    
    # Google Realtime Configuration
    google_realtime_model: str = "gemini-3.1-flash-live-preview"
    google_realtime_url: str = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
    
    # Nested Settings
    redis: RedisSettings = RedisSettings()
    llm: LlmSettings = LlmSettings()
    a2a: A2aSettings = A2aSettings()

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_prefix="SUPERVISOR_",
        env_nested_delimiter="__",
        extra="ignore"
    )

    _prompt_cache: Dict[str, Any] = {}
    _hitl_cache: Dict[str, Any] = {}

    @property
    def prompts(self) -> Dict[str, Any]:
        """Loads prompts from app/config/prompts.yml if not already cached."""
        if not self._prompt_cache:
            path = os.path.join(os.path.dirname(__file__), "..", "config", "prompts.yml")
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        self._prompt_cache = data.get("supervisor", {}).get("prompts", {})
                except Exception:
                    pass
        return self._prompt_cache

    @property
    def hitl_messages(self) -> Dict[str, Any]:
        """Loads HITL reason messages from app/config/hitl_messages.yml."""
        if not self._hitl_cache:
            path = os.path.join(os.path.dirname(__file__), "..", "config", "hitl_messages.yml")
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        self._hitl_cache = data.get("host", {}).get("a2a", {}).get("hitl", {}).get("reason-messages", {})
                except Exception:
                    pass
        return self._hitl_cache

    # Backward compatibility for existing code
    @property
    def orchestration_engine_setting(self) -> OrchestrationEngineType:
        return self.orchestration_engine

    @property
    def supervisor_config(self) -> Dict[str, Any]:
        return self.a2a.model_dump(by_alias=True)

    @property
    def llm_config(self) -> Dict[str, Any]:
        return self.llm.model_dump()

    @property
    def redis_prefix(self) -> str: return self.redis.prefix
    @property
    def redis_ttl_seconds(self) -> int: return self.redis.ttl_seconds

settings = Settings()
