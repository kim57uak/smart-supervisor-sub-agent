# 26. Agent Endpoint Refactoring Plan

Updated: 2026-04-28 (Aligned with Supervisor Enterprise Architecture)

## Current Direction

기존 도메인 endpoint는 레거시 계약을 유지하는 Facade 역할을 수행하며, 내부 로직은 **Decoupled Worker** 및 **Hexagonal Architecture** 기반으로 재구성한다.

## New Folder Structure (api/)

- `app/api/agent`: 일반 사용자용 챗 엔드포인트
- `app/api/a2a`: Supervisor 연동용 JSON-RPC 엔드포인트
- `app/api/support`: 공통 요청/응답 처리 및 검증 유틸리티

## Refactoring Rules (Python Standard)

- **Thin Endpoint**: 엔드포인트는 요청 파싱, 유효성 검사, 응답 매핑만 담당한다. 비즈니스 로직은 `application/execution` 계층으로 위임한다.
- **Snake Case**: 모든 내부 변수와 함수명은 `snake_case`를 사용한다.
- **Async First**: 모든 I/O 작업(DB, Redis, LLM)은 `async/await`를 기반으로 비동기 처리한다.
- **Pydantic Models**: 모든 요청과 응답 스키마는 `Pydantic`을 사용하여 엄격하게 관리한다.
- **Idempotency**: 모든 쓰기 요청은 `request_id`를 기반으로 멱등성을 보장한다.

## Authorization & Security

- **Session Isolation**: `session_id`를 기반으로 데이터 및 권한을 격리한다.
- **Scope-based Auth**: 엔드포인트 진입 시 `agent_authorization_service`를 호출하여 해당 `scope`에 대한 권한을 검증한다.

## Python Target Pseudocode (api/agent/chat.py)

```python
from fastapi import APIRouter, Depends
from ...application.execution.agent_service import AgentService
from ...schemas.agent import ChatRequest, ChatResponse

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    agent_service: AgentService = Depends(get_agent_service)
):
    # API 계층은 멱등성 및 큐잉을 담당하는 서비스 호출 후 즉시 응답
    result = await agent_service.handle_chat_request(
        session_id=request.session_id,
        message=request.message,
        request_id=request.request_id
    )
    return ChatResponse(**result)
```

## Key Modules to Implement

- `agent_authorization_service`
- `agent_request_factory`
- `agent_response_mapper`
- `a2a_jsonrpc_handler`
