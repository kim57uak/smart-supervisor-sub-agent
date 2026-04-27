"""
End-to-end 테스트: 플래너 → A2A 실제 통신 → downstream 응답 수신
"""
import asyncio
import sys
import json
sys.path.insert(0, '.')

from app.core.config import settings
from app.adapters.llm.llm_planning_service import LlmSupervisorPlanningService
from app.adapters.integration.default_a2a_invocation import DefaultA2AInvocationService

async def test_full_flow():
    # 1. 플래닝
    planner = LlmSupervisorPlanningService()
    await planner.load_agent_cards()
    
    test_input = "AAX20126042600P 판매상품 정보 조회해줘"
    print(f"[입력] {test_input}")
    print(f"{'='*60}")
    
    review_required, plan_data = await planner.plan(
        user_input=test_input,
        context={"session_id": "test-session"}
    )
    
    routing_queue = plan_data.get("routing_queue", [])
    is_direct = plan_data.get("planner_metadata", {}).get("direct_answer", False)
    
    print(f"\n[1단계 플래닝 결과]")
    print(f"  direct_answer: {is_direct}")
    print(f"  routing_queue: {len(routing_queue)}개")
    
    if is_direct or not routing_queue:
        print("  → Direct Answer 모드 (downstream 호출 없음)")
        return
    
    # 2. A2A 실제 통신
    invoker = DefaultA2AInvocationService()
    
    for step in routing_queue:
        agent_key = step["agent_key"]
        method = step["method"]
        arguments = step["arguments"]
        
        print(f"\n[2단계 A2A 호출] agent={agent_key}, method={method}")
        print(f"  arguments: {arguments}")
        
        result = await invoker.invoke(agent_key, method, arguments)
        
        print(f"\n[3단계 응답 수신]")
        print(f"  status: {result.get('status', 'N/A')}")
        answer = result.get("payload", {}).get("answer", "")
        print(f"  answer: {answer[:500]}...")

asyncio.run(test_full_flow())
