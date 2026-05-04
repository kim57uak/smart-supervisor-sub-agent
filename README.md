# 🌌 Smart Supervisor & A2A Multi-Agent System

![Architecture Overview](https://img.shields.io/badge/Architecture-A2A%20Multi--Agent-blue)
![Python](https://img.shields.io/badge/Python-3.11-green)
![Redis](https://img.shields.io/badge/Queue-Redis%20Reliable-red)

본 프로젝트는 초정밀 **A2A (Agent-to-Agent)** 오케스트레이션 엔진인 **Smart Supervisor**와 실제 업무를 수행하는 **Sub-Agent**로 구성된 엔터프라이즈급 멀티 에이전트 시스템입니다.

---

## 🚀 주요 특징 (Key Features)

### 1. 🎙️ 통합 음성 오케스트레이션 (Voice Pattern 3)
- **Server-Side Trigger**: 음성 인식이 완료되면 브라우저를 거치지 않고 서버 사이드에서 즉시 에이전트 작업을 실행합니다.
- **Real-time Streaming**: OpenAI Realtime API를 통해 텍스트 전사(STT)와 에이전트 추론 과정을 실시간으로 스트리밍합니다.
- **Zero-Latency Experience**: 인식 완료와 동시에 실행이 시작되는 혁신적인 사용자 경험을 제공합니다.

### 2. 🛡️ 엔터프라이즈급 신뢰성 (Reliability)
- **Reliable Queue**: Redis `BRPOPLPUSH` 패턴을 사용하여 At-Least-Once 작업 전달을 보장합니다.
- **Stability Tuning**: 롱 폴링(Long Polling) 대기를 위해 Redis 소켓 타임아웃을 20초로 최적화했습니다.
- **Atomic State Control**: Redis CAS(Compare-And-Set)를 통해 분산 환경에서도 작업 상태의 정합성을 유지합니다.

### 3. 📋 지능형 계획 및 관리 (Intelligent Planning)
- **Centralized Prompts**: `prompts.yml`을 통해 모든 에이전트의 지침과 STT 설정을 중앙 관리합니다.
- **HITL (Human-In-The-Loop)**: 중요 작업 실행 전 사용자 승인을 대기하는 정책 게이트를 지원합니다.
- **Circuit Breaker**: 장애가 발생한 에이전트 호출을 자동으로 차단하여 시스템 전체의 안정성을 확보합니다.

---

## 📂 프로젝트 구조 (Project Structure)

- [**`src/supervisor-agent/`**](file:///Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/src/supervisor-agent/README.md): 시스템의 중앙 관제 및 오케스트레이션을 담당하는 마스터 에이전트.
- [**`src/sub-agent/`**](file:///Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/src/sub-agent/README.md): MCP 도구와 연동하여 실질적인 업무를 수행하는 실행형 에이전트.
- [**`a2a-host_agent-architecture/`**](file:///Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/a2a-host_agent-architecture/): 시스템의 상세 시퀀스 및 아키텍처 문서군.
- [**`DETAILED_FUNCTION_FLOW.md`**](file:///Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/DETAILED_FUNCTION_FLOW.md): UI부터 DB까지의 모든 함수 단위 실행 흐름도.

---

## 🛠️ 시작하기 (Quick Start)

### 1. 가상환경 및 의존성 구축
모든 서비스는 프로젝트 루트의 통합 가상환경(`.venv`)에서 실행하는 것을 권장합니다. **Supervisor**의 의존성을 기준으로 환경을 구축합니다.

```bash
# 1. 가상환경 생성 (프로젝트 루트에서 실행)
python3 -m venv .venv

# 2. 가상환경 활성화
source .venv/bin/activate

# 3. 슈퍼바이저 기준 의존성 설치 (루트에서 실행)
pip install -r src/supervisor-agent/requirements.txt
```

### 2. 서비스 기동
```bash
# Supervisor 및 Sub-Agent 통합 실행 (start_all.sh 내부에서 venv 자동 참조)
./start_all.sh
```

### 3. 기능 검증
```bash
# 전체 파이프라인 E2E 검증
python verify_session_id_e2e.py
```

---

## 📚 관련 문서 (Documentation)
- **아키텍처 가이드**: [AGENT.md](file:///Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/AGENT.md)
- **음성 인식 시퀀스**: [33-voice-integrated-orchestration-sequence.puml](file:///Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/a2a-host_agent-architecture/33-voice-integrated-orchestration-sequence.puml)
- **구현 상세 명세**: [DETAILED_FUNCTION_FLOW.md](file:///Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/DETAILED_FUNCTION_FLOW.md)

---
**Last Updated**: 2026-05-04
**Current Version**: v2.5 (Voice Integrated Standard)
