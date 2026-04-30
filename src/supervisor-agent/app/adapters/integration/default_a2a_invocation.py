from typing import Dict, Any, AsyncGenerator
import json
import httpx
import structlog
from ...ports.integration_ports import A2AInvocationService
from ...core.config import settings
from ...domain.enums import ApiMethod

logger = structlog.get_logger()


class DefaultA2AInvocationService(A2AInvocationService):
    """
    A2A 표준 JSON-RPC를 통해 downstream agent를 실제 호출하는 어댑터.
    supervisor.yml routing 설정에서 endpoint를 읽어 HTTP 통신한다.
    """
    
    # Circuit Breaker state (in-memory)
    _failure_counts: Dict[str, int] = {}
    _circuit_open_until: Dict[str, float] = {}

    def _check_circuit_breaker(self, agent_key: str):
        """회로 차단 상태를 확인하고 열려있으면 예외를 발생시킨다."""
        import time
        
        cb_cfg = settings.supervisor_config.get("circuit-breaker", {})
        if not cb_cfg.get("enabled", True):
            return

        open_until = self._circuit_open_until.get(agent_key, 0)
        if time.time() < open_until:
            logger.warning("a2a_circuit_breaker_open", agent_key=agent_key, remaining=round(open_until - time.time(), 1))
            raise RuntimeError(f"Circuit Breaker is OPEN for agent: {agent_key}")

    def _record_success(self, agent_key: str):
        """성공 시 실패 카운트를 초기화한다."""
        self._failure_counts[agent_key] = 0
        if agent_key in self._circuit_open_until:
            del self._circuit_open_until[agent_key]

    def _record_failure(self, agent_key: str):
        """실패 시 카운트를 증가시키고 임계값 도달 시 회로를 연다."""
        import time
        
        cb_cfg = settings.supervisor_config.get("circuit-breaker", {})
        if not cb_cfg.get("enabled", True):
            return

        threshold = cb_cfg.get("failure-threshold", 2)
        open_duration = cb_cfg.get("open-duration-ms", 3000) / 1000.0
        
        count = self._failure_counts.get(agent_key, 0) + 1
        self._failure_counts[agent_key] = count
        
        if count >= threshold:
            self._circuit_open_until[agent_key] = time.time() + open_duration
            logger.error("a2a_circuit_breaker_tripped", agent_key=agent_key, duration=open_duration)

    def _resolve_endpoint(self, agent_key: str) -> str:
        """supervisor.yml routing 설정에서 해당 에이전트의 endpoint를 조회한다."""
        routing_config = settings.supervisor_config.get("routing", {})
        agent_config = routing_config.get(agent_key, {})
        endpoint = agent_config.get("endpoint")
        if not endpoint:
            raise ValueError(f"Endpoint not found for agent_key: {agent_key} in supervisor.yml routing")
        return endpoint

    def _resolve_timeout(self, agent_key: str) -> float:
        """supervisor.yml routing 설정에서 해당 에이전트의 timeout을 조회한다."""
        routing_config = settings.supervisor_config.get("routing", {})
        agent_config = routing_config.get(agent_key, {})
        timeout_ms = agent_config.get("timeout-ms", 120000)
        return timeout_ms / 1000.0  # ms → seconds

    def _build_jsonrpc_payload(self, method: str, arguments: Dict[str, Any], agent_key: str) -> Dict[str, Any]:
        """A2A 표준 JSON-RPC 요청 페이로드를 구성한다."""
        import uuid
        
        # arguments에서 message 추출
        message = arguments.get("message", str(arguments))
        
        return {
            "jsonrpc": "2.0",
            "id": f"sup-{agent_key}-{uuid.uuid4().hex[:8]}",
            "method": method,
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"text": message}]
                }
            }
        }

    async def invoke(self, agent_key: str, method: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """downstream agent에 A2A JSON-RPC 요청을 보내고 결과를 반환한다."""
        endpoint = self._resolve_endpoint(agent_key)
        timeout = self._resolve_timeout(agent_key)
        
        # Unary 호출이므로 streaming method를 message/send로 정규화
        inv_cfg = settings.supervisor_config.get("invocation", {})
        streaming_methods = set(inv_cfg.get("streaming-methods", ["message/stream", "SendStreamingMessage"]))
        default_method = inv_cfg.get("default-method", ApiMethod.SEND_MESSAGE.value)
        
        invoke_method = default_method if method in streaming_methods else method
        
        payload = self._build_jsonrpc_payload(invoke_method, arguments, agent_key)
        
        # Resilience Settings
        retry_cfg = settings.supervisor_config.get("retry", {})
        max_retries = retry_cfg.get("max-retries", 0)
        initial_backoff = retry_cfg.get("initial-backoff-ms", 500) / 1000.0
        max_backoff = retry_cfg.get("max-backoff-ms", 3000) / 1000.0
        
        current_attempt = 0
        last_error = None
        
        while current_attempt <= max_retries:
            try:
                # 1. Circuit Breaker Check
                self._check_circuit_breaker(agent_key)
                
                logger.info("a2a_invoke_start", 
                            agent_key=agent_key, 
                            attempt=current_attempt + 1,
                            method=invoke_method)
                
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(endpoint, json=payload)
                    
                    # Rationale (Why): A2A standard (Doc 08) specifies that 202 Accepted is the correct 
                    # response for async tasks. Treating both 200 and 202 as success prevents false failures.
                    if resp.status_code not in [200, 202]:
                        raise httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=None, response=resp)
                    
                    # For 202 Accepted, the body might be empty or just a task ACK
                    if resp.status_code == 202:
                        logger.info("a2a_invoke_accepted", agent_key=agent_key)
                        return {
                            "agent_key": agent_key,
                            "method": method,
                            "status": "COMPLETED",
                            "payload": {"answer": f"[{agent_key}] 요청이 접수되었습니다.", "data": {"status": "ACCEPTED"}}
                        }
                    
                    rpc_response = resp.json()
                    
                    # JSON-RPC error 처리 (error가 null이 아닌 경우만)
                    error_obj = rpc_response.get("error")
                    if error_obj is not None:
                        # RPC 에러는 재시도하지 않고 즉시 반환 (비즈니스 로직 에러로 취급)
                        self._record_success(agent_key) # 통신은 성공했으므로
                        logger.warning("a2a_invoke_rpc_error", agent_key=agent_key, error=error_obj)
                        return {
                            "agent_key": agent_key,
                            "method": method,
                            "status": "FAILED",
                            "payload": {
                                "answer": error_obj.get("message", "Unknown RPC error") if isinstance(error_obj, dict) else str(error_obj),
                                "data": error_obj,
                                "errorCode": str(error_obj.get("code", "UNKNOWN")) if isinstance(error_obj, dict) else "UNKNOWN"
                            }
                        }
                    
                    # 정상 응답
                    self._record_success(agent_key)
                    result = rpc_response.get("result")
                    if result is None:
                        logger.warning("a2a_invoke_missing_result", agent_key=agent_key, body=rpc_response)
                        result = rpc_response
                    
                    answer = self._extract_answer(result)
                    logger.info("a2a_invoke_success", agent_key=agent_key, answer_length=len(answer))
                    
                    return {
                        "agent_key": agent_key,
                        "method": method,
                        "status": "COMPLETED",
                        "payload": {"answer": answer, "data": result}
                    }
                    
            except Exception as e:
                current_attempt += 1
                last_error = e
                self._record_failure(agent_key)
                
                if current_attempt <= max_retries:
                    import asyncio
                    backoff = min(initial_backoff * (2 ** (current_attempt - 1)), max_backoff)
                    logger.warning("a2a_invoke_retry", agent_key=agent_key, attempt=current_attempt, next_backoff=backoff, error=str(e))
                    await asyncio.sleep(backoff)
                else:
                    logger.error("a2a_invoke_failed_all_attempts", agent_key=agent_key, total_attempts=current_attempt, error=str(e))
        
        # 모든 시도 실패 시
        return {
            "agent_key": agent_key,
            "method": method,
            "status": "FAILED",
            "payload": {
                "answer": f"Downstream agent error after {current_attempt} attempts: {str(last_error)}",
                "data": None,
                "errorCode": "INVOCATION_ERROR"
            }
        }

    async def invoke_stream(self, agent_key: str, method: str, arguments: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """downstream agent에 A2A 스트리밍 요청을 보낸다."""
        endpoint = self._resolve_endpoint(agent_key)
        timeout = self._resolve_timeout(agent_key)
        
        # Streaming method 보장
        inv_cfg = settings.supervisor_config.get("invocation", {})
        streaming_methods = inv_cfg.get("streaming-methods", ["message/stream", "SendStreamingMessage"])
        
        # 첫 번째 스트리밍 메서드를 기본값으로 사용
        invoke_method = method if method in streaming_methods else streaming_methods[0]
        
        payload = self._build_jsonrpc_payload(invoke_method, arguments, agent_key)
        
        logger.info("a2a_invoke_stream_start", agent_key=agent_key, endpoint=endpoint, method=invoke_method)
        
        try:
            # 1. Circuit Breaker Check
            self._check_circuit_breaker(agent_key)
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", endpoint, json=payload, 
                                          headers={"Accept": "text/event-stream"}) as resp:
                    if resp.status_code != 200:
                        self._record_failure(agent_key)
                        yield {
                            "agent_key": agent_key,
                            "method": method,
                            "status": "FAILED",
                            "payload": {"answer": f"HTTP {resp.status_code}", "data": None}
                        }
                        return
                    
                    # Connection success
                    self._record_success(agent_key)
                    buffer = ""
                    async for chunk in resp.aiter_text():
                        # Rationale (Why): Added detailed chunk logging to trace stream data flow 
                        # and diagnose why the user might not be seeing output.
                        logger.debug("a2a_stream_chunk_received", agent_key=agent_key, chunk_size=len(chunk))
                        buffer += chunk
                        while "\n\n" in buffer:
                            event_str, buffer = buffer.split("\n\n", 1)
                            # Parse SSE event
                            data_line = ""
                            for line in event_str.split("\n"):
                                if line.startswith("data: "):
                                    data_line = line[6:]
                            
                            if data_line:
                                try:
                                    event_data = json.loads(data_line)
                                    answer = self._extract_answer_from_event(event_data)
                                    if answer:
                                        logger.debug("a2a_stream_event_parsed", agent_key=agent_key, answer_preview=answer[:50])
                                        yield {
                                            "agent_key": agent_key,
                                            "method": method,
                                            "payload": {"answer": answer, "data": event_data}
                                        }
                                except json.JSONDecodeError as e:
                                    logger.warning("a2a_stream_json_decode_failed", agent_key=agent_key, error=str(e), data=data_line)
                                    pass
                                    
        except Exception as e:
            self._record_failure(agent_key)
            logger.error("a2a_invoke_stream_error", agent_key=agent_key, error=str(e))
            yield {
                "agent_key": agent_key,
                "method": method,
                "status": "FAILED",
                "payload": {"answer": f"Stream error: {str(e)}", "data": None}
            }

    def _extract_answer(self, result: Any) -> str:
        """JSON-RPC result에서 사용자에게 보여줄 답변 텍스트를 추출한다."""
        if result is None:
            return ""
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            # A2A 표준: result.status.message.parts[*].text
            status = result.get("status")
            if isinstance(status, dict):
                message = status.get("message")
                if isinstance(message, dict):
                    parts = message.get("parts", [])
                    texts = [p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p]
                    if texts:
                        return "\n".join(texts)
            
            # Fallback: result.answer 또는 result.message
            if "answer" in result:
                return str(result["answer"])
            if "message" in result and isinstance(result["message"], str):
                return result["message"]
            
            # 만약 result 자체가 message 포맷인 경우 (params와 동일 포맷)
            parts = result.get("parts")
            if isinstance(parts, list):
                texts = [p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p]
                if texts:
                    return "\n".join(texts)
                    
            # Last resort: JSON dump
            return json.dumps(result, ensure_ascii=False)
        return str(result)

    def _extract_answer_from_event(self, event_data: Any) -> str:
        """SSE 이벤트 데이터에서 답변 텍스트를 추출한다."""
        if isinstance(event_data, dict):
            result = event_data.get("result", event_data)
            return self._extract_answer(result)
        return str(event_data) if event_data else ""
