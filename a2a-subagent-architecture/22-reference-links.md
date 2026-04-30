# 22. Reference Links

Updated: 2026-04-25

## External References

- https://docs.langchain.com/
- https://langchain-ai.github.io/langgraph/
- https://github.com/a2aproject/A2A
- https://github.com/a2aproject/A2A/blob/main/docs/specification.md
- https://github.com/a2aproject/A2A/releases/tag/v1.0.0
- https://redis.io/docs/latest/
- https://fastapi.tiangolo.com/
- https://docs.pydantic.dev/

## A2A Version Notes

- 확인일: `2026-04-25`
- latest released protocol version은 `1.0.0`이다.
- canonical JSON-RPC method reference는 PascalCase(`SendMessage`, `SendStreamingMessage`, `GetTask`, `ListTasks`, `CancelTask`, `SubscribeToTask`)를 사용한다.
- canonical discovery path는 `/.well-known/agent-card.json`이다.
- 구버전 `v0.3.0`, `v0.2.6` specification은 slash style JSON-RPC methods(`message/send`, `message/stream`, `tasks/get`, `tasks/list`, `tasks/cancel`)를 사용한다.
- 구현은 current family를 기본으로 하고 legacy family는 inbound compatibility alias로만 유지한다.
- 내부 구현 필드명은 `snake_case`를 사용하고, 외부 계약 alias만 compatibility layer에서 매핑한다.

## MCP References

- [30. MCP Server Spec & Integration Mapping](file:///Users/dolpaks/Downloads/project/smart-supervisor-sub-agent/a2a-subagent-architecture/30-mcp-server-spec-integration-mapping.md)
- https://modelcontextprotocol.io/
- https://spring.io/projects/spring-ai (Spring AI MCP Implementation Reference)

## Runtime Reference Note

- 본 문서 세트의 구현 기준은 Python runtime이다.
- 기존 Java 소스 링크는 historical reference일 뿐 target package shape의 정본이 아니다.
- runtime guardrail/correlation/tool-parallel 정책의 단일 기준 설정은 `settings/agent.yml`이다.
