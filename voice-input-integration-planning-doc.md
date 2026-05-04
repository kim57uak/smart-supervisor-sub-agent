# GPT-4o mini Realtime 음성 통합 기획서 (최종)

## 요약
**OpenAI GPT-4o mini Realtime API**의 실시간 멀티모달 능력을 활용하여 **저지연 음성-텍스트 변환(STT)**을 구현합니다. 음성은 순수하게 편리한 **입력 수단**으로 사용되며, 변환된 텍스트는 기존의 Supervisor 아키텍처 흐름(A2A, 하위 에이전트 판단 등)을 그대로 따릅니다.

## 사용자 확정 사항
1. **모델**: `gpt-4o-mini-realtime-preview` 사용.
2. **방법**: OpenAI Realtime API (WebSocket)를 이용한 실시간 오디오 스트리밍 및 텍스트 변환.
3. **응답 형식**: 텍스트 전용 (LLM의 오디오 출력은 사용하지 않음).
4. **실행 로직**: 음성으로 변환된 텍스트는 기존 아키텍처와 동일하게 하위 에이전트(Sub-agent) 판단 및 실행 과정을 거침. (A2A 로직 유지)
5. **UI/UX**: 마이크 버튼 제공 및 음성 입력 중임을 나타내는 시각적 표시 영역(애니메이션 등) 추가.

## 솔루션 아키텍처

### 1. 실시간 음성 처리 경로 (Voice Path)
- **입력**: 클라이언트 브라우저에서 `MediaRecorder` API를 통해 오디오 데이터를 캡처하고 WebSocket으로 스트리밍합니다.
- **변환**: `OpenAiRealtimeAdapter`가 OpenAI Realtime API와 WebSocket 세션을 유지하며 오디오를 실시간으로 텍스트(Transcript)로 변환합니다.
- **트리거**: 음성 입력이 종료(VAD - Voice Activity Detection 또는 사용자 중단)되면, 최종 변환된 텍스트를 `SupervisorAgentService.execute_task`에 전달하여 기존 텍스트 대화와 동일한 로직을 수행합니다.

### 2. 백엔드 구성 요소
- **`VoiceStreamRouter`**: `/a2a/supervisor/voice/stream` WebSocket 엔드포인트를 처리합니다.
- **`OpenAiRealtimeAdapter`**: OpenAI Realtime API 세션 관리 및 실시간 텍스트 수신을 담당합니다.
- **`VoiceTranscriptionService`**: 오디오 세션을 관리하고 최종 텍스트가 완성되면 기존 서비스 레이어를 호출합니다.

### 3. 프론트엔드 구성 요소 및 UI 레이아웃
- **마이크 버튼**: 
    - 입력창(`textarea`) 바로 오른쪽, 전송 버튼 왼쪽에 배치.
    - 상태에 따라 아이콘 변경 (대기: 🎙️, 녹음 중: ⏹️ 또는 애니메이션).
- **실시간 음성 텍스트 표시 (Overlay)**:
    - 사용자가 말을 하면 실시간으로 변환되는 텍스트를 입력창 위에 반투명 레이어로 표시.
    - 최종 인식이 완료되면 해당 텍스트를 입력창에 삽입하거나 즉시 전송.
- **음성 파형 애니메이션**:
    - 마이크 활성화 시 상태 바(`status-progress`) 영역에 파동 형태의 애니메이션 효과 추가.

## 시스템 구성 요소 및 역할

| 구성 요소 | 역할 |
| :--- | :--- |
| `index.html` | 마이크 버튼 및 음성 시각화 UI 구현. |
| `VoiceStreamRouter` | 클라이언트 오디오 스트림 수신 및 OpenAI 연결. |
| `OpenAiRealtimeAdapter` | GPT-4o mini Realtime을 이용한 실시간 STT. |
| `SupervisorAgentService` | 변환된 텍스트를 받아 기존 오케스트레이션 수행. |

## 실행 계획
1. **UI 업데이트**: `index.html`에 마이크 버튼 및 음성 입력 UI 요소 추가 (반응형 디자인 적용).
2. **어댑터 구현**: `src/supervisor-agent/app/adapters/llm/openai_realtime_adapter.py` 작성.
3. **API 구현**: `src/supervisor-agent/app/api/supervisor.py`에 WebSocket 핸들러 추가.
4. **서비스 연동**: 음성 인식 완료 시 기존 `execute_task`를 호출하도록 연동.
5. **검증**: PC/모바일 브라우저에서 음성 입력 -> 실시간 텍스트 변환 -> 기존 아키텍처 기반 실행 확인.

### 4. 크로스 플랫폼 지원 (PC & Mobile)
- **반응형 레이아웃**: 모바일 화면(768px 이하)에서는 마이크 버튼과 전송 버튼의 크기를 터치 최적화하고, 하단 배치를 통해 한 손 조작성을 높입니다.
- **웹 표준 API**: `navigator.mediaDevices.getUserMedia`를 사용하여 Chrome, Safari(iOS), Edge 등 모든 표준 브라우저에서 별도 플러그인 없이 동작하게 합니다.
- **오디오 최적화**: 모바일의 가변적인 네트워크 대역폭을 고려하여 오디오 데이터를 효율적으로 인코딩(PCM16)하여 전송 지연을 최소화합니다.
- **보안 사항**: 마이크 권한은 HTTPS 환경에서만 허용되므로, 배포 시 SSL 적용이 필수임을 명시합니다.
