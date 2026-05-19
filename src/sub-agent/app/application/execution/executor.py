"""
[Sub-Agent] 에이전트 실행 오케스트레이터
=========================================
책임: 태스크 실행의 전체 생명주기 관리 (상태 천이 + 엔진 호출 + 이벤트 발행)
아키텍처 위치: Application Layer — Execution

실행 흐름:
  1. 사용자 메시지 저장 (history)
  2. 상태 RUNNING으로 천이 + PROGRESS 이벤트 발행
  3. OrchestrationEngine.execute() → LangGraph/Burr 그래프 실행
  4. 완료 결과 저장 + DONE 이벤트 발행
  5. 실패 시 ERROR 이벤트 발행 후 예외 재throws

예외 처리:
  - engine.execute() 실패 시 ERROR 이벤트 발행 후 상위(NACK 처리)로 전파
  - 각 단계마다 ProgressPublisher를 통해 Supervisor에 실시간 상태 전달
"""

import structlog
from typing import Dict, Any
from app.core.config import settings
from app.domain.enums import ProcessStatus, EventType, AgentRole
from app.ports.interfaces import ProgressPublisher, OrchestrationEngine
from app.application.persistence.agent_persistence import AgentPersistence
from app.domain.models import AgentExecutionResult, Message

logger = structlog.get_logger(__name__)

class AgentExecutor:
    """
    서브에이전트 태스크 실행 오케스트레이터.
    Engine(추상화) + Persistence + Publisher를 조합하여 실행.
    """
    def __init__(
        self,
        engine: OrchestrationEngine,
        persistence: AgentPersistence,
        publisher: ProgressPublisher
    ):
        self.engine = engine
        self.persistence = persistence
        self.publisher = publisher

    async def execute(self, session_id: str, task_id: str, message: str, trace_id: str = "unknown"):
        """
        전체 실행 생명주기:
          save_message → update_status(RUNNING) → engine.execute → complete_task → DONE
        """
        log = logger.bind(trace_id=trace_id, task_id=task_id, session_id=session_id)
        log.info("execution_started", engine=settings.orchestration_engine)

        await self.persistence.store.save_message(
            session_id,
            {"role": AgentRole.USER.value, "content": message, "task_id": task_id},
        )
        raw_history = await self.persistence.store.get_messages(session_id, limit=20)
        history = [Message(role=h.get("role", AgentRole.USER.value), content=h.get("content", "")) for h in raw_history]

        # 초기 상태 생성
        initial_state = {
            "task_id": task_id,
            "session_id": session_id,
            "trace_id": trace_id,
            "user_message": message,
            "history": history,
            "plans": [],
            "results": [],
            "final_answer": "",
            "status": ProcessStatus.RUNNING
        }

        try:
            await self.persistence.update_status(task_id, ProcessStatus.RUNNING)
            
            await self.publisher.publish(session_id, task_id, {
                "event_type": EventType.PROGRESS.value,
                "payload": {"status": ProcessStatus.RUNNING.value}
            }, trace_id=trace_id)

            # 엔진 실행 (LangGraph 또는 Burr)
            final_state = await self.engine.execute(session_id, task_id, initial_state)

            # 완료 처리
            execution_result = AgentExecutionResult(
                task_id=task_id,
                final_answer=final_state.get("final_answer", ""),
                raw_data={"results": final_state.get("results", [])}
            )

            await self.persistence.complete_task(task_id, execution_result)
            await self.persistence.store.save_message(
                session_id,
                {"role": AgentRole.ASSISTANT.value, "content": execution_result.final_answer, "task_id": task_id},
            )

            await self.publisher.publish(session_id, task_id, {
                "event_type": EventType.DONE.value,
                "payload": {
                    "status": ProcessStatus.COMPLETED.value,
                    "final_answer": final_state.get("final_answer")
                }
            }, trace_id=trace_id)
            
            log.info("execution_completed")
            return final_state

        except Exception as e:
            log.error("execution_failed", error=str(e))
            await self.publisher.publish(session_id, task_id, {
                "event_type": EventType.ERROR.value,
                "payload": {"error": str(e)}
            }, trace_id=trace_id)
            raise
