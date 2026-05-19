import httpx
import structlog
from typing import List, Dict, Any, TYPE_CHECKING
from ...core.config import settings

if TYPE_CHECKING:
    from .mcp_infrastructure import McpTransportFactory

logger = structlog.get_logger(__name__)

# ──────────────────────────────────────────────
# MCP 도구 레지스트리
# ──────────────────────────────────────────────
# 설정된 모든 MCP 서버에서 도구 목록을 실시간으로 탐색(discovery)하고 캐싱한다.
# 탐색 순서: initialize → notifications/initialized → tools/list
# 탐색된 도구 정보는 Planner(LLM)가 도구 선택 시 사용할 스키마로 제공된다.
# 하나투어 도메인: 상품/예약/고객/결제 서버의 MCP 도구를 등록한다.
class McpToolRegistry:
    def __init__(self, transport_factory: "McpTransportFactory"):
        self.factory = transport_factory
        self._tools = []          # [(name, server_id, inputSchema, description), ...]

    # 전체 MCP 서버 대상 100% 실시간 도구 탐색
    # 각 서버별로: ① initialize 핸드셰이크 → ② initialized 알림 → ③ tools/list 호출
    # 실패 시 해당 서버는 건너뛰고 다음 서버로 진행한다.
    async def refresh_tools(self) -> List[Dict[str, Any]]:
        all_discovered_tools = []
        
        for server_name, config in settings.mcp_servers.items():
            logger.info("mcp_discovery_start", server=server_name, url=config.host)
            
            try:
                # ① 전송 계층 생성 (팩토리에서 생성, 세션 관리 안 함)
                transport = self.factory.create_transport(server_name)
                
                # ② 핸드셰이크: initialize (프로토콜 협상, 세션 ID 획득)
                init_result = await transport.call("initialize", {})
                
                if "error" in init_result:
                    logger.error("mcp_init_failed", server=server_name, error=init_result["error"])
                    continue

                # ③ initialized 알림 전송
                await transport.notify("notifications/initialized", {})

                # ④ 도구 목록 조회: tools/list
                tools_result = await transport.call("tools/list", {})
                
                if "result" in tools_result and "tools" in tools_result["result"]:
                    discovered = tools_result["result"]["tools"]
                    logger.info("mcp_discovery_success", server=server_name, count=len(discovered))
                    
                    for tool in discovered:
                        tool_name = tool.get("name")
                        tool["server_id"] = server_name          # 라우팅용 서버 식별자 주입
                        all_discovered_tools.append(tool)
                        logger.info("mcp_tool_registered", server=server_name, tool=tool_name)
                else:
                    logger.warn("mcp_no_tools_found", server=server_name, result=tools_result)

            except Exception as e:
                logger.error("mcp_discovery_exception", server=server_name, error=str(e))
        
        self._tools = all_discovered_tools
        return self._tools

    # 탐색된 전체 도구 스키마 반환
    # LLM Planner가 사용 가능한 도구를 인지하고 선택하는 데 사용된다.
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return self._tools

    # 도구명으로 호스팅 서버 조회
    # execute_tools 단계에서 올바른 MCP 서버로 라우팅하기 위해 사용된다.
    def get_tool_server(self, tool_name: str) -> str:
        for tool in self._tools:
            if tool.get("name") == tool_name:
                return tool.get("server_id", "unknown")
        return "unknown"

    # 도구명(및 서버명)으로 메타데이터 조회
    # Schema Guard(mcp_adapters.py)가 입력 검증 시 사용한다.
    def get_tool_schema(self, tool_name: str, server_name: str | None = None) -> Dict[str, Any]:
        for tool in self._tools:
            if tool.get("name") != tool_name:
                continue
            if server_name and tool.get("server_id") != server_name:
                continue
            return tool
        return {}
