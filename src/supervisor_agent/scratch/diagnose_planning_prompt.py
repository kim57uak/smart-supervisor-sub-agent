"""
진단 스크립트: planning prompt에 모든 정보가 매핑되는지 검증
"""
import asyncio
import sys
sys.path.insert(0, '.')

from app.core.config import settings
from app.adapters.llm.llm_planning_service import LlmSupervisorPlanningService

async def diagnose():
    svc = LlmSupervisorPlanningService()
    
    # 1. 에이전트 카드 로딩
    print("=" * 60)
    print("[1] 에이전트 카드 로딩 (GET /.well-known/agent.json)")
    print("=" * 60)
    await svc.load_agent_cards()
    print(f"  캐시된 카드 수: {len(svc._agent_card_cache)}")
    for name, card in svc._agent_card_cache.items():
        print(f"  - {name}: {card.get('description', 'N/A')}")
        skills = card.get('skills', [])
        for s in skills:
            print(f"    스킬: {s.get('name', '')} → {s.get('description', '')}")
    
    # 2. routing config 확인
    print("\n" + "=" * 60)
    print("[2] supervisor.yml routing 설정")
    print("=" * 60)
    routing_config = settings.supervisor_config.get("routing", {})
    allowed_agents_list = list(routing_config.keys())
    print(f"  허용 에이전트: {allowed_agents_list}")
    
    # 3. 에이전트 카드 매칭 검증
    print("\n" + "=" * 60)
    print("[3] routing key ↔ 카드 캐시 매칭")
    print("=" * 60)
    for agent_key in allowed_agents_list:
        card = next(
            (v for k, v in svc._agent_card_cache.items() if agent_key.lower() in k.lower()),
            None
        )
        if card:
            print(f"  ✅ {agent_key} → 매칭: {card.get('name')}")
        else:
            print(f"  ❌ {agent_key} → 매칭 실패! (fallback 사용됨)")
    
    # 4. 실제 프롬프트 포맷팅 시뮬레이션
    print("\n" + "=" * 60)
    print("[4] 실제 LLM에 전달될 프롬프트 (포맷팅 결과)")
    print("=" * 60)
    
    system_prompt = settings.prompts["planning-system"]
    planning_template = settings.prompts["planning-template"]
    
    agent_cards_str = svc._build_agent_cards_str(allowed_agents_list)
    allowed_agents_str = ", ".join(allowed_agents_list)
    
    from datetime import datetime
    test_input = "AAX20126042600P 판매상품 정보 조회해줘"
    
    user_prompt = planning_template.format(
        planningSystem="",
        today=datetime.now().strftime("%Y-%m-%d"),
        allowedAgents=allowed_agents_str,
        agentCards=agent_cards_str,
        userMessage=test_input,
        history=""
    )
    
    print("\n[SYSTEM PROMPT]")
    print(system_prompt)
    print("\n[USER PROMPT]")
    print(user_prompt)

asyncio.run(diagnose())
