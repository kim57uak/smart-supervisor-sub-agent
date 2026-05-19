"""
[Sub-Agent] A2A Discovery 엔드포인트 — Agent Card 조회
=======================================================
책임: /.well-known/agent-card.json 경로로 서브에이전트의 Agent Card 제공
아키텍처 위치: API Layer — A2A Protocol (Discovery)

A2A 표준: 슈퍼바이저 에이전트가 서브에이전트를 검색할 때 사용
  - 각 AgentCard는 name + description + capabilities + skills + endpoints 포함
  - LLM 라우팅 정확도를 향상시키기 위해 description에 구체적인 용어 사용
  - '판매상품코드' 같은 특정 도메인 용어를 포함하여 검색 정확도 개선

엔드포인트:
  GET /.well-known/agent-card.json
"""

from fastapi import APIRouter
from ...schemas.a2a import AgentCard, AgentSkill, AgentEndpoints
from ...core.config import settings

router = APIRouter()

@router.get("/agent-card.json")
async def get_agent_cards():
    """
    서브에이전트가 제공하는 모든 Agent Card 목록 반환.
    각 카드는 name/description/capabilities/skills/endpoints 포함.
    """
    cards = [
        AgentCard(
            name="product",
            description="판매 상품 및 판매상품코드 정보 조회, 검색 및 관리 에이전트",
            capabilities=["product_info", "inventory_check", "product_search"],
            skills=[
                AgentSkill(name="getSaleProductDetails", description="판매상품코드 또는 상품명을 기반으로 판매 상품의 상세 정보를 조회 및 검색합니다."),
                AgentSkill(name="createAutoCopySaleProducts", description="상품 정보를 기반으로 자동 복사 상품을 생성합니다.")
            ],
            endpoints=AgentEndpoints(message=f"/a2a/product")
        ),
        AgentCard(
            name="reservation",
            description="신규 예약 생성 및 관리 에이전트",
            capabilities=["reservation_creation", "booking_status"],
            skills=[
                AgentSkill(name="createReservation", description="사용자 요청에 따라 신규 예약을 생성합니다.")
            ],
            endpoints=AgentEndpoints(message=f"/a2a/reservation")
        ),
        AgentCard(
            name="supply-cost",
            description="상품 공급가 분석 및 조회 에이전트",
            capabilities=["cost_analysis", "pricing_lookup"],
            skills=[
                AgentSkill(name="getSupplyCostInfo", description="상품의 공급가 및 원가 정보를 조회합니다.")
            ],
            endpoints=AgentEndpoints(message=f"/a2a/supply-cost")
        ),
        AgentCard(
            name="weather",
            description="전 세계 날씨 예보 및 기상 알림 조회 에이전트",
            capabilities=["weather_forecast", "weather_alerts"],
            skills=[
                AgentSkill(name="getWeatherForecastByLocation", description="특정 지역의 날씨 예보를 조회합니다."),
                AgentSkill(name="getAlerts", description="기상 특보 및 알림 정보를 조회합니다.")
            ],
            endpoints=AgentEndpoints(message=f"/a2a/weather")
        )
    ]
    return [card.model_dump() for card in cards]
