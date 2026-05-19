import structlog
from typing import Dict, Any
from ...ports.interfaces import OrchestrationEngine

logger = structlog.get_logger()

from .burr_factory import BurrWorkflowFactory

# ──────────────────────────────────────────────
# Burr 오케스트레이션 엔진 어댑터
# ──────────────────────────────────────────────
# OrchestrationEngine 포트의 Burr 구현체.
# BurrWorkflowFactory.create_application_builder()로 빌더를 생성하고,
# initial_state를 주입한 후 build() → arun()으로 실행한다.
# LangGraphAdapter와 동일한 인터페이스로 동작한다.
class BurrAdapter(OrchestrationEngine):
    def __init__(self, factory: BurrWorkflowFactory):
        self.factory = factory

    # Burr 애플리케이션 실행
    # ① initial_state에서 trace_id 추출 (에이전트 간 추적용)
    # ② 기본 상태(plans=[], history=[], loop_count=0)와 병합
    # ③ ApplicationBuilder에 상태 주입 → build() → arun()
    # ④ Burr State를 dict로 변환하여 반환
    async def execute(self, 
                      session_id: str, 
                      task_id: str, 
                      initial_state: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("subagent_burr_execution_start", task_id=task_id)
        
        trace_id = initial_state.get("trace_id", "unknown")
        
        # 기본 상태와 initial_state 병합 (중복 키는 initial_state 우선)
        state_to_inject = {
            "plans": [],
            "history": [],
            "loop_count": 0,
            **initial_state
        }
        
        app = (
            self.factory.create_application_builder(session_id, task_id, trace_id)
            .with_state(**state_to_inject)
            .build()
        )
        
        # compose_response 노드에서 중단 → 최종 결과 수집
        last_action, result, state = await app.arun(
            halt_after=["compose_response"]
        )
        
        logger.info("subagent_burr_execution_finished", task_id=task_id, last_action=last_action)
        
        # Burr State → dict 변환 (버전 호환성: as_dict() 또는 items())
        return state.as_dict() if hasattr(state, "as_dict") else dict(state.items())
