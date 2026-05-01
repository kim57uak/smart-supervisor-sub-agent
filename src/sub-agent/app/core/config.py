import os
import yaml
import structlog
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger(__name__)

from ..domain.enums import RedisNamespace, OrchestrationEngineType

# --- 코드성 데이터 상수화 (Constants) ---

class DefaultConfig:
    # LLM & Redis
    MODEL = "gpt-4o-mini"
    REDIS_URL = "redis://localhost:6379/0"
    
    # Redis Prefixes
    REDIS_PREFIXES = {
        "task": "subagent:task",
        "idempotency": "subagent:idempotency",
        "events": "subagent:events",
        "conversation": "subagent:conv",
        "checkpoint": "subagent:ckpt"
    }
    
    # A2A Scopes
    A2A_SCOPES = ["chat", "weather", "supply-cost", "reservation", "sale-product"]
    A2A_BASE_URL = "http://localhost:8082"
    
    # MCP Configuration
    MCP_HOST = "http://10.225.18.50:8080"
    MCP_SERVERS = {
        "weather": ["getWeatherForecastByLocation", "getAlerts"],
        "supply-cost": ["getSupplyCostInfo"],
        "reservation": ["createReservation"],
        "sale-product": ["createAutoCopySaleProducts", "getSaleProductDetails"]
    }
    
    # Engine Default
    ENGINE = OrchestrationEngineType.LANGGRAPH

# --- 하위 설정 모델 정의 (Type Safety) ---

class LlmProviderSettings(BaseModel):
    model: str
    temperature: float = 0.0

class LlmSettings(BaseModel):
    provider: str = "openai"
    providers: Dict[str, LlmProviderSettings] = {
        "google": LlmProviderSettings(model="gemini-1.5-flash"),
        "openai": LlmProviderSettings(model=DefaultConfig.MODEL)
    }

class RedisPrefixSettings(BaseModel):
    global_prefix: str = RedisNamespace.GLOBAL_PREFIX.value
    task: str = DefaultConfig.REDIS_PREFIXES["task"]
    idempotency: str = DefaultConfig.REDIS_PREFIXES["idempotency"]
    events: str = DefaultConfig.REDIS_PREFIXES["events"]
    conversation: str = DefaultConfig.REDIS_PREFIXES["conversation"]
    checkpoint: str = DefaultConfig.REDIS_PREFIXES["checkpoint"]

class GraphSettings(BaseModel):
    max_tool_iterations: int = 4
    checkpoint_enabled: bool = True
    graph_id: str = "default_graph"

class AgentRuntimeSettings(BaseModel):
    request_timeout: str = "20s"
    provider_timeout: str = "12s"
    tool_timeout: str = "8s"
    max_tool_calls_per_request: int = 6
    max_prompt_tokens: int = 8192
    max_completion_tokens: int = 2048

class TraceSettings(BaseModel):
    enabled: bool = True
    propagate_fields: List[str] = ["trace_id", "request_id", "session_id"]
    use_supervisor_values_first: bool = True

class AgentSettings(BaseModel):
    graph: GraphSettings = GraphSettings()
    runtime: AgentRuntimeSettings = AgentRuntimeSettings()
    trace: TraceSettings = TraceSettings()
    redis_ttl: int = 1800
    redis_prefixes: RedisPrefixSettings = RedisPrefixSettings()
    default_model: str = DefaultConfig.MODEL

class McpServerSettings(BaseModel):
    host: str = DefaultConfig.MCP_HOST
    protocol: str = "streamable"
    endpoint: str = "/mcp"
    reuse_session: bool = True
    cache_tools: bool = True
    allow_legacy_sse_fallback: bool = True
    tools: List[str] = []

class A2aSettings(BaseModel):
    enabled: bool = True
    public_base_url: str = DefaultConfig.A2A_BASE_URL
    scopes: List[str] = DefaultConfig.A2A_SCOPES

# --- 메인 설정 클래스 ---

class Settings(BaseSettings):
    app_name: str = "mcp-sub-agent"
    debug: bool = False
    version: str = "1.0.0"
    
    # API Configuration
    api_prefix: str = "/api/v1"
    orchestration_engine: OrchestrationEngineType = DefaultConfig.ENGINE
    
    # Redis Configuration
    redis_url: str = DefaultConfig.REDIS_URL
    
    # API Keys
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")
    
    # Nested Settings
    llm: LlmSettings = LlmSettings()
    agent: AgentSettings = AgentSettings()
    a2a: A2aSettings = A2aSettings()
    mcp_servers: Dict[str, McpServerSettings] = {
        k: McpServerSettings(tools=v) for k, v in DefaultConfig.MCP_SERVERS.items()
    }
    
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_prefix="SUBAGENT_",
        env_nested_delimiter="__",
        extra="ignore"
    )

    _prompt_cache: Dict[str, Any] = {}

    @property
    def prompts(self) -> Dict[str, Any]:
        """Loads prompts from app/config/prompts.yml if not already cached."""
        if not self._prompt_cache:
            path = os.path.join(os.path.dirname(__file__), "..", "config", "prompts.yml")
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        self._prompt_cache = data.get("prompts", {})
                except Exception:
                    pass
        return self._prompt_cache

settings = Settings()
