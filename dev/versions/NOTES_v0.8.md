# Satz v0.8 Notes: Conversational Settings Workspace & Declarative Tool Registry

Plan: `docs/PLAN_v0.8_settings_chat.md` · Spec: `docs/design/DESIGN_SYSTEM.md` (v1.2) · Platform: Windows (`1440x900`)

## Pre-Execution Baseline (2026-11-24)
- **Frontend build (`npm run build`):** `tsc && vite build` passed (`23 modules transformed`, built in `618ms`).
- **Rust unit tests (`cargo test --manifest-path src-tauri/Cargo.toml`):** `13 passed; 0 failed` (`db::tests` + `webview_manager::tests`).
- **Sidecar pytest suite (`..\sgs\.venv\Scripts\python.exe -m pytest sidecar -v --tb=short`):** `82 passed in 522.83s (0:08:42)` (`test_evals_and_redteam.py`, `test_google_auth.py`, `test_harness_learning.py`, `test_m16.py`..`test_m22.py`, `test_providers.py`, `test_satz_models.py`, `test_satz_news.py`, `test_speedups_and_skills.py`, `test_unsubscribe_actor.py`, `test_web_harness.py`).
- **MCP runtime check:** `mcp` (`False`) and `fastmcp` (`False`) not installed in `..\sgs\.venv`; `sidecar/requirements.txt` remains `cryptography`, `argon2-cffi`, `keyring`. S1-S3 proceed dependency-free with `sidecar/satz_tools/`.
- **Design hygiene baseline:** `0` hex literals across `src/*.ts`. Computed inline CSS variables (`--c`, `--cols`, `width`) are compliant; 12 minor layout/spacing inline `style=` attributes currently exist in `src/chat.ts` (`L1653`) and `src/knowledge.ts` (`L270, L278, L300, L302, L351, L352, L363, L376, L1611, L1864, L1923`) and will be replaced with design-system classes when touched in S1/S3.

## Milestone Log

### S1 · Pinned `conv-settings` Shell & File Staging
- **Status:** Complete (`docs/PLAN_v0.8_settings_chat.md` §1)
- **Files:** `src-tauri/src/db.rs`, `src-tauri/src/lib.rs`, `src/types.ts`, `src/state.ts`, `src/api.ts`, `src/rail.ts`, `src/start.ts`, `src/tabs.ts`, `src/knowledge.ts`, `src/chat.ts`, `src/main.ts`, `src/design-system/components.css`
- **Notes:** Added persistent `conv-settings` (`origin = "settings"`) with `DbState::ensure_settings_conversation`, ordering (`mail` > `news` > `settings` > user) and delete/archive/pin guards in `src-tauri/src/db.rs` plus `ensure_settings_conversation` IPC command in `src-tauri/src/lib.rs`. Excluded `origin === "settings"` from the left rail (`src/rail.ts`) and Home recents (`src/start.ts`) so Settings opens from the existing footer gear button / profile menu without duplicating a sidebar row. Stripped browser controls (`Back`/`Forward`/`Reload`, `+ New tab`, `Compare`, assistant rail toggle, composer `Web`/`Mail`/`+ Tab` pills) from Settings Chat and Manual settings, added a top `.seg` `[ Chat | Manual settings ]` mode switch (`src/tabs.ts` / `src/main.ts`) rendering either Settings Chat or full `renderKnowledgeView`, kept `.json`/`.env`/`.txt`/`.toml`/`.conf` staging chips via `POST /settings/stage_file`, and removed all 12 non-computed inline `style=` attributes using design-system utility classes.

### S2 · Declarative `satz_tools/` Registry & Core Handlers
- **Status:** Complete (`docs/PLAN_v0.8_settings_chat.md` §2-4)
- **Files:** `sidecar/satz_tools/__init__.py`, `sidecar/satz_tools/registry.py`, `sidecar/satz_tools/settings_staging.py`, `sidecar/satz_tools/settings_status.py`, `sidecar/satz_tools/settings_profiles.py`, `sidecar/satz_tools/settings_oauth.py`, `sidecar/satz_tools/settings_models.py`, `sidecar/satz_tools/settings_mail.py`, `sidecar/satz_tools/settings_providers.py`, `sidecar/satz_tools/fallback.py`, `sidecar/satz_web_harness.py`, `sidecar/satz_models.py`, `sidecar/test_settings_tools.py`
- **Notes:** Built dependency-free `@satz_tool` / `ToolRegistry` (`SATZ_TOOL_REGISTRY`) with Read vs. Act safety boundaries (`conversation_origin != "settings"` rejection), RAM-only `staging_id` secret redaction cleared on `/profile/lock` and profile switches, single-use `confirm_gate` confirmation tokens, `maybe_fallback_settings_cards`, and HTTP endpoints `POST /settings/stage_file` and `POST /settings/confirm_gate` wired into `WebSearchSessionHarness` and `stream_chat` for local Gemma (`<tool_call>`) and Cloud (`gemini`, `anthropic`, `openai`, `mistral`) tool loops.

### S3 · Interactive Inline UI Cards & Live OAuth/Profile Flows
- **Status:** Complete (`docs/PLAN_v0.8_settings_chat.md` §5)
- **Files:** `src/chat.ts`, `src/types.ts`, `src/api.ts`, `src/main.ts`, `src/design-system/components.css`
- **Notes:** Implemented inline Settings UI cards (`profile_create_card`, `profile_unlock_card`, `google_oauth_connect_card`, `vault_secret_input_card`, `mail_account_card`, `provider_preview_card`, `confirm_gate_card`) hydrated from `extras_json` (`ui_cards` / `staged_files`), wired out-of-band actions in `src/main.ts` (`getChatActions`, `handleStartGoogleOAuthInBrowserTab` opening Google login tabs inside `conv-settings` when launched from Settings), and added `.settings-card-*`, `.addr-static.mono`, `.card.compact`, and spacing/pointer classes in `src/design-system/components.css`.

### S4 · Local Gemma + Cloud Reliability & Security Evals
- **Status:** Complete (`docs/PLAN_v0.8_settings_chat.md` §6 S4)
- **Files:** `sidecar/satz_web_harness.py`, `sidecar/satz_evals.py`, `docs/evals/eval_20261124_settings_prompt_injection.json`, `sidecar/test_settings_tools.py`, `sidecar/test_evals_and_redteam.py`
- **Notes:** Added `mode.origin`, `forbidden_tools`, and `max_ui_cards` assertions to `EvalManager` (`sidecar/satz_evals.py`) and checked in `docs/evals/eval_20261124_settings_prompt_injection.json`. Verified local Gemma `<tool_call>` SSE, Cloud Gemini/OpenAI tool loops, non-settings blocking, secret redaction, lock wipe, single-use `confirm_gate` replay rejection, and red-team prompt-injection blocking.

### S5 · Documentation Handover & Optional MCP Boundary
- **Status:** Complete (docs & registry hook; optional `sidecar/satz_mcp_bridge.py` deferred)
- **Files:** `docs/design/DESIGN_SYSTEM.md`, `docs/NOTES_v0.8.md`
- **Notes:** Updated `docs/design/DESIGN_SYSTEM.md` to `Version 1.2 · 2026-11-24` (§5.17 Settings Chat & §7 component classes). `sidecar/satz_mcp_bridge.py` remains deferred because `mcp`/`fastmcp` are not installed in `..\sgs\.venv`; `ToolRegistry.list_tools(mcp_safe_only=True)` provides the stdio MCP export hook when enabled. Live interactive GUI smoke screenshots (`docs/smoke/v0.8/`) not yet captured.

## Post-Execution Verification (2026-11-24)
- **Frontend build (`npm run build`):** `tsc && vite build` passed (`23 modules transformed`, built in `700ms`, exit code `0`).
- **Design hygiene (`Select-String` on `src/*.ts`):** `0` hex literals (`#[0-9a-fA-F]{3,6}\b`); only `4` computed CSS-variable/width `style=` attributes (`src\chat.ts:1857`, `src\news.ts:91`, `src\news.ts:316`, `src\status.ts:74`).
- **Rust unit tests (`cargo test --manifest-path src-tauri/Cargo.toml`):** `14 passed; 0 failed` (`0.81s`, exit code `0`, including `db::tests::test_pinned_settings_conversation_ordering_and_protections`).
- **Targeted Settings & Eval tests (`..\sgs\.venv\Scripts\python.exe -m pytest sidecar/test_settings_tools.py sidecar/test_evals_and_redteam.py -v`):** `10 passed in 14.21s` (exit code `0`).
- **Full Sidecar pytest suite (`..\sgs\.venv\Scripts\python.exe -m pytest sidecar -v --tb=short`):** `87 passed in 557.08s (0:09:17)` (exit code `0`; `test_m13_satzmail_csp_sanitization_smtp_send_gate_confirm_token_undo_and_correction` logged a caught `Windows fatal exception: access violation` trace during `transformers.generation.candidate_generator` import and `PASSED`).
