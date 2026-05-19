"""
[Sub-Agent] 중앙 집중식 설정 관리
==================================
책임: 모든 환경 설정을 Pydantic Settings를 통해 단일 진입점으로 관리
아키텍처 위치: Core / Configuration Layer
원칙:
  - 모든 설정값은 DefaultConfig 상수로 정의 → Settings에서 참조
  - .env 파일 + 환경변수(SUBAGENT_ prefix)로 오버라이드 가능
  - typed nested settings로 타입 안전성 보장
  - prompts.yml 캐싱으로 파일 I/O 최소화

사용법:
  from app.core.config import settings
  settings.redis_url, settings.llm.provider, settings.prompts["system"]
"""

import os
import yaml
import structlog
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger(__name__)

from ..domain.enums import RedisNamespace, OrchestrationEngineType

# ============================================================
# DefaultConfig: 변경 빈도가 낮은 코드성 상수 집합
# ============================================================

class DefaultConfig:
    """시스템 전역 기본값. 환경변수로 오버라이드 전의 fallback 값."""
    MODEL = "gpt-4o-mini"
    REDIS_URL = "redis://localhost:6379/0"
    
    REDIS_PREFIXES = {
        "task": "subagent:task",
        "idempotency": "subagent:idempotency",
        "events": "subagent:events",
        "conversation": "subagent:conv",
        "checkpoint": "subagent:ckpt"
    }
    
    A2A_SCOPES = ["chat", "weather", "supply-cost", "reservation", "sale-product"]
    A2A_BASE_URL = "http://localhost:8082"
    
    MCP_HOST = "http://10.225.18.50:8080"
    MCP_SERVERS = {
        "weather": ["getWeatherForecastByLocation", "getAlerts"],
        "supply-cost": ["getSupplyCostInfo"],
        "reservation": ["createReservation"],
        "sale-product": ["createAutoCopySaleProducts", "getSaleProductDetails"]
    }
    
    ENGINE = OrchestrationEngineType.LANGGRAPH

# ============================================================
# 세부 설정 모델 (타입 안전성 + 자동 완성)
# ============================================================

class LlmProviderSettings(BaseModel):
    """개별 LLM 제공자(OpenAI/Google 등)의 모델 및 temperature"""
    model: str
    temperature: float = 0.0

class LlmSettings(BaseModel):
    """LLM 설정: 활성 제공자 선택 + 제공자별 상세 설정"""
    provider: str = "openai"
    providers: Dict[str, LlmProviderSettings] = {
        "google": LlmProviderSettings(model="gemini-1.5-flash"),
        "openai": LlmProviderSettings(model=DefaultConfig.MODEL)
    }

class RedisPrefixSettings(BaseModel):
    """Redis 키 Prefix — 충돌 방지를 위한 네임스페이스"""
    global_prefix: str = RedisNamespace.GLOBAL_PREFIX.value
    task: str = DefaultConfig.REDIS_PREFIXES["task"]
    idempotency: str = DefaultConfig.REDIS_PREFIXES["idempotency"]
    events: str = DefaultConfig.REDIS_PREFIXES["events"]
    conversation: str = DefaultConfig.REDIS_PREFIXES["conversation"]
    checkpoint: str = DefaultConfig.REDIS_PREFIXES["checkpoint"]

class GraphSettings(BaseModel):
    """LangGraph/Burr 그래프 실행 설정"""
    max_tool_iterations: int = 4
    checkpoint_enabled: bool = True
    graph_id: str = "default_graph"

class AgentRuntimeSettings(BaseModel):
    """에이전트 실행 시 timeout/token 제한"""
    request_timeout: str = "20s"
    provider_timeout: str = "12s"
    tool_timeout: str = "8s"
    max_tool_calls_per_request: int = 6
    max_prompt_tokens: int = 8192
    max_completion_tokens: int = 2048

class TraceSettings(BaseModel):
    """분산 추적(trace_id 전파) 설정"""
    enabled: bool = True
    propagate_fields: List[str] = ["trace_id", "request_id", "session_id"]
    use_supervisor_values_first: bool = True

class AgentSettings(BaseModel):
    """에이전트 종합 설정 — Graph + Runtime + Trace + Redis"""
    graph: GraphSettings = GraphSettings()
    runtime: AgentRuntimeSettings = AgentRuntimeSettings()
    trace: TraceSettings = TraceSettings()
    redis_ttl: int = 1800
    redis_prefixes: RedisPrefixSettings = RedisPrefixSettings()
    default_model: str = DefaultConfig.MODEL

class McpServerSettings(BaseModel):
    """MCP 서버 연결 설정 — host/protocol/timeout/tools"""
    host: str = DefaultConfig.MCP_HOST
    protocol: str = "streamable"
    endpoint: str = "/mcp"
    reuse_session: bool = True
    cache_tools: bool = True
    allow_legacy_sse_fallback: bool = True
    tools: List[str] = []

class A2aSettings(BaseModel):
    """A2A 프로토콜 설정 — discovery/scope/endpoint"""
    enabled: bool = True
    public_base_url: str = DefaultConfig.A2A_BASE_URL
    scopes: List[str] = DefaultConfig.A2A_SCOPES

# ============================================================
# Settings: 최상위 설정 클래스 (전역 싱글톤)
# ============================================================

class Settings(BaseSettings):
    """
    Pydantic BaseSettings 기반 설정.
    환경변수 우선순위: SUBAGENT_OPENAI_API_KEY > OPENAI_API_KEY (alias) > .env > 기본값
    env_nested_delimiter="__" 예: SUBAGENT_LLM__PROVIDER="google"
    """
    app_name: str = "mcp-sub-agent"
    debug: bool = False
    version: str = "1.0.0"
    
    api_prefix: str = "/api/v1"
    orchestration_engine: OrchestrationEngineType = DefaultConfig.ENGINE
    
    redis_url: str = DefaultConfig.REDIS_URL
    
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")
    
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
        """prompts.yml을 lazy-loading + 캐싱하여 반환"""
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

# 전역 싱글톤 인스턴스
settings = Settings()
