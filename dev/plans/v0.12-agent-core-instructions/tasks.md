# Tasks: `v0.12-agent-core-instructions`

- **Plan:** [v1.md](v1.md)
- **Status:** Complete

## Checklist
- [x] Author `dev/agents/INSTRUCTIONS.md`, `core_dev_flows.md`, and `release_management.md`
- [x] Build cross-platform hooks (`hook_runner.mjs`, `session_start_context.py`, `pre_invocation_context.py`, `pre_tool_guard.py`, `post_edit_brain_sync.py`, `stop_gate_check.py`, `pre_commit_dev_sync.py`, `release_gate.py`)
- [x] Wire Antigravity (`.agents/hooks.json`) and Claude Code (`.claude/settings.json`) lifecycle enforcement across `SessionStart`, `PreInvocation`/`UserPromptSubmit`, `PreToolUse`, `PostToolUse`, and `Stop`
- [x] Package Antigravity/Claude skills (`satz-release-manager`, `satz-dev-brain`, `satz-eval-auditor`)
- [x] Populate `behavior/`, `roles/`, and `evals/` subfolders with real project specs & benchmarks
- [x] Wire root `.agents/`, `.claude/settings.json`, `AGENTS.md`, `CLAUDE.md`, and `.gemini/antigravity.md`
- [x] Verify `release_gate.py --quick`, Dev Brain `monitor`, `eval`, and `sidecar.test_dev_brain`
