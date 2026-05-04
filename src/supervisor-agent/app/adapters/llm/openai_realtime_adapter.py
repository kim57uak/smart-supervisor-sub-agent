import asyncio
import json
import base64
import websockets
import structlog
from typing import AsyncIterator, Optional

from app.adapters.llm.voice_adapter_interface import VoiceAdapter
from app.core.config import settings

logger = structlog.get_logger(__name__)

class OpenAiRealtimeAdapter(VoiceAdapter):
    """
    OpenAI Realtime API(v1)를 사용한 실시간 음성-텍스트 변환(STT) 어댑터.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.openai_api_key
        self.model = settings.openai_realtime_model
        self.url = f"{settings.openai_realtime_url}?model={self.model}"
        self._ws = None

    async def connect(self):
        """OpenAI Realtime WebSocket 연결 수립 및 초기 세션 설정."""
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not configured")
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }
        
        # Rationale (Why): Support for both websockets <16.0 (extra_headers) and >=16.0 (additional_headers)
        try:
            logger.info("openai_realtime_connecting", url=self.url)
            self._ws = await websockets.connect(
                self.url, 
                additional_headers=headers,
                close_timeout=10
            )
        except TypeError as te:
            if "additional_headers" in str(te) or "unexpected keyword argument" in str(te):
                logger.info("falling_back_to_extra_headers")
                self._ws = await websockets.connect(
                    self.url, 
                    extra_headers=headers,
                    close_timeout=10
                )
            else:
                raise
        except Exception as e:
            logger.error("openai_realtime_connection_failed", error=str(e))
            raise

        logger.info("openai_realtime_connected", model=self.model)
        await self._update_session()

    async def _update_session(self):
        """세션 설정을 업데이트하여 STT 성능 최적화."""
        # Rationale (Why): Use prompts.yml for consistency and easy refactoring
        stt_instructions = settings.prompts.get("stt-system")
        
        session_update = {
            "type": "session.update",
            "session": {
                "modalities": ["text"],
                "instructions": stt_instructions,
                "input_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": settings.openai_realtime_stt_model
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.4, 
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 400 # Rationale (Why): Reduced from 600ms for faster auto-response.
                }
            }
        }
        await self._ws.send(json.dumps(session_update))

    async def send_audio(self, audio_data: bytes):
        """브라우저에서 받은 PCM16 바이너리 데이터를 OpenAI로 전송."""
        if not self._ws:
            return

        try:
            audio_event = {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(audio_data).decode("utf-8")
            }
            await self._ws.send(json.dumps(audio_event))
            
            # Rationale (Why): Confirming the flow of raw bytes to OpenAI
            # We use a simple counter to avoid excessive logging
            if not hasattr(self, '_send_count'): self._send_count = 0
            self._send_count += 1
            if self._send_count % 50 == 0:
                logger.info("openai_audio_sent", bytes=len(audio_data), total_chunks=self._send_count)
        except Exception as e:
            logger.error("openai_send_audio_failed", error=str(e))

    async def commit(self):
        """현재까지의 오디오 버퍼를 강제로 확정하고 응답(STT)을 생성하도록 트리거."""
        if not self._ws:
            return
        try:
            logger.info("openai_manual_commit_requested")
            # 1. 오디오 버퍼 커밋
            await self._ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
            # 2. 응답 생성 트리거 (STT 이벤트를 유도하기 위함)
            await self._ws.send(json.dumps({"type": "response.create"}))
        except Exception as e:
            logger.error("openai_commit_failed", error=str(e))

    async def listen(self) -> AsyncIterator[dict]:
        """OpenAI로부터 오는 이벤트를 구독하여 실시간 텍스트 데이터 추출."""
        if not self._ws:
            return

        try:
            async for message in self._ws:
                event = json.loads(message)
                event_type = event.get("type")

                # Rationale (Why): In STT-only mode, we primarily listen to input_audio_transcription.completed
                # which is triggered by the Whisper model on the user's input.
                if event_type == "conversation.item.input_audio_transcription.completed":
                    transcript = event.get("transcript", "")
                    if transcript.strip():
                        logger.info("openai_input_transcript_completed", text=transcript)
                        yield {"type": "final_transcript", "text": transcript}

                # Fallback: If the model is responding with text (as requested in instructions)
                elif event_type == "response.text.delta":
                    # Rationale (Why): This provides real-time visual feedback as the model "echoes" the speech.
                    yield {"type": "transcript", "text": event.get("delta", "")}
                
                elif event_type == "response.text.done":
                    # Rationale (Why): We ignore this for final_transcript to prioritize the Whisper model's 
                    # direct transcription, preventing the LLM's potential "answers" from being submitted.
                    logger.debug("openai_response_text_done_ignored_in_favor_of_input_transcription")
                    pass

                # Original audio transcript events (only relevant if modality includes audio)
                elif event_type == "response.audio_transcript.delta":
                    yield {"type": "transcript", "text": event.get("delta", "")}
                
                elif event_type == "response.audio_transcript.done":
                    transcript = event.get("transcript", "")
                    if transcript.strip():
                        logger.info("openai_audio_transcript_done", text=transcript)
                        yield {"type": "final_transcript", "text": transcript}

                elif event_type == "error":
                    logger.error("openai_realtime_error", error=event.get("error"))
                    yield {"type": "error", "message": event.get("error", {}).get("message")}
                
                # Debug logging for other events if needed
                elif event_type not in ["input_audio_buffer.speech_started", "input_audio_buffer.speech_stopped"]:
                    logger.debug("openai_event_received", type=event_type)

        except websockets.exceptions.ConnectionClosed:
            logger.info("openai_realtime_connection_closed")
        except Exception as e:
            logger.error("openai_realtime_listen_failed", error=str(e))
            yield {"type": "error", "message": str(e)}

    async def close(self):
        """연결 종료."""
        if self._ws:
            try:
                await self._ws.close()
            except:
                pass
            self._ws = None
