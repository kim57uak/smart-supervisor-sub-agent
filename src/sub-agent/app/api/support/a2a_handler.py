"""
[Sub-Agent] A2A JSON-RPC 요청 처리 핸들러
===========================================
책임: A2A 프로토콜(JSON-RPC 2.0) 요청을 수신하여 Method에 따라 분기 처리
아키텍처 위치: API Support Layer — A2A Protocol Handler

지원 메서드:
  - SendMessage / SendStreamingMessage: 〓> AgentExecutor 실행 후 응답 반환
  - CancelTask: 태스크 취소 (placeholder)
  - GetTask / ListTasks: 태스크 상태 조회 (placeholder)

메서드 Alias:
  - "message/send" → "SendMessage" (레거시 호환)
  - "message/stream" → "SendStreamingMessage"
  - "tasks/get" → "GetTask"
  - "tasks/list" → "ListTasks"
  - "tasks/cancel" → "CancelTask"

주의:
  - session_id는 반드시 요청 파라미터로 전달되어야 함
  - task_id 누락 시 CPython id() 사용 (uuid로 대체 필요)
"""

import uuid
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from ...application.execution.executor import AgentExecutor

class JsonRpcRequest(BaseModel):
    """A2A JSON-RPC 2.0 요청"""
    jsonrpc: str = "2.0"
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)
    id: Optional[Any] = None

class JsonRpcResponse(BaseModel):
    """A2A JSON-RPC 2.0 응답"""
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[Any] = None

async def handle_a2a_request(
    agent_name: str, 
    request: JsonRpcRequest,
    executor: Optional[AgentExecutor] = None
) -> JsonRpcResponse:
    """
    A2A JSON-RPC 요청의 진입점.
    Method에 따라 실행/취소/조회/Placeholder 로직 분기.
    """
    method_mapping = {
        "message/send": "SendMessage",
        "message/stream": "SendStreamingMessage",
        "tasks/get": "GetTask",
        "tasks/list": "ListTasks",
        "tasks/cancel": "CancelTask"
    }
    
    canonical_method = method_mapping.get(request.method, request.method)
    
    # === 실제 실행 (executor 제공 시) ===
    if canonical_method in ["SendMessage", "SendStreamingMessage"] and executor:
        def _recover_session_id_from_params(params: Dict[str, Any]) -> str:
            sid = params.get("session_id")
            if sid:
                return str(sid)
            return ""

        message = request.params.get("message", "")
        
        # Gemini rich message 포맷 처리 (parts 구조)
        if isinstance(message, dict):
            parts = message.get("parts", [])
            if parts and isinstance(parts, list):
                message = " ".join([p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p])
            else:
                message = str(message)
        
        session_id = request.params.get("session_id") or _recover_session_id_from_params(request.params)
        if not session_id:
            return JsonRpcResponse(
                error={"code": -32602, "message": "session_id is required"},
                id=request.id
            )
        trace_id = request.params.get("trace_id", "unknown")
        task_id = request.params.get("task_id", f"task-{uuid.uuid4().hex[:12]}")

        try:
            final_state = await executor.execute(session_id, task_id, message, trace_id=trace_id)
            
            final_answer = final_state.get("final_answer", "")
            if not final_answer and final_state.get("results"):
                last_res = final_state["results"][-1]
                final_answer = last_res.get("output", str(last_res))

            result = {
                "status": "COMPLETED",
                "agent": agent_name,
                "payload": {
                    "answer": final_answer,
                    "data": {"results": final_state.get("results", [])}
                }
            }
            return JsonRpcResponse(result=result, id=request.id)
        except Exception as e:
            return JsonRpcResponse(
                error={"code": -32000, "message": f"Execution error: {str(e)}"},
                id=request.id
            )
    
    # === 태스크 취소 ===
    if canonical_method == "CancelTask":
        task_id = request.params.get("id") or request.params.get("task_id")
        return JsonRpcResponse(
            result={"task_id": task_id, "status": "CANCELED", "success": True},
            id=request.id
        )

    # === Placeholder (executor 없을 때의 fallback) ===
    if canonical_method in ["SendMessage", "SendStreamingMessage"]:
        message = request.params.get("message", "")
        
        result = {
            "status": "COMPLETED",
            "agent": agent_name,
            "payload": {
                "answer": f"[{agent_name}] 요청 '{message}'을(를) 처리했습니다. (Method: {canonical_method})",
                "data": {"agent": agent_name, "processed": True, "method": canonical_method}
            }
        }
        return JsonRpcResponse(result=result, id=request.id)
    
    # === 알 수 없는 메서드 ===
    return JsonRpcResponse(
        error={
            "code": -32601,
            "message": f"Method not found: {request.method}"
        },
        id=request.id
    )
