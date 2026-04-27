"""
사용자 요청 직접 테스트: AAX20126042600P 판매상품 정보 검색해죠
"""
import asyncio
import sys
import json
sys.path.insert(0, '.')

from app.core.config import settings
from app.adapters.llm.llm_planning_service import LlmSupervisorPlanningService
from app.adapters.integration.default_a2a_invocation import DefaultA2AInvocationService

async def test_user_request():
    # 1. 초기화 및 카드 로딩
    planner = LlmSupervisorPlanningService()
    await planner.load_agent_cards()
    
    test_input = "AAX20126042600P 판매상품 정보 검색해죠"
    print(f"\n[1] 사용자 입력: {test_input}")
    print(f"{'='*60}")
    
    # 2. 플래닝 실행
    print("[2] 플래닝 실행 중...")
    review_required, plan_data = await planner.plan(
        user_input=test_input,
        context={"session_id": "real-test-session"}
    )
    
    routing_queue = plan_data.get("routing_queue", [])
    is_direct = plan_data.get("planner_metadata", {}).get("direct_answer", False)
    
    print(f"\n[플래닝 결과]")
    print(f"  - Direct Answer 여부: {is_direct}")
    print(f"  - 라우팅 큐 크기: {len(routing_queue)}개")
    
    if is_direct or not routing_queue:
        print("  → LLM이 직접 응답하기로 결정했습니다.")
        return

    # 3. A2A 실제 호출
    invoker = DefaultA2AInvocationService()
    
    for step in routing_queue:
        agent_key = step["agent_key"]
        method = step["method"]
        arguments = step["arguments"]
        
        print(f"\n[3] A2A 호출 실행: {agent_key} ({method})")
        print(f"  - 인자: {arguments}")
        
        # 실제 HTTP 호출
        result = await invoker.invoke(agent_key, method, arguments)
        
        print(f"\n[4] 하위 에이전트({agent_key}) 응답 수신")
        print(f"  - 상태: {result.get('status')}")
        answer = result.get("payload", {}).get("answer", "")
        print("-" * 40)
        print(answer)
        print("-" * 40)

if __name__ == "__main__":
    asyncio.run(test_user_request())
