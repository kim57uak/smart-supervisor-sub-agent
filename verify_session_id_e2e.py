import asyncio
import json
from pathlib import Path
import uuid

import httpx


SUPERVISOR_URL = "http://127.0.0.1:8000/a2a/supervisor"
SESSION_ID = "sess-e2e-reservation-session-id-check"
USER_MESSAGE = "AAX20126043000P 판매상품으로 예약 생성해줘"


def _read_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="ignore")


def _assert_contains(haystack: str, needle: str, label: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"[FAIL] missing '{needle}' in {label}")


async def main() -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        send_payload = {
            "jsonrpc": "2.0",
            "id": "e2e-send",
            "method": "message/send",
            "params": {
                "session_id": SESSION_ID,
                "request_id": f"req-{uuid.uuid4()}",
                "message": USER_MESSAGE,
            },
        }
        send_resp = await client.post(SUPERVISOR_URL, json=send_payload)
        send_resp.raise_for_status()
        send_json = send_resp.json()
        task_id = send_json.get("result", {}).get("task_id", "")
        if not task_id:
            raise AssertionError(f"[FAIL] task_id missing in send response: {send_json}")

        decide_payload = {
            "jsonrpc": "2.0",
            "id": "e2e-decide",
            "method": "tasks/review/decide",
            "params": {
                "task_id": task_id,
                "decision": "APPROVE",
                "session_id": SESSION_ID,
                "comment": "approved_from_verify_script",
            },
        }
        decide_resp = await client.post(SUPERVISOR_URL, json=decide_payload)
        decide_resp.raise_for_status()
        decide_json = decide_resp.json()
        if decide_json.get("error"):
            raise AssertionError(f"[FAIL] review decide failed: {decide_json}")

    await asyncio.sleep(2.0)

    sup_uvicorn = _read_text("src/supervisor-agent/uvicorn.log")
    sup_workers = "".join(
        _read_text(f"src/supervisor-agent/worker_{i}.log") for i in range(1, 5)
    )
    sub_uvicorn = _read_text("src/sub-agent/uvicorn.log")

    sup_all = sup_uvicorn + "\n" + sup_workers
    _assert_contains(sup_all, SESSION_ID, "supervisor logs")
    _assert_contains(sup_all, "a2a_payload_built", "supervisor logs")
    _assert_contains(sub_uvicorn, SESSION_ID, "sub-agent uvicorn.log")
    _assert_contains(sub_uvicorn, "authorization_successful", "sub-agent uvicorn.log")

    print(json.dumps({"ok": True, "session_id": SESSION_ID}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
