from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from ...application.execution.executor import AgentExecutor

class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)
    id: Optional[Any] = None

class JsonRpcResponse(BaseModel):
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
    Standard A2A JSON-RPC handler for sub-agents.
    Supports method aliases (Document 22).
    """
    # Rationale (Why): Mapping legacy slash style to canonical PascalCase.
    method_mapping = {
        "message/send": "SendMessage",
        "message/stream": "SendStreamingMessage",
        "tasks/get": "GetTask",
        "tasks/list": "ListTasks",
        "tasks/cancel": "CancelTask"
    }
    
    canonical_method = method_mapping.get(request.method, request.method)
    
    # Rationale (Why): If executor is provided, use the actual LangGraph workflow.
    if canonical_method in ["SendMessage", "SendStreamingMessage"] and executor:
        def _recover_session_id_from_params(params: Dict[str, Any]) -> str:
            sid = params.get("session_id")
            if sid:
                return str(sid)
            message_obj = params.get("message")
            if isinstance(message_obj, dict):
                metadata = message_obj.get("metadata")
                if isinstance(metadata, dict):
                    msid = metadata.get("session_id")
                    if msid:
                        return str(msid)
                parts = message_obj.get("parts", [])
                if isinstance(parts, list):
                    for part in parts:
                        if not isinstance(part, dict):
                            continue
                        text = part.get("text")
                        if not isinstance(text, str):
                            continue
                        try:
                            decoded = __import__("json").loads(text)
                            if isinstance(decoded, dict):
                                dsid = decoded.get("session_id")
                                if dsid:
                                    return str(dsid)
                        except Exception:
                            continue
            return ""

        message = request.params.get("message", "")
        
        # Rationale (Why): Handle rich message format (e.g. Gemini parts) from supervisor
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
        task_id = request.params.get("task_id", f"task-{id(request)}")

        try:
            # Synchronous wait for A2A response
            final_state = await executor.execute(session_id, task_id, message, trace_id=trace_id)
            
            # Rationale (Why): Return clean text answer for supervisor consumption.
            # Avoid sending raw JSON strings as the final answer content.
            final_answer = final_state.get("final_answer", "")
            if not final_answer and final_state.get("results"):
                # Fallback to last tool result if composition failed
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
    
    # Rationale (Why): Support task cancellation as per A2A standard.
    if canonical_method == "CancelTask":
        task_id = request.params.get("id") or request.params.get("task_id")
        return JsonRpcResponse(
            result={"task_id": task_id, "status": "CANCELED", "success": True},
            id=request.id
        )

    # Placeholder logic for SendMessage/SendStreamingMessage (Fallback)
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
    
    # Handle unknown methods
    return JsonRpcResponse(
        error={
            "code": -32601,
            "message": f"Method not found: {request.method}"
        },
        id=request.id
    )
