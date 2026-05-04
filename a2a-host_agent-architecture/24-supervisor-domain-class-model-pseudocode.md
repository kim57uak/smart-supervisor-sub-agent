# 24. Supervisor Domain Class Model Reference

Updated: 2026-05-04 (Implementation Aligned)

## Core Execution Models

```python
class FrozenRoutingStep(BaseModel):
    order: int
    agent_key: str
    method: str
    source_type: str  # PLANNER | HANDOFF
    reason: str
    arguments: Dict[str, Any]
    handoff_depth: int
    parent_agent_key: Optional[str] = None
    pre_hitl_a2ui: Optional[str] = None

class FrozenExecutionPlan(BaseModel):
    task_id: str
    session_id: str
    request_id: str
    trace_id: str
    state_version: int
    execution_mode: str  # SEND | STREAM
    frozen_plan_hash: str
    routing_queue: List[FrozenRoutingStep]
    execution_constraints: ExecutionConstraintSet
    review_reason: Optional[str] = None
```

## Core Execution logic (Service Tier)

### 1. SupervisorAgentService (API Entry)
```python
# supervisor_agent_service.py
async def handle_request(self, session_id: str, message: str, request_id: str):
    # 1. 멱등성 체크 및 예약
    # 2. LlmPlanningService를 통한 2단계 플래닝 (Routing + HITL Policy)
    review_required, plan_data = await self.planner.plan(message, context)
    
    # 3. 계획 영속화 (FrozenExecutionPlan)
    # 4. 리뷰 필요 시 스냅샷 생성 및 중단, 미필요 시 작업 큐 적재
    if review_required:
        await self.persistence.save_snapshot(snapshot)
        return {"status": "REVIEW_REQUIRED", "task_id": task_id}
    
    await self.queue.enqueue(task_id, payload)
    return {"status": "ACCEPTED", "task_id": task_id}
```

### 2. SupervisorGraphExecutionService (Worker Internal)
```python
# supervisor_graph_execution_service.py
async def execute(self, session_id: str, task_id: str, execution_plan: FrozenExecutionPlan):
    # 1. 오케스트레이션 엔진(LangGraph/Burr) 호출
    # Workflow: select_next_agent -> invoke_agent -> update_swarm_state -> check_completion
    final_state = await self.engine.execute(session_id, task_id, execution_plan)
    
    # 2. 결과 합성 (LlmResponseComposeService)
    final_answer = await self.composer.compose(final_state["results"], final_state["context"])
    
    # 3. 최종 상태 업데이트 및 메시지 저장
    await self.persistence.complete_task(task_id, final_answer)

### 3. Voice Interaction Flow (Real-time STT)
```python
# supervisor.py (WebSocket)
async def websocket_voice_stream(websocket: WebSocket):
    # 1. VoiceAdapterFactory를 통한 어댑터(OpenAI 등) 생성
    adapter = VoiceAdapterFactory.create_adapter()
    await adapter.connect()
    
    # 2. 비동기 리스닝 루프 시작 (Forward to Client)
    async def listen_loop():
        async for event in adapter.listen():
            await websocket.send_json(event)
            
    # 3. 오디오 수신 및 스트리밍
    while True:
        data = await websocket.receive()
        if "bytes" in data:
            await adapter.send_audio(data["bytes"])
```
```

## Security & Snapshot Models

```python
class ReviewedExecutionSnapshot(BaseModel):
    task_id: str
    session_id: str
    resume_token: str
    frozen_plan: FrozenExecutionPlan
    review_reason: Optional[str] = None

class SnapshotVerificationResult(BaseModel):
    signature_matched: bool
    ttl_valid: bool
    is_allowed: bool  # Logic property
```
