"""
[Sub-Agent] 외부 요청 → 내부 도메인 객체 변환 팩토리
=====================================================
책임: API 요청을 내부 도메인 컨텍스트로 표준화 변환
아키텍처 위치: API Support Layer — Request/Response 변환

참고: 현재는 main.py의 ChatRequest Pydantic 모델을 직접 사용 중.
      이 팩토리는 API 스키마와 도메인 모델 사이의 변환 계층을 제공.
"""

import uuid
from typing import Optional, Dict, Any
from ...domain.models import Message
from ...domain.enums import AgentRole

class AgentRequestFactory:
    """
    외부 API 입력 → 내부 요청 객체 생성 표준화.
    - session_id/message → 도메인 컨텍스트로 변환
    - request_id/trace_id 자동 생성 (누락 시)
    - 사용처: chat_usecase 진입 전 데이터 준비
    """
    @staticmethod
    def create_chat_context(
        session_id: str, 
        message: str, 
        request_id: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """외부 요청에서 내부 실행 컨텍스트 생성"""
        return {
            "session_id": session_id,
            "message": message,
            "request_id": request_id or str(uuid.uuid4()),
            "trace_id": trace_id or f"tr-{uuid.uuid4().hex[:12]}",
            "task_id": str(uuid.uuid4())
        }
