# 22. Architecture Document Index

Updated: 2026-04-28 (Implementation Refined)

## Purpose

본 문서는 `smart-supervisor` 프로젝트의 엔터프라이즈급 아키텍처 문서 세트 인덱스다. 
실제 소스 코드는 **비동기 큐잉 모델(Decoupled Worker)**과 **CQRS** 패턴을 따르며, 아래 순서에 따라 읽는 것을 권장한다.

## Recommended Reading Order

### 1. 시스템 및 구조 (Core Foundation)
- `01` System Context (전체 연결도)
- `02` Package Policy (폴더 및 계층 정책)
- `03` Component Architecture (컴포넌트 관계도)
- `17` Package / Class Spec (실제 클래스 명세)

### 2. 실행 흐름 및 상태 (Behavior & Flow)
- `11` State Machine (태스크 수명주기 및 런타임 상태)
- `19` Runtime Sequence (비동기 워커 및 멱등성 흐름)
- `07` Streaming Sequence (분리된 이벤트 스트리밍 방식)
- `08` Exception Handling (표준 에러 매핑 및 복구)

### 3. 보안 및 운영 정책 (Governance & Policy)
- `09` Security & Integrity Model (해시 검증 및 무결성 감사)
- `14` Dependency Policy (레이어 간 의존성 규칙)
- `21` Settings Structure (YAML 설정 구조)
- `12` Technology Decision (최종 기술 스택 결정 사유)

### 4. 구현 및 데이터 명세 (Detailed Specs)
- `15` Usecase Mapping (기능별 런타임 매핑)
- `18` Domain Pseudocode (핵심 비즈니스 로직 의사코드)
- `31` FrozenExecutionPlan Schema (동결 계획 데이터 규격)

## Maintenance Rule

- 새 문서를 추가하거나 명칭을 변경할 때는 본 인덱스를 반드시 업데이트한다.
- 모든 문서는 **Karpathy Guidelines**의 Simplicity와 Surgical Change 원칙을 문서 레벨에서도 준수한다.
