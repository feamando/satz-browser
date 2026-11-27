# Satz Browser Agent & Model Core Instructions

Applies to **Antigravity**, **Claude Code**, and all development subagents working in `satz-browser`.
Core Playbooks: [core_dev_flows.md](core_dev_flows.md) · [release_management.md](release_management.md) · Dev Hub: [../README.md](../README.md)

## 1. Repository & Customization Structure (`dev/agents/`)
- **Core Instructions:** [INSTRUCTIONS.md](INSTRUCTIONS.md) (this file), [core_dev_flows.md](core_dev_flows.md), [release_management.md](release_management.md)
- **Hooks:** [hooks/](hooks/README.md) — [hook_runner.mjs](hooks/hook_runner.mjs), [behavior_eval_store.py](hooks/behavior_eval_store.py), [session_start_context.py](hooks/session_start_context.py), [pre_invocation_context.py](hooks/pre_invocation_context.py), [pre_tool_guard.py](hooks/pre_tool_guard.py), [post_edit_brain_sync.py](hooks/post_edit_brain_sync.py), [stop_gate_check.py](hooks/stop_gate_check.py), [pre_commit_dev_sync.py](hooks/pre_commit_dev_sync.py), [release_gate.py](hooks/release_gate.py) (bridged via root `.agents/hooks.json` and `.claude/settings.json`)
- **Skills:** [skills/](skills/satz-release-manager/SKILL.md) — `satz-release-manager`, `satz-dev-brain`, `satz-eval-auditor`, `satz-ui-design-i18n`, `satz-cross-platform-shell`, `satz-sidecar-models-boundary`, `satz-tools-safety-boundary`, `satz-feature-planner`, `satz-git-sync` (bridged via root `.agents/skills.json`)
- **Security & Git Sync:** [security_audit.py](../../scripts/security_audit.py) (`scan`, `scrub-text`, `install-git-hooks`) · [git_sync.py](../../scripts/git_sync.py) (`status`, `pull`, `sync --push`)
- **Developer Behavior:** [behavior/](behavior/README.md) — [developer_patterns.yaml](behavior/developer_patterns.yaml), [behavior_log.jsonl](behavior/behavior_log.jsonl), & background analyzer ([agent_background_worker.py](../../scripts/agent_background_worker.py))
- **Role Management:** [roles/](roles/README.md) — [roles.yaml](roles/roles.yaml) (`release-manager`, `platform-verifier`, `dev-brain-architect`, `eval-security-auditor`)
- **Evals & Error Log:** [evals/](evals/README.md) — [error_log.jsonl](evals/error_log.jsonl), [agent_eval_cases.yaml](evals/agent_eval_cases.yaml), [dev_brain_eval_cases.json](evals/dev_brain_eval_cases.json)

## 2. Hard Invariants Across All Tasks
1. **Optional `../sgs` at Runtime:** `sidecar/planck_vendor/` and `sidecar/models/planck/` (`< 90 MB` shards, zero Git LFS) must work independently; never modify `../sgs`.
2. **Design System & i18n:** Tokens from `src/design-system/tokens.css` only (zero raw hex), zero em/en dashes (`\u2014`/`\u2013`) in UI copy, update `src/i18n/catalog.ts`, validate `node scripts/i18n_extract.mjs --check`.
3. **Plans & Versions:** Create `dev/plans/<plan-slug>/v1.md` + `tasks.md` per initiative; capture release state into `dev/versions/snapshots/` and `dev/analytics/build_telemetry.jsonl`.
4. **Release Gates Before Tagging:** Exact semver parity (`package.json`, `Cargo.toml`, `tauri.conf.json`), `dev/agents/hooks/release_gate.py` passing, private updater keys never committed (`~/.tauri/satz.key` / `TAURI_SIGNING_PRIVATE_KEY`), macOS `.dmg` unsigned `xattr -cr /Applications/satz.app` note preserved.
5. **Dev Brain Sync & Eval:** Keep `dev/brain/brain_index.sqlite` (`journal_mode=DELETE`) current via `python scripts/dev_brain.py reindex` and verify `monitor` + `eval` cleanly before committing.
