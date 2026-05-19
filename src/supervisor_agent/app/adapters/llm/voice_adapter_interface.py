from abc import ABC, abstractmethod
from typing import AsyncIterator

class VoiceAdapter(ABC):
    """
    실시간 음성 인식을 위한 공통 어댑터 인터페이스.
    OpenAI Realtime, Gemini Live 등 다양한 멀티모달 서비스로의 확장을 고려한 추상화 계층입니다.
    """
    
    @abstractmethod
    async def connect(self):
        """서비스와의 WebSocket 연결을 수립합니다."""
        pass

    @abstractmethod
    async def send_audio(self, audio_data: bytes):
        """바이너리 오디오 데이터를 서비스로 전송합니다."""
        pass

    @abstractmethod
    async def listen(self) -> AsyncIterator[dict]:
        """서비스로부터 오는 실시간 텍스트 및 상태 이벤트를 수신합니다."""
        pass

    @abstractmethod
    async def commit(self):
        """현재까지의 오디오를 확정하고 응답을 트리거합니다."""
        pass

    @abstractmethod
    async def close(self):
        """연결을 안전하게 종료합니다."""
        pass
