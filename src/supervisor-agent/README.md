# 🧠 Smart Supervisor Agent (Enterprise Orchestrator)

## 🎯 개요 (Overview)
본 프로젝트는 **A2A (Agent-to-Agent)** 생태계의 중앙 관제탑 역할을 수행하는 **슈퍼바이저 에이전트**입니다. 복잡한 사용자 요청을 분석하여 실행 계획(Planning)을 수립하고, 적절한 서브에이전트에게 업무를 할당하며, 전체 실행 과정을 조율합니다.

---

## 👥 대상 사용자 및 개발자 (Target Audience)

### 👤 일반 사용자 (User)
- **A2UI (Agentic UI)**를 통해 복잡한 작업을 자연어로 지시할 수 있습니다.
- 작업의 진행 상태를 실시간으로 모니터링하고, 필요한 경우 중간 승인(HITL)을 통해 실행 방향을 결정할 수 있습니다.
- 모든 작업 이력과 결과를 대시보드에서 한눈에 확인 가능합니다.

### 💻 개발자 (Developer)
- **LangGraph**를 사용하여 복잡한 에이전트 워크플로우를 커스터마이징할 수 있습니다.
- 새로운 서브에이전트 탐색 로직이나 실행 일관성 정책을 정의할 수 있습니다.
- Redis 기반의 분산 아키텍처를 활용해 높은 가용성을 가진 시스템을 구축할 수 있습니다.

---

## 🎯 주요 아키텍처 및 특징 (Core Architecture)

### 1. Enterprise Reliability (Doc 01)
- **Decoupled Background Worker**: API 서버와 실행 로직이 `Redis Task Queue`를 통해 물리적으로 분리되었습니다. (`worker.py`)
- **Reliable Queue Pattern**: `BRPOPLPUSH` 기반의 At-Least-Once 전달 보장 로직을 적용하여 워커 장애 시에도 작업 유실이 없습니다.
- **Graceful Shutdown**: `SIGTERM` 감지 시 현재 진행 중인 에이전트 실행을 완료한 후 안전하게 종료됩니다.

### 2. State Integrity & Concurrency (Doc 29)
- **Global CAS Transition**: 모든 상태 전이(`WAITING_REVIEW`, `RUNNING`, `COMPLETED`, `CANCELED`)에 Redis `WATCH/MULTI` 기반의 Compare-And-Set 로직이 적용되어 분산 환경에서의 경합을 완벽히 차단합니다.
- **Version Control**: 모든 Task 레코드는 `version` 필드를 통해 변경 이력을 관리하며, 충돌 시 `STATE_VERSION_MISMATCH`를 반환합니다.

### 3. Review Security & Integrity (Doc 31)
- **Frozen Plan Hash Verification**: 승인 시점에 `FrozenExecutionPlan`의 해시값을 재계산하여 계획 변조 여부를 7단계 정밀 검증합니다.
- **Drift Policy Enforcement**: 계획이 수립된 시점과 승인된 시점 사이의 환경 변화(Agent 차단, 메서드 은퇴 등)를 감지하여 실행을 차단합니다.

### 4. Self-healing Discovery (A2A Standard)
- **Canonical Path Alignment**: 모든 서브에이전트 탐색은 `/.well-known/agent-card.json` 표준 경로를 통해 수행됩니다.
- **Lifespan Discovery**: 슈퍼바이저 기동 시 `asynccontextmanager`를 통해 서브에이전트 정보를 선제적으로 로드합니다.
- **Lazy Fallback**: 기동 시점에 서브에이전트가 오프라인이더라도 재탐색을 시도하는 자가 치유 로직이 적용되어 있습니다.

---

## 🏗 시스템 컴포넌트

1. **API Tier (Producer)**: 계획 수립 및 큐 삽입
2. **Worker Tier (Consumer)**: 에이전트 그래프 실행 및 이벤트 스트리밍
3. **A2UI (Dashboard)**: `app/static/index.html`을 통한 웹 기반 제어

---

## 🚀 시작하기 (Getting Started)

### 사전 요구사항
- **Redis Server** 가동 필수
- **Python 3.11** 환경 권장 (3.13 환경에서 일부 UI 호환성 이슈 발생 가능)
- **Environment Variables**: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` 등 필수 설정

### 실행 방법
```bash
# API 서버 및 워커 동시 기동
rtk ./start.sh

# 개별 실행 시
rtk uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers <API_WORKERS>
rtk python worker.py --concurrency <WORKER_COUNT>
```

### 📊 에이전트 실행 시각화 (Burr UI)
Burr 엔진을 사용하는 경우, 다음 명령어로 에이전트의 상태 머신과 실행 이력을 실시간으로 모니터링할 수 있습니다.
```bash
# Burr UI 서버 기동 (기본 포트: 7241)
rtk burr
```
접속 주소: [http://localhost:7241](http://localhost:7241)

---

## 📈 스케일링 가이드 (Scaling Guide)

시스템 리소스(CPU Core)에 따른 최적의 워커 배치 권장안입니다. 본 시스템은 LLM I/O 바운드 작업이 많으므로 코어 수보다 많은 워커를 할당하는 것이 효율적입니다.

| CPU 코어 | API 워커 (Uvicorn) | 백그라운드 워커 (`worker.py`) | 추천 시나리오 |
| :--- | :--- | :--- | :--- |
| **4 Core** | 2 - 4 | 8 - 12 | 소규모 팀 협업, 개인 비서용 |
| **8 Core** | 4 - 8 | 16 - 24 | 중급 규모 서비스, 10개 이상의 서브에이전트 조율 |
| **16 Core** | 8 - 16 | 32 - 64 | 엔터프라이즈급 부하, 대량의 실시간 플래닝 처리 |

> [!TIP]
> **I/O 대기 시간 활용**: 에이전트는 LLM 응답을 기다리는 시간이 길기 때문에, 백그라운드 워커 수를 코어 수의 2~4배로 설정하는 것이 CPU 사용률을 극대화할 수 있는 방법입니다.

---

## ✅ 아키텍처 검증 테스트
```bash
cd src/supervisor-agent
export PYTHONPATH=$PYTHONPATH:.
rtk pytest tests/integration_test.py
```

---

## ⚠️ 주의사항 (Precautions)

> [!IMPORTANT]
> **데이터 영속성**: 모든 작업 상태는 Redis에 저장됩니다. Redis 데이터 초기화 시 진행 중인 모든 세션 정보가 유실되므로 주의하십시오.

> [!WARNING]
> **Planning 비용**: 복잡한 요청에 대해 수립된 실행 계획은 LLM 토큰을 소모합니다. 불필요하게 긴 요청은 비용 증가의 원인이 될 수 있습니다.

> [!CAUTION]
> **보안 정책**: `supervisor.yml`에 설정된 `allow_list`를 통해 서브에이전트의 접근 권한을 엄격히 관리하세요. 권한이 없는 서브에이전트 호출은 시스템에 의해 차단됩니다.

---

## 🛠 개발 가이드 (Developer Guide)

### 주요 모듈 설명
- `app/adapters/orchestration/`: LangGraph 팩토리 및 핸드오프 정책
- `app/application/execution/`: HITL 게이트 및 실행 일관성 코디네이터
- `app/infrastructure/llm/`: LLM 런타임 및 프롬프트 관리
- `app/static/`: A2UI 프론트엔드 자산

---
**Status**: 🟢 Architecture-Aligned (Zero-Gap)
**Last Verified**: 2026-04-27
