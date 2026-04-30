import httpx
import json
import asyncio
import sys
import os

# Rationale (Why): Console-based E2E test to verify the fix from entry point to MCP transport.
# Ensures that headers, ports, and synchronized keys are working correctly.

async def test_endpoint(name: str, url: str, payload: dict, method: str = "POST"):
    print(f"\n{'='*20} {name} 테스트 {'='*20}")
    print(f"URL: {url}")
    if method == "POST":
        print(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "POST":
                resp = await client.post(url, json=payload)
            else:
                resp = await client.get(url)
            
            print(f"\n[Response Status] {resp.status_code}")
            try:
                data = resp.json()
                print(f"[Response Body]\n{json.dumps(data, indent=2, ensure_ascii=False)}")
                if resp.status_code in [200, 201, 202]:
                    print(f"✅ {name} 성공")
                else:
                    print(f"❌ {name} 실패 (상태 코드 오류)")
            except:
                print(f"❌ {name} 실패: {resp.text}")
    except Exception as e:
        print(f"⚠️ 에러 발생: {str(e)}")

async def main():
    # Rationale (Why): Using port 8082 as synchronized in the previous step.
    base_url = "http://localhost:8082"
    
    # 1. Health Check
    await test_endpoint("Health Check", f"{base_url}/health", {}, "GET")

    # 2. User Chat API (일반 사용자용)
    # Rationale: 'sale-product' 스코어에 대한 권한 검증 및 MCP 연동 확인
    chat_payload = {
        "session_id": "console-tester",
        "message": "AAX20126042900A 상품의 상세 정보를 알려줘.",
        "request_id": "req-chat-001"
    }
    # Note: Using the hyphenated path as per Document 06/07 refactoring rules.
    await test_endpoint("User Chat API", f"{base_url}/api/v1/agent/sale-product/chat", chat_payload)

    # 3. A2A JSON-RPC API (슈퍼바이저용)
    # Rationale: 'X-MCP-Server-Id' 헤더와 하이픈(-) 기반 라우팅 키 동기화 확인
    a2a_payload = {
        "jsonrpc": "2.0",
        "id": "a2a-001",
        "method": "message/send",
        "params": {
            "session_id": "supervisor-node",
            "message": "weather 정보를 알려줘 (Seoul)",
            "trace_id": "trace-uuid-999"
        }
    }
    await test_endpoint("A2A Standard API", f"{base_url}/a2a/weather", a2a_payload)

if __name__ == "__main__":
    print("🚀 서브에이전트 E2E 통합 테스트를 시작합니다...")
    # Rationale (Why): Ensure the server is likely running on 8082 before testing.
    asyncio.run(main())
