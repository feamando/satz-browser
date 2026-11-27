# Agent & Pipeline Hooks (`dev/agents/hooks/`)

Cross-platform lifecycle automation hooks for Antigravity, Claude Code, and local release verification.

## Unified Dispatcher & Shared Helpers
- [hook_runner.mjs](hook_runner.mjs) — Cross-platform Node launcher used by `.agents/hooks.json` (`cwd=.agents/`) and `.claude/settings.json` (`cwd=.`). Resolves repo root cleanly, prefers `<repo>/.venv` or `../sgs/.venv` Python while bypassing Windows Store `WindowsApps\python3.exe` stubs, and fails open (`{}`) on runtime errors.
- [hook_common.py](hook_common.py) — Shared payload parser & emitter supporting both Antigravity camelCase and Claude Code snake_case JSON contracts.
- [hooks.json](hooks.json) — Reference Antigravity lifecycle spec (mirrored at repo root in `.agents/hooks.json` and `.claude/settings.json`).

## Lifecycle Hooks
- [session_start_context.py](session_start_context.py) (`SessionStart`) — Read-only bootstrap injecting core agent rules, Dev Brain graph health, active plans (`dev/plans/*/tasks.md`), git hook health, and recent error lessons (`dev/agents/evals/error_log.jsonl`).
- [pre_invocation_context.py](pre_invocation_context.py) (`PreInvocation` / `UserPromptSubmit`) — Read-only per-prompt Dev Brain retrieval (top 3 semantic + neighbor matches), deduplicated per conversation/prompt hash via OS temp cache.
- [pre_tool_guard.py](pre_tool_guard.py) (`PreToolUse`) — Blocks edits targeting sibling `../sgs`, em/en dashes in `src/i18n/catalog.ts`, hardcoded hex literals in non-token CSS files, private keys/secrets/PII/OS-user-path leaks in workspace files, `git push` when `scripts/security_audit.py scan --mode unpushed` fails, and `git tag` calls when `package.json`/`Cargo.toml`/`tauri.conf.json` versions diverge.
- [post_edit_brain_sync.py](post_edit_brain_sync.py) (`PostToolUse`) — Automatically reindexes `dev/brain/brain_index.sqlite` whenever files under `dev/` are modified and logs manifest version parity & scrubbed errors.
- [stop_gate_check.py](stop_gate_check.py) (`Stop`) — Auto-reindexes stale `dev/` files and blocks completion once if broken Dev Brain links, dirty `src/` i18n mismatches, or dirty release manifest version mismatches exist (with `continuationActive`/`stop_hook_active` loop guard).

## Standalone Git / Security / Release Checks
- [pre_commit_dev_sync.py](pre_commit_dev_sync.py) — Validates manifest version parity, UI dash/secret/privacy audit (`scripts/security_audit.py`), `<90 MB` Planck shard caps, and refreshes `dev/brain/brain_index.sqlite` (`--check-only` for `.git/hooks/pre-push`).
- [release_gate.py](release_gate.py) — Full pre-release validator executed before tagging `v*` or running `build_preview`.
- [scripts/security_audit.py](../../../scripts/security_audit.py) — Pre-push / pre-commit privacy, key scrubbing, and anonymization engine (`scan`, `scrub-text`, `install-git-hooks`).
