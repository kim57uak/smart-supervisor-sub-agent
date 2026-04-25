# 16. Reference Links

Updated: 2026-04-25

## Python Runtime

- https://docs.python.org/3.11/
- https://docs.python.org/3.12/

## FastAPI / Pydantic

- https://fastapi.tiangolo.com/
- https://docs.pydantic.dev/latest/

## LangChain / LangGraph

- https://docs.langchain.com/oss/python/langchain/overview
- https://docs.langchain.com/oss/python/langgraph/overview
- https://docs.langchain.com/oss/python/concepts/products

## OpenAI / Google GenAI

- https://platform.openai.com/docs/api-reference/responses
- https://platform.openai.com/docs/guides/agents-sdk
- https://googleapis.github.io/python-genai/

## A2A

- https://github.com/a2aproject/A2A
- https://a2a-protocol.org/

## Internal References

- [13-implementation-roadmap.md](/Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/a2a-host_agent-architecture/13-implementation-roadmap.md)
- [17-supervisor-package-class-spec.md](/Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/a2a-host_agent-architecture/17-supervisor-package-class-spec.md)
- [21-a2a-supervisor-yml-recommended-structure.md](/Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/a2a-host_agent-architecture/21-a2a-supervisor-yml-recommended-structure.md)
- [26-supervisor-entry-contract-and-runtime-flow.md](/Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/a2a-host_agent-architecture/26-supervisor-entry-contract-and-runtime-flow.md)
- [27-supervisor-hitl-swarm-handoff-architecture.md](/Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/a2a-host_agent-architecture/27-supervisor-hitl-swarm-handoff-architecture.md)
- [28-supervisor-a2ui-architecture-and-operating-model.md](/Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/a2a-host_agent-architecture/28-supervisor-a2ui-architecture-and-operating-model.md)
- [29-supervisor-security-and-reliability-model.md](/Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/a2a-host_agent-architecture/29-supervisor-security-and-reliability-model.md)
- [30-supervisor-responsibility-separation-guide.md](/Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/a2a-host_agent-architecture/30-supervisor-responsibility-separation-guide.md)

## 2026-04-25 정합성 메모

- 본 문서는 `25`~`30` 문서 기준으로 현재 supervisor architecture reference set을 구성한다.
- 이번 차례 구현 스코프는 `APPROVE`, `CANCEL`만 포함하며 `REVISE`는 다음 단계로 이관한다.
- 상품/예약/주문 등 데이터 생성·변경(create/update/delete) 요청은 리스크 점수와 무관하게 HITL 강제 정책을 적용한다.
- A2A 계약은 `legacy + v1.0`을 모두 충족하는 호환 모드로 유지한다.
- handoff 설계/가드레일 기준은 `27`, 책임 경계는 `30`을 우선 참조한다.
