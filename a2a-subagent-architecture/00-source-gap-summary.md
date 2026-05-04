# 00. Source Gap Summary

Updated: 2026-05-04 (Architecture Sync Completed)

이 폴더 문서는 이제 `Python 3.11+ + FastAPI + LangChain + LangGraph/Burr + A2A + Redis + MCP adapter runtime` 기준의 **엔터프라이즈급 구현 설계 문서**다.

## Enterprise Alignment

- **Hexagonal Architecture**: `ports`와 `adapters`를 통한 기술/도메인 분리 (Burr/LangGraph 멀티 엔진 지원).
- **CQRS**: `execution`, `persistence`, `read` 계층의 분리.
- **Decoupled Worker**: API와 무거운 실행 로직(Worker)의 분리.
- **Supervisor Consistency**: `src/supervisor-agent`의 구조 및 명명 규칙을 서브 에이전트에도 동일하게 적용하여 일관성 확보.

## Sync Status (2026-05-04)

- **Naming Sync**: 소스 코드의 실제 클래스명 및 파일 구조를 문서(Doc 16, 20)에 반영 완료.
- **Engine Extension**: LangGraph 외에 Burr 오케스트레이션 엔진 사양 추가.
- **Model Fidelity**: `AgentTask`의 `state_version`, `AiChatChunk` 규격 등 소스 코드 기반 최신화 완료.

## Replace

- 기존 4계층(`endpoint -> application -> domain -> infrastructure`) 구조를 **Hexagonal + CQRS** 구조로 대체.
- 모든 단일 서비스(`agent_orchestrator`) 중심 설계를 `execution` 서비스군으로 세분화.
- 동기적 실행 흐름을 Redis Queue 기반 비동기 워커 흐름으로 전환.

## Current Rule

- 문서의 정본 기준은 Python runtime 및 Hexagonal 아키텍처다.
- 내부 naming은 `snake_case`를 엄격히 준수한다.
- Supervisor 아키텍처와 상충되는 부분이 있을 경우 Supervisor를 정본으로 간주한다.
