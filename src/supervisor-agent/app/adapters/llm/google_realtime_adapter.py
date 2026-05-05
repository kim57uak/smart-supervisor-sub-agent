import asyncio
import json
import base64
import websockets
import structlog
from typing import AsyncIterator, Optional

from app.adapters.llm.voice_adapter_interface import VoiceAdapter
from app.core.config import settings

logger = structlog.get_logger(__name__)

class GoogleRealtimeAdapter(VoiceAdapter):
    """
    Google Gemini Multimodal Live API를 사용한 실시간 음성-텍스트 변환(STT) 어댑터.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.google_api_key
        self.model = f"models/{settings.google_realtime_model}"
        self.url = f"{settings.google_realtime_url}?key={self.api_key}"
        self._ws = None

    async def connect(self):
        """Gemini Live WebSocket 연결 수립 및 초기 세션 설정."""
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is not configured")
            
        try:
            logger.info("google_realtime_connecting", url=self.url)
            self._ws = await websockets.connect(self.url)
            logger.info("google_realtime_connected", model=self.model)
            
            # 1. Setup message 전송 (필수)
            await self._send_setup()
            
            # 2. Setup 완료 대기 (중요: 완료 전에 데이터를 보내면 1011 에러 발생 가능)
            msg = await self._ws.recv()
            setup_data = json.loads(msg)
            if "setupComplete" in setup_data:
                logger.info("google_realtime_setup_complete")
            else:
                logger.error("google_setup_failed", data=setup_data)
                raise ValueError(f"Gemini Live setup failed: {setup_data}")

        except Exception as e:
            logger.error("google_realtime_connection_failed", error=str(e))
            raise

    async def _send_setup(self):
        """초기 세션 설정을 위한 Setup 메시지 전송."""
        stt_instructions = settings.prompts.get("stt-system")
        
        setup_msg = {
            "setup": {
                "model": self.model,
                "generation_config": {
                    "response_modalities": ["AUDIO"]
                },
                "system_instruction": {
                    "parts": [{"text": stt_instructions}]
                },
                "input_audio_transcription": {},
                "output_audio_transcription": {}
            }
        }
        await self._ws.send(json.dumps(setup_msg))
        logger.info("google_realtime_setup_sent")

    async def send_audio(self, audio_data: bytes):
        """브라우저에서 받은 PCM16 데이터를 Gemini로 전송 (16kHz 기준)."""
        if not self._ws:
            return

        try:
            # Rationale (Why): 최신 Gemini Live API는 'media_chunks' 대신 'audio' 필드를 직접 사용함 (Deprecated 대응)
            audio_msg = {
                "realtime_input": {
                    "audio": {
                        "mime_type": "audio/pcm;rate=24000",
                        "data": base64.b64encode(audio_data).decode("utf-8")
                    }
                }
            }
            await self._ws.send(json.dumps(audio_msg))
        except Exception as e:
            logger.error("google_send_audio_failed", error=str(e))

    async def commit(self):
        """
        현재까지의 입력을 확정하고 모델 응답을 트리거.
        """
        if not self._ws:
            return
        try:
            logger.info("google_manual_commit_requested")
            # Rationale (Why): 공식 매뉴얼에 따른 'client_content' 및 'turn_complete' 신호 전송
            commit_msg = {
                "client_content": {
                    "turns": [],
                    "turn_complete": True
                }
            }
            await self._ws.send(json.dumps(commit_msg))
        except Exception as e:
            logger.error("google_commit_failed", error=str(e))

    async def listen(self) -> AsyncIterator[dict]:
        """Gemini로부터 오는 이벤트를 구독하여 실시간 텍스트 데이터 추출."""
        if not self._ws:
            return

        user_text_buffer = ""
        try:
            async for message in self._ws:
                data = json.loads(message)
                
                # 1. 사용자의 음성 입력 전사 처리 (STT 역할)
                # API 버전에 따라 inputTranscription이 최상위에 올 수도 있고 serverContent 내부에 올 수도 있음
                transcription_data = None
                if "inputTranscription" in data:
                    transcription_data = data["inputTranscription"]
                elif "serverContent" in data and "inputTranscription" in data["serverContent"]:
                    transcription_data = data["serverContent"]["inputTranscription"]
                
                if transcription_data:
                    text = transcription_data.get("text") or transcription_data.get("data") or ""
                    if text:
                        user_text_buffer = text
                        logger.debug("google_user_transcript_delta", text=text)
                        yield {"type": "transcript", "text": text}
                
                # 2. 모델의 응답 처리 (결과 출력 역할)
                if "serverContent" in data:
                    content = data["serverContent"]
                    
                    if "modelTurn" in content:
                        if user_text_buffer:
                            logger.info("google_user_turn_finished", final_text=user_text_buffer)
                            yield {"type": "final_transcript", "text": user_text_buffer}
                            user_text_buffer = "" # 전송 후 버퍼 초기화

                        parts = content["modelTurn"].get("parts", [])
                        for part in parts:
                            if "text" in part:
                                text = part["text"]
                                yield {"type": "transcript", "text": text}
                    
                    # turnComplete 확인
                    if content.get("turnComplete"):
                        logger.info("google_turn_complete_received")
                        if user_text_buffer:
                            yield {"type": "final_transcript", "text": user_text_buffer}
                            user_text_buffer = ""
                        yield {"type": "final_transcript", "text": "", "role": "assistant"}

                if "error" in data:
                    logger.error("google_realtime_error", error=data["error"])
                    yield {"type": "error", "message": data["error"].get("message")}

        except websockets.exceptions.ConnectionClosed:
            logger.info("google_realtime_connection_closed")
        except Exception as e:
            logger.error("google_realtime_listen_failed", error=str(e))
            yield {"type": "error", "message": str(e)}

    async def close(self):
        """연결 종료."""
        if self._ws:
            try:
                await self._ws.close()
            except:
                pass
            self._ws = None
