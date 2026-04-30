import os
import yaml
import structlog
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger(__name__)

class LlmProviderSettings(BaseModel):
    model: str
    temperature: float = 0.0

class LlmSettings(BaseModel):
    provider: str = "openai"
    providers: Dict[str, LlmProviderSettings] = {
        "google": LlmProviderSettings(model="gemini-1.5-flash"),
        "openai": LlmProviderSettings(model="gpt-4o-mini")
    }

from ..domain.enums import RedisNamespace

class RedisPrefixSettings(BaseModel):
    global_prefix: str = RedisNamespace.GLOBAL_PREFIX.value
    task: str = "subagent:task"
    idempotency: str = "subagent:idempotency"
    events: str = "subagent:events"
    conversation: str = "subagent:conv"
    checkpoint: str = "subagent:ckpt"

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

class ScopeSettings(BaseModel):
    allowed_servers: List[str]
    allowed_tools_by_server: Dict[str, List[str]]
    default_model: str = "gemini-1.5-flash"

class AgentSettings(BaseModel):
    graph: GraphSettings = GraphSettings()
    runtime: AgentRuntimeSettings = AgentRuntimeSettings()
    trace: TraceSettings = TraceSettings()
    redis_ttl: int = 1800
    redis_prefixes: RedisPrefixSettings = RedisPrefixSettings()
    default_model: str = "gemini-1.5-flash"
    scopes: Dict[str, ScopeSettings] = {}

class McpServerSettings(BaseModel):
    host: str
    protocol: str = "streamable"
    endpoint: str = "/mcp"
    reuse_session: bool = True
    cache_tools: bool = True
    allow_legacy_sse_fallback: bool = True
    tools: List[str] = []

class A2aSettings(BaseModel):
    enabled: bool = True
    public_base_url: str = "http://localhost:8082"
    scopes: List[str] = ["chat", "weather", "supply-cost", "reservation", "sale-product"]

class Settings(BaseSettings):
    app_name: str = "mcp-sub-agent"
    debug: bool = False
    version: str = "1.0.0"
    
    # API Configuration
    api_prefix: str = "/api/v1"
    
    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"
    
    # API Keys
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")
    
    # Nested Settings (Document 21)
    llm: LlmSettings = LlmSettings()
    agent: AgentSettings = AgentSettings()
    a2a: A2aSettings = A2aSettings()
    mcp_servers: Dict[str, McpServerSettings] = {
        "weather": McpServerSettings(
            host="http://10.225.18.50:8080",
            tools=["getWeatherForecastByLocation", "getAlerts"]
        ),
        "supply-cost": McpServerSettings(
            host="http://10.225.18.50:8080",
            tools=["getSupplyCostInfo"]
        ),
        "reservation": McpServerSettings(
            host="http://10.225.18.50:8080",
            tools=["createReservation"]
        ),
        "sale-product": McpServerSettings(
            host="http://10.225.18.50:8080",
            tools=["createAutoCopySaleProducts", "getSaleProductDetails"]
        )
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
                        logger.info("prompts_loaded_from_yaml", path=path)
                except Exception as e:
                    logger.error("failed_to_load_prompts", path=path, error=str(e))
        return self._prompt_cache

settings = Settings()
