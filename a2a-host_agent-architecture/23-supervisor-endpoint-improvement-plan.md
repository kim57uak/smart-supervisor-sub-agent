# 23. Supervisor A2A Endpoint Improvement Plan

## Goal

- `supervisor_a2a_endpoint` 단일 진입점에서 JSON-RPC/A2A 계약을 안정적으로 처리한다.

## Plan

1. 입력 검증 강화
- method allowlist 검증
- params schema 검증
- `tasks/review/get`, `tasks/review/decide` 입력 스키마 추가
- 결정값은 `APPROVE/CANCEL`만 허용

2. 오류 일관화
- JSON-RPC error code 매핑 표준화
- 내부 예외 메시지 sanitize

3. 스트리밍 안정화
- `message/stream` chunk framing 규칙 고정
- 취소/타임아웃 시 종료 이벤트 규칙 통일

4. A2A 호환성 유지
- `legacy + v1.0` 메서드명을 모두 수용하고 enum 기반으로 정규화

5. Swarm 상태 연계
- review 조회/결정 응답에 swarm 상태 버전(`state_version`)을 포함해 동시성 충돌을 감지


---

## 2026-04-24 정합성 메모

- 본 문서는 `25`~`30` 문서 기준으로 현재 supervisor architecture 원칙을 상위 기준으로 따른다.
- 이번 차례 구현 스코프는 `APPROVE`, `CANCEL`만 포함하며 `REVISE`는 다음 단계로 이관한다.
- 상품/예약/주문 등 데이터 생성·변경(create/update/delete) 요청은 리스크 점수와 무관하게 HITL 강제 정책을 적용한다.
- A2A 계약은 `legacy` + `v1.0`을 모두 충족하는 호환 모드로 유지한다(메서드 enum 기반 관리).
- 사용자 추가정보 수집(이름/전화/이메일)은 향후 계획으로 분리하며, 입력 UX는 자연어/콤마 텍스트 수용 후 내부 구조화 원칙을 따른다.
