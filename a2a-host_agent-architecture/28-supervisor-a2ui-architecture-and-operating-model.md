# 28. Supervisor A2UI Architecture And Operating Model

Updated: 2026-04-25
Current baseline: `src/app`

## Purpose

본 문서는 supervisor의 A2UI 역할, 생성 시점, 실패 처리, 운영 모델을 Python runtime 기준으로 정리한다.

## Positioning

A2UI는 supervisor의 기본 응답을 대체하는 기능이 아니라, 사용자의 의사결정을 더 잘 돕기 위한 보조 표현 계층이다.

원칙:

- text response는 항상 기본값으로 유지한다.
- A2UI는 선택적으로 추가된다.
- A2UI 실패가 supervisor 전체 응답 실패로 전파되면 안 된다.

## Two A2UI Phases

### 1. Pre-HITL A2UI

- downstream invoke보다 먼저 발생할 수 있다.
- waiting review나 execution 대신 먼저 응답을 종료할 수 있다.
- 데이터 변경을 직접 수행하지 않는다.

### 2. Post-Invoke Compose A2UI

- compose 결과의 일부로 생성된다.
- text `compose-result`와 함께 유지한다.
- raw payload를 그대로 노출하지 않고 정규화된 view model을 사용한다.

## Generic Onboarding Rule

supervisor의 기본 확장 경로는 아래다.

1. `supervisor.yml`에 downstream agent 등록
2. registry가 agent를 인식
3. agent card를 읽어 capability를 해석
4. planner/routing/invocation은 추가 코드 없이 동작

## Adapter Exception Rule

예외적으로 domain adapter를 허용하는 범위:

- downstream raw payload shape가 과도하게 다양해 generic normalization이 불안정한 경우
- 표준 field mapping만으로는 일정표, 예약 seed, 판매상품 생성 form 같은 UI를 안정적으로 만들기 어려운 경우

이 adapter는 optional presentation extension이어야 하며, 신규 agent 기본 등록 메커니즘이 되어서는 안 된다.

## Fallback Rules

A2UI 실패는 아래 중 하나로 수렴해야 한다.

- text response only
- text response + minimal metadata

금지 규칙:

- A2UI 실패 때문에 `compose-result`까지 같이 소실되는 구조
- 사용자에게 raw parser error를 노출하는 구조
- A2UI가 없으면 설명 가능한 답변도 못 주는 구조
