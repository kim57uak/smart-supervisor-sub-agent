"""
[Sub-Agent] 내부 실행 결과 → 외부 API 응답 변환
=================================================
책임: 도메인 레이어의 실행 결과를 API 응답 스키마로 매핑
아키텍처 위치: API Support Layer — Response Mapping
"""

from typing import Dict, Any, Optional
from ...domain.enums import ProcessStatus

class AgentResponseMapper:
    """
    내부 결과 → 외부 API 응답 표준화 매퍼.
    - map_to_chat_response: 정상 수용 응답 (202 Accepted)
    - map_duplicate_response: 중복 요청 응답
    """
    @staticmethod
    def map_to_chat_response(
        task_id: str, 
        trace_id: str, 
        status: ProcessStatus = ProcessStatus.ACCEPTED
    ) -> Dict[str, Any]:
        """일반 채팅 요청 응답 생성"""
        return {
            "task_id": task_id,
            "status": status.value,
            "trace_id": trace_id,
            "stream_url": f"/api/v1/stream/{task_id}"
        }

    @staticmethod
    def map_duplicate_response(request_id: str, trace_id: str) -> Dict[str, Any]:
        """중복 요청 감지 응답 생성 (Idempotency)"""
        return {
            "status": "ALREADY_PROCESSED", 
            "request_id": request_id, 
            "trace_id": trace_id
        }
