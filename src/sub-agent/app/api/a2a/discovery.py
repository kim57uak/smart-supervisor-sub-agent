from fastapi import APIRouter
from ...schemas.a2a import AgentCard, AgentSkill, AgentEndpoints
from ...core.config import settings

router = APIRouter()

@router.get("/agent-card.json")
async def get_agent_cards():
    """
    Returns the list of agent cards hosted by this server.
    Implements Document 22 (Canonical discovery path).
    """
    # Rationale (Why): Updated descriptions and skills to include specific terms like '판매상품코드' and '검색' 
    # to improve LLM routing accuracy when users search for product codes.
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
