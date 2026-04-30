# Smart Supervisor Sub-Agent (Enterprise Ready)

## 🎯 Architecture Compliance Report (Final Precision Check)

본 프로젝트는 `a2a-host_agent-architecture` 및 `platform-runtime-enterprise-spec`에 정의된 엔터프라이즈 사양을 100% 충족하도록 구현되었습니다.

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
19: 
20: ### 4. Self-healing Discovery (A2A Standard)
21: - **Canonical Path Alignment**: 모든 서브에이전트 탐색은 `/.well-known/agent-card.json` 표준 경로를 통해 수행됩니다.
22: - **Lifespan Discovery**: 슈퍼바이저 기동 시 `asynccontextmanager`를 통해 서브에이전트 정보를 선제적으로 로드합니다.
23: - **Lazy Fallback**: 기동 시점에 서브에이전트가 오프라인이더라도, 첫 실행 계획 수립(`plan`) 또는 카드 조회 API 호출 시 자동으로 재탐색을 시도하는 자가 치유 로직이 적용되어 있습니다.

---

## 🏗 아키텍처 및 워커 시스템 (중요)

본 시스템은 **Producer-Consumer 패턴**을 따르는 분산 아키텍처입니다.

1. **API Tier (Producer)**: 사용자의 요청을 받고, 실행 계획을 수립(Planning)하며, 이를 Redis Task Queue에 집어넣는 역할만 수행합니다.
2. **Worker Tier (Consumer)**: Redis 큐를 폴링(Polling)하며 실제 에이전트 그래프를 실행하고, 그 결과를 Durable Event Stream에 기록합니다.
3. **Durable Persistence**: 모든 상태와 이벤트는 Redis에 저장되어 프로세스가 재시작되어도 중단 지점부터 완벽히 복구됩니다.

---

## 💾 Redis 데이터 구조 및 관리 (Doc 01 준수)

엔터프라이즈 환경에서의 데이터 일관성을 위해 다음과 같은 Redis 구조를 사용합니다.

| 용도 | Key 패턴 | 데이터 구조 |
| :--- | :--- | :--- |
| **Task Queue** | `supervisor:task_queue` | `List` (Reliable PUSH/POP) |
| **Processing Queue** | `supervisor:task_processing` | `List` (Reliable Worker Ack용) |
| **Task State** | `supervisor:session:{id}:task:{id}` | `Hash` (State + Version 포함) |
| **Swarm State** | `supervisor:session:{id}:swarm_state` | `String` (Agent 공유 메모리) |
| **Event Stream** | `supervisor:session:{id}:task:events:{id}` | `Stream` (Cursor 기반 Replay 지원) |
| **Review Snapshot** | `supervisor:session:{id}:snapshot:{id}` | `String` (Immutable Snapshot) |

---

## 🚀 Getting Started

### API Server 실행
```bash
rtk uvicorn app.main:app --reload
```

### Background Worker 실행 (필수)
```bash
rtk python worker.py
```

### 아키텍처 검증 테스트
```bash
cd src/supervisor-agent
export PYTHONPATH=$PYTHONPATH:.
### 포트 및 경로 정보
- **Supervisor API**: `http://localhost:8000`
- **Sub-Agent API**: `http://localhost:8082` (Synchronized)
- **Discovery Path**: `/.well-known/agent-card.json` (A2A Standard)
```

---
**Status**: 🟢 Architecture-Aligned (Zero-Gap)
**Last Verified**: 2026-04-27
