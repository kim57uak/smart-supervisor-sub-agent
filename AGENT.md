@/Users/dolpaks/.codex/RTK.md

# Custom Codex Agent Project Instructions

## Before coding (mandatory)

**Before** editing code or running shell commands in this repository:

- **Karpathy (카파시) 코딩 원칙**은 **전역 설정이 정본**이다. Cursor가 이 사용자·머신에 대해 적용하는 내용—`/Users/dolpaks/.cursor` 및 Cursor 앱/계정에 저장된 **User Rules(Rules for AI 등)**와 세션에 주입된 전역 규칙을 **최우선**으로 준수한다. 레포 안의 Karpathy 요약·예시는 **보조**이며, **전역과 충돌하면 전역이 이긴다**.
- **레포 전용 규칙**: **`AGENT.md`**(이 파일)와 **`.cursor/rules/karpathy-rtk.mdc`**는 RTK, 프로젝트 맵, 스킬 안내 등 **이 저장소에만 해당하는 것**을 다룬다. `AGENTS.md`는 Cursor에서 위 파일들을 함께 참조하도록 연결한다.
- User home **`~/.cursor`**는 Cursor IDE 데이터(확장, 프로젝트 캐시, 전역 규칙과 연동된 설정 등)이다—**삭제하지 않는다**.

## RTK Shell Rule

Always prefix shell commands with `rtk` in this repository.

Examples:

```bash
rtk git status
rtk rg -n "pattern" .
rtk python3 -m compileall -q backend/app
rtk npm run build
```

Use `rtk proxy <cmd>` only when `rtk` does not support a command shape directly, such as complex `find` predicates.

## Karpathy guidelines (coding discipline)

**정본:** Cursor 전역 규칙 **`/Users/dolpaks/.cursor/rules/andrej-karpathy-claude.mdc`** (`alwaysApply: true`; 내용은 `/Users/dolpaks/Downloads/project/andrej-karpathy-skill/CLAUDE.md`와 동기). 여기에 더해 Cursor **User Rules** 등이 있으면 세션에 주입된 전역 규칙을 따르며, **충돌 시 User Rules·앱 설정이 우선**할 수 있다. 이 레포의 로컬 Karpathy/RTK 파일은 그 전역 규칙을 **대체하지 않는다**.

RTK reference:

- `/Users/dolpaks/.codex/RTK.md`

## Project Map

- Web app root: `/Users/dolpaks/Downloads/project/smart-supervisor-sub-agent`
- Supervisor Backend: `src/supervisor-agent/app`
- Supervisor Static UI: `src/supervisor-agent/app/static`
- Sub-Agent Backend: `src/sub-agent/app`
- User skills root: `/Users/dolpaks/.gemini/antigravity/skills`
- User agents root: `/Users/dolpaks/.gemini/antigravity/agents`
- Agent-to-skill index: `/Users/dolpaks/.gemini/antigravity/agents/README.md`

## Skill Discovery Summary

Codex should treat `/Users/dolpaks/.codex/skills/*/SKILL.md` as the source of truth for installed user skills. Agent configs in `/Users/dolpaks/.codex/agents/*/config.json` map runnable agents to those skills.

Current notable skill groups:

- Engineering harness and implementation: `agent-harness-engineering`, `program-from-planning-doc`, `requirements-code-check`, `polyglot-code-review`
- Java/Spring work: `java-a2a-multi-agent`, `java-coding-standards`, `springboot-patterns`, `springboot-security`, `springboot-verification`
- Document and media production: `doc`, `pdf`, `pptx-generator`, `imagegen`
- Browser/API docs support: `playwright`, `openai-docs`
- Skill/plugin operations: `skill-creator`, `skill-installer`, `plugin-creator`, `run-all-sh`
- Business operations: `proposal-estimate-builder`, `contract-review`, `interactive-planning-doc`, `advanced-statistical-analysis`
- Solo-business workflows: `founder-dashboard`, `pricing-packaging-lab`, `competitor-watch`, `customer-support-playbook`, `invoice-tax-workflow`, `sop-automation-runbook`

Important rename:

- `java-agent-harness-engineering` was renamed to `agent-harness-engineering`.
- The matching agent is now `agent-harness-engineering-agent`.
- The current skill file is `/Users/dolpaks/.codex/skills/agent-harness-engineering/SKILL.md`.

## Dashboard Behavior Notes

- Organization chart and Inspector data are generated from the live user skill and agent folders, not from hardcoded UI lists.
- If a skill is renamed, update both the skill folder/frontmatter and the matching agent `config.json`/`agent.md`.
- The backend also normalizes stale `skill_path` values by resolving installed skills through `skill_name` when possible.

## Verification Shortcuts

```bash
rtk rg -n "old-skill-name|new-skill-name" /Users/dolpaks/.codex/skills /Users/dolpaks/.codex/agents backend
rtk python3 -m compileall -q backend/app
rtk node --check backend/app/static/app.js
```
