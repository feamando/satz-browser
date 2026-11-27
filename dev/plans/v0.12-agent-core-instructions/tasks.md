# Tasks: `v0.12-agent-core-instructions`

- **Plan:** [v2.md](v2.md) (supersedes [v1.md](v1.md))
- **Status:** Complete

## Checklist
- [x] Author `dev/agents/INSTRUCTIONS.md`, `core_dev_flows.md`, and `release_management.md`
- [x] Build cross-platform hooks (`hook_runner.mjs`, `behavior_eval_store.py`, `session_start_context.py`, `pre_invocation_context.py`, `pre_tool_guard.py`, `post_edit_brain_sync.py`, `stop_gate_check.py`, `pre_commit_dev_sync.py`, `release_gate.py`)
- [x] Wire Antigravity (`.agents/hooks.json`) and Claude Code (`.claude/settings.json`) lifecycle enforcement across `SessionStart`, `PreInvocation`/`UserPromptSubmit`, `PreToolUse`, `PostToolUse`, and `Stop`
- [x] Add core subsystem skills (`satz-ui-design-i18n`, `satz-cross-platform-shell`, `satz-sidecar-models-boundary`, `satz-tools-safety-boundary`, `satz-feature-planner`) + upgrade `satz-release-manager` with `scripts/release_version.py`
- [x] Implement detached background behavior-to-skill and error-to-eval worker (`scripts/agent_background_worker.py`)
- [x] Verify `release_gate.py --quick`, Dev Brain `monitor`, `eval`, and `sidecar.test_dev_brain` + `sidecar.test_telemetry`
