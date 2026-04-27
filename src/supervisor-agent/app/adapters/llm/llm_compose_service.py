from typing import List, Dict, Any, AsyncGenerator, Tuple
from ...ports.llm_ports import SupervisorResponseComposeService
from ...infrastructure.llm.llm_runtime import LlmRuntime
from ...core.config import settings


class LlmSupervisorResponseComposeService(SupervisorResponseComposeService):
    def __init__(self):
        self.llm = LlmRuntime.get_chat_model()

    async def compose(self, results: List[Dict[str, Any]], context: Dict[str, Any]) -> str:
        """prompts.yml의 compose-system, compose-template을 사용하여 최종 응답을 합성한다."""
        user_message = context.get("message", "")
        
        # 히스토리 로딩 (supervisor.yml 정책 반영)
        history_config = settings.supervisor_config.get("history", {})
        max_turns = history_config.get("max-turns", 5)
        raw_history = context.get("history", [])
        recent_history = raw_history[-(max_turns * 2):] if raw_history else []
        history_str = ""
        for msg in recent_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            history_str += f"{role.upper()}: {content}\n"

        if not results:
            if user_message:
                try:
                    system_prompt = settings.prompts["compose-system"]
                    response = await self.llm.ainvoke([
                        ("system", system_prompt),
                        ("user", f"Context History:\n{history_str}\n\nUser Message: {user_message}")
                    ])
                    return response.content
                except Exception as e:
                    return f"응답 생성 실패: {str(e)}"
            return "조회된 결과가 없습니다."

        results_str = "\n".join([
            f"Agent [{res.get('agent_key')}]: {res.get('payload', {}).get('answer')}"
            for res in results
        ])
        
        # A2UI 설정 확인
        a2ui_enabled = settings.supervisor_config.get("a2ui", {}).get("enabled", False)
        a2ui_hint = "\nNote: A2UI rendering is ENABLED. Keep your summary brief if the results already contain UI data." if a2ui_enabled else ""

        system_prompt = settings.prompts["compose-system"]
        compose_template = settings.prompts["compose-template"]
        
        user_prompt = compose_template.format(
            composeSystem="",
            userMessage=user_message,
            history=history_str,
            downstreamResults=results_str + a2ui_hint
        )
        
        try:
            response = await self.llm.ainvoke([
                ("system", system_prompt),
                ("user", user_prompt)
            ])
            return response.content
            
        except Exception as e:
            return f"실행 완료 (LLM 합성 실패: {str(e)})"

    async def stream_compose(self, results: List[Dict[str, Any]], context: Dict[str, Any]) -> AsyncGenerator[Tuple[str, str], None]:
        """
        토큰 단위 스트리밍. prompts.yml의 프롬프트를 사용한다.
        Yields tuples of (event_type, token) where event_type is 'reasoning' or 'chunk'.
        """
        user_message = context.get("message", "")

        # 히스토리 로딩 (supervisor.yml 정책 반영)
        history_config = settings.supervisor_config.get("history", {})
        max_turns = history_config.get("max-turns", 5)
        raw_history = context.get("history", [])
        recent_history = raw_history[-(max_turns * 2):] if raw_history else []
        history_str = ""
        for msg in recent_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            history_str += f"{role.upper()}: {content}\n"

        if not results:
            system_prompt = settings.prompts["compose-system"]
            messages = [
                ("system", system_prompt),
                ("user", f"Context History:\n{history_str}\n\nUser Message: {user_message or '안녕하세요'}")
            ]
        else:
            results_str = "\n".join([
                f"Agent [{res.get('agent_key')}]: {res.get('payload', {}).get('answer')}"
                for res in results
            ])
            
            # A2UI 설정 확인
            a2ui_enabled = settings.supervisor_config.get("a2ui", {}).get("enabled", False)
            a2ui_hint = "\nNote: A2UI rendering is ENABLED. Keep your summary brief if the results already contain UI data." if a2ui_enabled else ""

            system_prompt = settings.prompts["compose-system"]
            compose_template = settings.prompts["compose-template"]
            user_prompt = compose_template.format(
                composeSystem="",
                userMessage=user_message,
                history=history_str,
                downstreamResults=results_str + a2ui_hint
            )
            messages = [
                ("system", system_prompt),
                ("user", user_prompt)
            ]

        # A2UI early check (Spring AI style)
        a2ui_enabled = settings.supervisor_config.get("a2ui", {}).get("enabled", False)
        if a2ui_enabled:
            for res in results:
                raw_payload = res.get("payload", {})
                raw_data = raw_payload.get("data", {})
                if raw_data and (raw_data.get("a2ui") or raw_data.get("protocol") == "a2ui"):
                    # FOUND A2UI! Yield it and return early
                    import json
                    a2ui_data = raw_data.get("a2ui") or raw_data
                    yield ("a2ui", json.dumps(a2ui_data))
                    yield ("chunk", "A2UI 화면을 통해 결과를 확인해 주세요.")
                    return

        try:
            async for chunk in self.llm.astream(messages):
                # 1. Check for explicit reasoning/thinking content
                reasoning_content = None
                
                # Check additional_kwargs (OpenAI o-series, Anthropic thinking, Groq)
                if hasattr(chunk, 'additional_kwargs'):
                    reasoning_content = (
                        chunk.additional_kwargs.get('reasoning_content') or
                        chunk.additional_kwargs.get('thinking') or
                        chunk.additional_kwargs.get('reasoning')
                    )
                
                # Check response_metadata (some LangChain versions)
                if not reasoning_content and hasattr(chunk, 'response_metadata'):
                    reasoning_content = (
                        chunk.response_metadata.get('reasoning_content') or
                        chunk.response_metadata.get('thinking')
                    )

                if reasoning_content:
                    yield ("reasoning", reasoning_content)
                    if not chunk.content:
                        continue
                
                # 2. Yield actual answer content
                if chunk.content:
                    yield ("chunk", chunk.content)
                    
        except Exception as e:
            yield ("chunk", f"응답 생성 오류: {str(e)}")
