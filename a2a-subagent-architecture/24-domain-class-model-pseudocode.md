# 24. Sub-Agent Domain Pseudocode

## Core Models (domain/models.py)

```python
class AgentTask(BaseModel):
    task_id: str
    session_id: str
    request_id: str
    status: ProcessStatus  # ACCEPTED | RUNNING | COMPLETED | FAILED
    result: Optional[AgentExecutionResult] = None
    state_version: int = 0

class ToolPlan(BaseModel):
    tool_name: str
    server_name: str
    arguments: Dict[str, Any]
    reasoning: str

class AiChatChunk(BaseModel):
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class PlanningContext(BaseModel):
    session_id: str
    history: List[Message]
    available_tools: List[Dict[str, Any]]
    current_plan: Optional[ToolPlan] = None
    tool_results: List[Dict[str, Any]] = Field(default_factory=list)
```

## Core Execution logic (Service Tier)

### 1. AgentChatUseCase (API Entry)
```python
# chat_usecase.py
async def handle_chat_request(self, session_id: str, message: str, request_id: str):
    # 멱등성 체크 및 예약
    task_id = f"task_{uuid4()}"
    is_new = await self.store.check_and_reserve_idempotency(request_id, task_id)
    if not is_new:
        # 기존 task_id를 조회하여 반환하거나 에러 처리
        return {"status": "ALREADY_PROCESSED"}

    # 초기 상태 저장 (status: ACCEPTED)
    task = AgentTask(
        task_id=task_id, 
        session_id=session_id, 
        request_id=request_id,
        status=ProcessStatus.ACCEPTED
    )
    await self.persistence.save_task(task)

    # 워커 큐 적재 (Decoupled)
    await self.queue.enqueue({
        "task_id": task_id, 
        "session_id": session_id, 
        "message": message,
        "request_id": request_id
    })
    return {"status": "ACCEPTED", "task_id": task_id}
```

### 2. AgentExecutor (Worker Internal)
```python
# executor.py
async def execute(self, session_id: str, task_id: str, message: str):
    # 1. 상태를 RUNNING으로 전이
    await self.persistence.update_status(task_id, ProcessStatus.RUNNING)
    
    # 2. 오케스트레이션 엔진 호출 (LangGraph/Burr)
    # initial_state 구성 시 이전 history 등 context 로드 포함
    initial_state = await self._prepare_initial_state(session_id, task_id, message)
    final_state = await self.engine.execute(session_id, task_id, initial_state)

    # 3. 결과 영속화 및 히스토리 저장
    result = AgentExecutionResult(
        task_id=task_id, 
        final_answer=final_state.get("final_answer", "")
    )
    await self.persistence.complete_task(task_id, result)
    await self.store.save_message(session_id, {"role": "assistant", "content": result.final_answer})
```

## MCP Tool Execution (Adapter Tier)

```python
# McpExecutor.execute (mcp_adapters.py)
async def execute(self, plan: ToolPlan):
    # 1. McpToolRegistry에서 해당 서버 및 도구 정보 확인
    # 2. McpClientSessionManager를 통해 세션 획득
    # 3. JSON-RPC 호출 수행
    # 4. 결과 반환
    return {"status": "success", "output": tool_result}
```
