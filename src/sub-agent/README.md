# 🤖 Smart Sub-Agent (A2A & MCP Implementation)

## 🎯 개요 (Overview)
본 프로젝트는 **A2A (Agent-to-Agent)** 표준 프로토콜을 준수하고 **MCP (Model Context Protocol)**를 통해 실질적인 도구(Tools)와 데이터에 접근하는 실행형 에이전트입니다. 슈퍼바이저 에이전트의 지시를 받아 실제 업무를 수행하고 그 결과를 스트리밍으로 전달합니다.

---

## 👥 대상 사용자 및 개발자 (Target Audience)

### 👤 일반 사용자 (User)
- 슈퍼바이저 에이전트와 연결되어 동작하는 개별 기능 단위의 에이전트입니다.
- 직접적인 UI보다는 슈퍼바이저를 통해 작업을 수행하지만, 개별 에이전트의 상태와 로그를 통해 작업 진행 상황을 확인할 수 있습니다.

### 💻 개발자 (Developer)
- 신규 도구(Tools)를 추가하거나 MCP 서버와 연동하여 에이전트의 역량을 확장할 수 있습니다.
- A2A 규격에 따른 `agent-card.json` 노출 및 JSON-RPC 2.0 기반의 상호작용 로직을 관리합니다.

---

## 🏗 주요 아키텍처 (Architecture)

1. **A2A Protocol**: 슈퍼바이저와의 통신을 위한 표준 규격을 제공합니다 (`app/api/a2a.py`).
2. **MCP Adapters**: 외부 도구 및 데이터 소스와 통신하기 위한 프로토콜 어댑터입니다 (`app/adapters/mcp/`).
3. **Background Worker**: 긴 실행 시간이 필요한 작업을 Redis 큐를 통해 비동기로 처리합니다 (`worker.py`).
4. **Durable Streaming**: 작업 진행 상황을 실시간으로 슈퍼바이저에게 전달합니다.

---

## 🚀 시작하기 (Getting Started)

### 사전 요구사항
- **Python 3.11** 환경 권장 (3.13 환경에서 일부 UI 호환성 이슈 발생 가능)
- **Redis**: 작업 큐 및 상태 관리를 위해 필요합니다.
- **LLM API Key**: OpenAI 또는 Anthropic 등의 API 키가 필요합니다.

### 실행 방법
```bash
# 서버 기동
rtk ./start.sh

# 서버 중지
rtk ./stop.sh

# 개별 실행 시
rtk uvicorn app.main:app --host 0.0.0.0 --port 8082 --workers <API_WORKERS>
rtk python worker.py --concurrency <WORKER_COUNT>

# 정상 작동 확인
rtk ./verify_subagent.sh

### 📊 에이전트 실행 시각화 (Burr UI)
Burr 엔진을 사용하는 경우, 에이전트의 상태 전이 과정을 시각적으로 확인할 수 있습니다.
```bash
# Burr UI 서버 기동 (기본 포트: 7241)
rtk burr
```
접속 주소: [http://localhost:7241](http://localhost:7241)
```

---

## 📈 스케일링 가이드 (Scaling Guide)

서브에이전트의 역할과 사용 가능한 리소스에 따른 최적화 가이드입니다. 서브에이전트는 실제 도구(MCP Tools)를 실행하므로, 도구의 성격(I/O vs CPU)에 따라 조정이 필요합니다.

| CPU 코어 | API 워커 (Uvicorn) | 백그라운드 워커 (`worker.py`) | 추천 시나리오 |
| :--- | :--- | :--- | :--- |
| **4 Core** | 2 | 4 - 8 | 단순 정보 조회, 이메일 발송 등 가벼운 도구 |
| **8 Core** | 4 | 12 - 20 | 데이터 요약, 복합 문서 처리 등 I/O 바운드 도구 |
| **16 Core** | 8 | 24 - 48 | 대량의 파일 처리, 대규모 MCP 도구 셋 운영 |

> [!IMPORTANT]
> **병렬 실행 제한**: 특정 MCP 도구(예: 데이터베이스 쓰기)는 병렬 실행 시 경합이 발생할 수 있습니다. 이 경우 백그라운드 워커 수를 늘리기보다 워커 인스턴스를 분리하여 운영하는 것을 권장합니다.

---

## 🛠 개발 가이드 (Developer Guide)

### 폴더 구조
- `app/adapters/mcp/`: MCP 서버 연동 및 도구 레지스트리
- `app/application/execution/`: 에이전트 실행 로직 및 워커 서비스
- `app/domain/`: 도메인 모델 및 예외 정의
- `app/config/`: 프롬프트 및 설정 파일 (`prompts.yml`)

### 신규 도구 추가 방법
1. `app/adapters/mcp/mcp_tool_registry.py`에 새로운 도구 정의를 추가합니다.
2. `app/application/execution/executor.py`에서 도구 실행 로직을 구현합니다.
3. 슈퍼바이저 에이전트의 Planning 단계에서 해당 도구를 인식할 수 있도록 `prompts.yml`을 업데이트합니다.

---

## ⚠️ 주의사항 (Precautions)

> [!IMPORTANT]
> **Redis 연결 필수**: 본 시스템은 Redis 없이 동작하지 않습니다. 반드시 Redis 서버가 가동 중인지 확인하세요.

> [!WARNING]
> **MCP 서버 가용성**: 연동된 MCP 서버가 응답하지 않을 경우 도구 실행이 실패할 수 있습니다. `verify_subagent.sh`를 통해 연동 상태를 주기적으로 체크하세요.

> [!CAUTION]
> **환경 변수 보안**: `.env` 또는 시스템 환경 변수에 저장된 API 키가 유출되지 않도록 주의하세요. `app/core/config.py`에서 관리되는 설정값들을 확인하십시오.

---

## ✅ 검증 (Verification)
`rtk pytest src/sub-agent/tests/integration_test.py`를 실행하여 기본적인 A2A 통신 및 도구 실행 로직이 정상인지 확인할 수 있습니다.
