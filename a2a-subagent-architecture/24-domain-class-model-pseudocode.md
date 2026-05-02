# 24. Sub-Agent Domain Pseudocode

## Core Models (domain/models.py)

```python
class AgentTask(BaseModel):
    task_id: str
    session_id: str
    request_id: str
    status: ProcessStatus  # ACCEPTED | RUNNING | COMPLETED | FAILED
    result: Optional[AgentExecutionResult] = None

class ToolPlan(BaseModel):
    tool_name: str
    server_name: str
    arguments: Dict[str, Any]
    reasoning: str

class PlanningContext(BaseModel):
    session_id: str
    history: List[Message]
    available_tools: List[Dict[str, Any]]
```

## Core Execution logic (Service Tier)

### 1. AgentChatUseCase (API Entry)
```python
async def handle_chat_request(self, session_id, message, request_id):
    # 멱등성 체크
    is_new = await self.persistence.store.check_and_reserve_idempotency(request_id, task_id)
    if not is_new: return {"status": "ALREADY_PROCESSED"}

    # 초기 상태 저장
    task = AgentTask(task_id=task_id, session_id=session_id, status=ProcessStatus.ACCEPTED)
    await self.persistence.store.save_task(task)

    # 워커 큐 적재 (Decoupled)
    await self.queue.enqueue({"task_id": task_id, "session_id": session_id, "message": message})
    return {"status": "ACCEPTED", "task_id": task_id}
```

### 2. AgentExecutor (Worker Internal)
```python
async def execute(self, session_id, task_id, message):
    # 1. 상태를 RUNNING으로 전이
    await self.persistence.update_status(task_id, ProcessStatus.RUNNING)
    
    # 2. 오케스트레이션 엔진 호출 (LangGraph/Burr)
    # Workflow: load_context -> select_tools -> execute_tools -> compose_response
    final_state = await self.engine.execute(session_id, task_id, initial_state)

    # 3. 결과 영속화 및 히스토리 저장
    result = AgentExecutionResult(task_id=task_id, final_answer=final_state["final_answer"])
    await self.persistence.complete_task(task_id, result)
    await self.persistence.store.save_message(session_id, {"role": "assistant", "content": result.final_answer})
```

## MCP Tool Execution (Adapter Tier)

```python
# McpToolExecutor.execute
async def execute(self, plan: ToolPlan, runtime_fields: Dict):
    # McpToolRegistry에서 해당 서버의 엔드포인트 정보 획득
    # MCP 서버로 JSON-RPC 호출 (HTTP/SSE Transport)
    # 결과를 표준 형식으로 반환
    return {"status": "success", "output": tool_result}
```
