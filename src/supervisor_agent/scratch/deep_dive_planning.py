import asyncio
import os
import sys
from dotenv import load_dotenv
import json

# Load .env
load_dotenv(os.path.join(os.getcwd(), "src", "supervisor-agent", ".env"))

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src", "supervisor-agent"))

from app.adapters.llm.llm_planning_service import LlmPlanningService
from app.application.execution.hitl_gate_service import PreHitlA2uiService
from app.domain.models import FrozenExecutionPlan, FrozenRoutingStep

async def deep_dive():
    planner = LlmPlanningService()
    a2ui_service = PreHitlA2uiService()
    
    user_input = "AAX20126043000P 예약 생성해죠.이름 김병두 전화번호 01038569626"
    print(f"--- [1. User Input] ---\n{user_input}\n")
    
    # Discovery
    print("--- [2. Discovery Check] ---")
    await planner.load_agent_cards()
    cards = planner.get_cached_agent_cards()
    print(f"Cached Agents: {list(cards.keys())}")
    
    # Planning
    print("\n--- [3. Planning Phase] ---")
    review_required, plan_data = await planner.plan(user_input, {"history": []})
    
    print(f"Review Required: {review_required}")
    print(f"Plan Data:\n{json.dumps(plan_data, indent=2, ensure_ascii=False)}")
    
    # Build Plan Object
    routing_queue = [FrozenRoutingStep(**step) for step in plan_data["routing_queue"]]
    plan = FrozenExecutionPlan(
        task_id="test-task",
        session_id="test-session",
        request_id="test-req",
        trace_id="test-trace",
        state_version=0,
        execution_mode="STREAM",
        request_hash="hash",
        frozen_plan_hash="hash",
        created_at=None,
        expires_at=None,
        routing_queue=routing_queue,
        planner_metadata=plan_data.get("planner_metadata", {}),
        execution_constraints=plan_data.get("execution_constraints", {}),
        review_reason=plan_data.get("planner_metadata", {}).get("review_reason")
    )
    
    # A2UI Check
    print("\n--- [4. A2UI Check] ---")
    a2ui_form = a2ui_service.build_pre_hitl_form(plan)
    if a2ui_form:
        print(f"A2UI Form Detected: {json.dumps(a2ui_form, indent=2, ensure_ascii=False)}")
    else:
        print("No A2UI form detected.")

if __name__ == "__main__":
    asyncio.run(deep_dive())
