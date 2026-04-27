import httpx
import json
import asyncio

async def fetch_card(name, url):
    payload = {
        "jsonrpc": "2.0",
        "id": f"check-{name}",
        "method": "agent/card",
        "params": {}
    }
    print(f"\n[실행] {name} 에이전트 카드 조회 중... ({url})")
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                result = resp.json().get("result", {})
                print(f"✅ {name} 응답 성공:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"❌ {name} 응답 오류 (HTTP {resp.status_code})")
    except Exception as e:
        print(f"⚠️ {name} 연결 실패: {str(e)}")

async def main():
    endpoints = {
        "product": "http://localhost:8082/a2a/product",
        "reservation": "http://localhost:8082/a2a/reservation"
    }
    await asyncio.gather(*(fetch_card(name, url) for name, url in endpoints.items()))

if __name__ == "__main__":
    asyncio.run(main())
