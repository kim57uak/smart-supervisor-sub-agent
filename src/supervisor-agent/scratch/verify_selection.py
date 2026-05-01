import asyncio
import uuid
import httpx
import json
import os
import sys
from dotenv import load_dotenv

# Load .env
load_dotenv(os.path.join(os.getcwd(), "src", "supervisor-agent", ".env"))

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src", "supervisor-agent"))

from httpx import ASGITransport
from app.main import app
from app.domain.enums import TaskState, Decision

async def verify_hitl_and_selection():
    print("==================================================")
    print(" VERIFYING AGENT SELECTION & HITL FLOW")
    print("==================================================")
    
    transport = ASGITransport(app=app)
    api_prefix = "/a2a/supervisor"
    
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # --- 1. Send Reservation Request ---
        print("\n[Step 1] Sending reservation request")
        session_id = f"trace-res-{uuid.uuid4().hex[:8]}"
        send_request = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "session_id": session_id,
                "message": "AAX20126043000P 예약 생성해죠.이름 김병두 전화번호 01038569626"
            },
            "id": 1
        }
        
        resp = await client.post(api_prefix, json=send_request)
        data = resp.json()
        print(f"Initial Response Status: {data.get('result', {}).get('status')}")
        
        result = data.get("result", {})
        task_id = result.get("task_id")
        
        # --- 2. Approve ---
        print(f"\n[Step 2] Approving task {task_id}")
        approve_request = {
            "jsonrpc": "2.0",
            "method": "tasks/review/decide",
            "params": {
                "task_id": task_id,
                "decision": Decision.APPROVE.value,
                "session_id": session_id
            },
            "id": 2
        }
        await client.post(api_prefix, json=approve_request)
        print("✅ Approved.")
        
        # --- 3. Stream & Analysis ---
        print("\n[Step 3] Monitoring events for Agent Selection & Execution")
        await asyncio.sleep(1) # Small delay for index propagation
        stream_request = {
            "jsonrpc": "2.0",
            "method": "tasks/events",
            "params": {"task_id": task_id, "cursor": "0"},
            "id": 3
        }
        
        async with client.stream("POST", f"{api_prefix}/stream", json=stream_request, timeout=60.0) as response:
            async for line in response.aiter_lines():
                if not line: continue
                try:
                    event_data = json.loads(line)
                    event_type = event_data.get("event_type")
                    payload = event_data.get("payload", {})
                    
                    if event_type == "progress":
                        progress_type = payload.get("type")
                        if progress_type and progress_type.startswith("calling_"):
                            print(f"🔍 AGENT SELECTED: {progress_type[8:]} (Order: {payload.get('data', {}).get('order')})")
                        elif progress_type == "routing_summary":
                            print(f"📊 ROUTING SUMMARY: {json.dumps(payload.get('data', {}).get('steps'), indent=2)}")
                            
                    elif event_type == "chunk":
                        # print(f"📝 TOKEN: {payload.get('answer', '')}")
                        pass
                    elif event_type == "done":
                        print("\n✅ TASK COMPLETED")
                        print(f"Final Answer Preview: {payload.get('final_answer')[:100]}...")
                        break
                    elif event_type == "error":
                        print(f"❌ ERROR: {payload}")
                        break
                except:
                    pass

if __name__ == "__main__":
    asyncio.run(verify_hitl_and_selection())
