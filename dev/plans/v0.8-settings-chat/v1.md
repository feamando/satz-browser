# Satz v0.8 Plan: Conversational Settings Workspace & Declarative Tool Registry

Author: Nikita Gorshkov (with Antigravity) · 2026-11-24 · Status: Ready for execution · Follows: `docs/PLAN_v0.7_design_system.md` · Spec: `docs/design/DESIGN_SYSTEM.md`

**TL;DR.** Make **Settings** a permanent pinned conversation workspace (`conv-settings`, `origin = "settings"`) with **Chat** as its default landing tab, mirroring `Mail` (`conv-mail`) and `News` (`conv-news`). Users can manage profiles, Google OAuth accounts, Mail IMAP/SMTP credentials, cloud API keys, model roles, and action providers conversationally (or by dropping a `.json` / `.env` file into the composer) while keeping existing manual forms accessible in sibling lane tabs. Execution is **model-agnostic** (supporting both local `gemma-4-e4b` and user-configured cloud models), strictly compliant with **`docs/design/DESIGN_SYSTEM.md` (v1.1)**, guarded by a **zero-secret prompt boundary + `send_gate` confirm tokens**, and powered by a new modular **`sidecar/satz_tools/` `ToolRegistry`** that replaces hardcoded tool `if/elif` dispatch and keeps a clean adapter boundary for optional MCP interop later.

---

## 0. Architectural Constraints & Non-Negotiables

1. **Zero-Secret Prompt Boundary (Local & Cloud):** Raw secrets (profile PINs, Google `client_secret` JSONs, OAuth access/refresh tokens, IMAP/SMTP app passwords, cloud API keys, `.env` values) MUST NEVER enter `messages` SQLite, chat transcripts, Brain Markdown entities, or any LLM prompt/tool argument log. Config/secret files dropped or attached in chat are intercepted in IPC/sidecar memory via an ephemeral `staging_id`; the model sees only sanitized metadata (`{staging_id, kind, prefix/host/project_id}`), and sensitive interactive entry happens inside inline `.card` UI forms talking directly to authenticated sidecar routes (`X-Satz-Token`).
2. **Read / Act & `send_gate` Boundary:** User natural-language chat inside `conv-settings` may call Settings tools, but web page / email / untrusted document contents NEVER authorize Settings mutations. Any action that switches active credentials/profiles, deletes a profile/provider/OAuth connection, or modifies vault auth MUST emit a `send_gate` confirmation (`confirm_token`, single-use) via `.draft` / confirm `.card` before committing.
3. **Model-Agnostic Execution:** All Settings tools compile from one schema (`_active_tools_spec`) consumed identically by local `gemma-4-e4b` (`stream_local_gemma_chat`) and configured cloud models (`stream_cloud_chat` across `CLOUD_PROVIDERS_SPEC`: `gemini`, `anthropic`, `openai`, `mistral`). On `origin === "settings"`, respect `state.selectedModel` and do not auto-escalate a user's chosen local model to cloud via `resolve_chat_route`.
4. **Design System Compliance (`DESIGN_SYSTEM.md` v1.1):**
   - Use semantic CSS tokens only (`--canvas`, `--panel`, `--sunk`, `--hover`, `--line`, `--ink`, `--muted`, `--faint`, `--accent`, `--good`, `--warn`, `--danger`); zero hex literals or non-computed `style=` in `src/*.ts`.
   - Fonts by role: `--font-ui` (Inter), `--font-display` (Besley 700, titles >= 15px only), `--font-mono` (JetBrains Mono, data/URLs/micro labels only).
   - UI copy rules: sentence case, plain-word actions (no `[brackets]`), zero em dashes or en dashes, zero emojis.
   - Verify every UI milestone across **Light (paper) & Dark (violet-black)** themes and **Floating & Flush** layouts, keeping live webview geometry intact via `scheduleWebviewLayoutSync()`.
5. **Backward Compatibility:** Keep all existing Settings sidecar HTTP endpoints (`/profile/*`, `/oauth/google/*`, `/mail/*`, `/models/config`, `/providers/*`), `vault.enc` format (`satz_passwords.py`), and manual UI forms (`src/knowledge.ts`) working cleanly inside dedicated lane tabs alongside `Chat`.

---

## 1. Pinned Conversation Surface (`conv-settings`, `origin = "settings"`)

### 1.1 Rust SQLite & Tauri IPC (`src-tauri/src/db.rs`, `src-tauri/src/lib.rs`)

Extend the permanent pinned system conversation pattern currently used by `ensure_mail_conversation` (`db.rs:630`) and `ensure_news_conversation` (`db.rs:634`):

- **Deterministic Record:** Add `DbState::ensure_settings_conversation(&self) -> SqlResult<Conversation>` in `src-tauri/src/db.rs` calling `self.ensure_pinned_origin_conversation("settings", "conv-settings", "Settings")` (mirroring `ensure_mail_conversation` at `L630` and `ensure_news_conversation` at `L634`).
- **Tauri Command (`src-tauri/src/lib.rs`):** Add `#[tauri::command] fn ensure_settings_conversation(db: State<'_, DbState>) -> Result<Conversation, String>` and register it in `invoke_handler`.
- **Rail Ordering & Guards (`src-tauri/src/db.rs`):**
  - Update `list_conversations` priority order: `CASE c.origin WHEN 'mail' THEN 3 WHEN 'news' THEN 2 WHEN 'settings' THEN 1 ELSE 0 END DESC`.
  - Update `pin_conversation` (`L820`), `archive_conversation` (`L836`), and `delete_conversation` (`L852`, `L858`) guards from `origin IN ('mail', 'news')` / `matches!(origin.as_deref(), Some("mail") | Some("news"))` to include `'settings'` / `Some("settings")`.

### 1.2 Left Rail, Top Bar, Lane Tabs & Navigation (`src/types.ts`, `src/api.ts`, `src/rail.ts`, `src/tabs.ts`, `src/main.ts`, `src/knowledge.ts`)

- **`src/types.ts`:** Extend `ConversationOrigin`:
  ```ts
  export type ConversationOrigin = "chat" | "direct" | "mail" | "news" | "settings";
  ```
- **`src/api.ts`:** Add `apiEnsureSettingsConversation(): Promise<Conversation>` mirroring `apiEnsureMailConversation` (`L372`) and `apiEnsureNewsConversation` (`L385`).
- **`src/rail.ts`:**
  - Include `origin === "settings"` in `systemPinned` (`L70`) and `isPinnedSystem` (`L318`) using the `settings` icon from `src/design-system/icons.ts` (renders right below `Mail` and `News`, above `.sep` and user pins).
  - Show a compact status indicator right-aligned on the row when attention is needed (e.g., locked profile or missing model key using `.dot.warn` / mono text).
  - Rewire `#rail-open-knowledge-btn` (`L277`, `L508`) in `src/main.ts` (`onOpenKnowledgeView` at `L1567`) to ensure and select `conv-settings` with `activeTabId = "chat"` (or toggle back cleanly), eliminating the disconnected chatless Settings overlay while keeping `Mod+B` (`showBrainView`) dedicated to Satz Brain.
- **`src/tabs.ts` & `src/main.ts`:**
  - Treat `isSettingsConv = detail.conversation.origin === "settings"` in `renderTopBar` (`L30`) and `renderTabStrip` (`L338`):
    - **Top bar (`.addr.addr-static-box`):** `lock` icon + `satz://settings` in mono `--muted` / `--faint`, plus agent-panel fold toggle if needed (agent panel starts folded on `settings` by default, just like Mail/News lanes, keeping full focus on `.thread` and inline cards).
    - **Lane tabs (`.tabs`):**
      1. `Chat` (`data-tab-id="chat"`, **default active** on selecting `conv-settings`)
      2. `Profiles & Vault` (`settings-lane:profiles`)
      3. `Models & Keys` (`settings-lane:models`)
      4. `Google & Mail` (`settings-lane:google_mail`)
      5. `Providers` (`settings-lane:providers`)
      6. `Sources & Sync` (`settings-lane:sources`)
    - Render the matching classic sections from `src/knowledge.ts` (`renderKnowledgeView` accordions, `renderGoogleOAuthSectionHtml`, `renderActionProvidersSectionHtml`, `renderMailAccountsSectionHtml`, Theme/Layout `.seg` controls) inside each manual lane tab so power users have zero-click access to forms and tables without leaving the conversation.
  - Refresh sidecar Settings state (`loadSettingsPanelData()`) automatically in the background whenever `conv-settings` is selected (`selectConversation`, `main.ts:3340`).

### 1.3 Secret-Safe Config & Secret File Staging (`src/chat.ts`, `sidecar/satz_models.py`)

Currently `#chat-image-file-input` (`src/chat.ts:662, 1825`) and `extractImageFilesFromDataTransfer` (`src/chat.ts:47, 1845, 1897`) only accept images.

- **Frontend intake (`src/chat.ts`, `src/main.ts`):**
  - On `conv-settings` (and optionally via a clear file-type guard anywhere), extend attach/drop/paste handling to accept `.json`, `.env`, `.txt`, `.toml`, and `.conf` files up to `512 KB`.
  - Send non-image config files directly to a dedicated sidecar endpoint **`POST /settings/stage_file`** (`filename`, `mime`, `content_text`) **instead** of embedding raw text in `messages` SQLite or chat request bodies.
  - Render only the returned safe handle (`{staging_id, detected_kind, summary, safe_fields}`) as a `.pill` in `.composer-ctx` (e.g., `google_client_secret · project: my-app · staged`).
- **Sidecar ephemeral staging store (`sidecar/satz_models.py`):**
  - Store staged payloads strictly in an in-memory TTL dict (`_staged_files[staging_id]`, TTL 10 minutes, bound to current session, wiped on profile lock/switch or consumption, never written unencrypted to SQLite/disk).
  - Auto-classify staged files deterministically before any LLM runs:
    - `google_client_secret`: matches `"installed"` or `"web"` OAuth client JSON via `parse_google_client_secret_json` (`satz_google_auth.py:55`). Redacts `client_secret`, masks `client_id` (`_mask_client_id`), exposes `project_id`, `redirect_uris`.
    - `env_secrets`: parses `KEY=VALUE` pairs, classifies recognized keys (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `MISTRAL_API_KEY`, IMAP/SMTP passwords, etc.), exposes key names & masked prefixes only (`AIza...9x2Q`), never values.
    - `unknown_text`: safe byte/line count only, never auto-fed if it appears to contain key/token material (`-----BEGIN`, `sk-`, `AIza`, `GOCSPX-`, `pass=`).
- **`/chat` Wire Contract (`src/api.ts:1427`, `sidecar/satz_models.py:10077`):**
  - Extend the `/chat` JSON request and `SatzSidecarRuntime.stream_chat(...)` with `origin: ConversationOrigin` and `staged_files: Array<{ staging_id, filename, detected_kind }>` (safe handles only, never raw secrets).
  - Extend the `/chat` SSE completion event and `ChatMessage.extras_json` with optional `ui_cards?: SettingsUiCard[]` so inline interactive Settings cards persist across conversation reloads without storing secrets in SQLite.

---

## 2. Model-Agnostic Execution & Scoped Tooling

Both local and cloud models share the exact same tool schema contract via `WebSearchSessionHarness._active_tools_spec` (`sidecar/satz_web_harness.py:1906`):

1. **Dispatch & Route Preservation (`sidecar/satz_models.py`):**
   - When `origin === "settings"` (passed explicitly on `/chat` request from frontend), force `should_run_web = False` by default (unless user explicitly clicks `Web` or asks a web search) and **skip automatic model escalation** in `resolve_chat_route` (`L6696`).
   - User-selected local model (`gemma-4-e4b`) -> runs via `stream_local_gemma_chat` (`L5133`) with privacy indicator `local only`.
   - User-selected cloud model (`gemini:*`, `anthropic:*`, `openai:*`, `mistral:*`) -> runs via `stream_cloud_chat` (`L4991`) with privacy indicator `cloud (<provider>)` and explicit system reminder that staged secrets remain local in `vault.enc` via `staging_id` handles.
2. **Small-Model Reliability Guardrails (Active for `gemma-4-e4b` and Beneficial for Cloud):**
   - Pass `tool_scope="settings"` into `_active_tools_spec(...)`, scoping active tools strictly to Settings tools (+ read-only `settings_get_summary`) instead of 30+ web/shopping/mail tools.
   - Restrict Settings tool JSON schemas to **flat top-level primitive arguments** (`string`, `boolean`, `integer`, `enum`), maximum 4 parameters per tool.
   - Include a compact **2-example local addendum** in `build_local_tool_system_addendum` when `tool_scope="settings"` showing exact `call:...{...}` / `<tool_call>` syntax for Settings tasks (e.g., staging a Google secret, preparing profile creation).
   - **Malformed-call repair + deterministic card fallback:** If `gemma-4-e4b` returns malformed tool args or fails tool invocation twice, recover deterministically from detected intent / staged file kind and render the corresponding interactive `.card` directly in `.thread` so onboarding never dead-ends.

---

## 3. Extensible `sidecar/satz_tools/` Registry & MCP Strategy

### 3.1 Why In-Sidecar `ToolRegistry` Instead of Standalone Internal MCP

Check against current environment: `mcp` and `fastmcp` are not installed in `..\sgs\.venv` (`sidecar/requirements.txt` contains `cryptography`, `argon2-cffi`, `keyring`). More importantly, running Satz's own Settings tools as a separate external MCP subprocess creates real friction:
- **In-memory security coupling:** Unlocked `vault.enc` keys (`ProfilePasswordManager`), SQLite `self.store_lock`, `GoogleOAuthManager` loopback callback HTTP server, and `gemma_infer_lock` all live inside `SatzSidecarRuntime`. Splitting tools into another process would force building an authenticated back-channel IPC bridge or duplicating sensitive vault handles.
- **Typed UI cards & out-of-band secret intake:** Settings tools must return structured UI directives (`ui_card`, `confirm_token` for `send_gate`, `open_url` for Google OAuth tabs, `refresh_hints` for frontend stores) alongside model-readable JSON summaries, whereas standard MCP `text`/`image` blocks have to tunnel UI payloads via custom metadata anyway.
- **Startup & dispatch speed:** In-process calls execute in `<1ms` with zero child-process startup tax during unlock.

### 3.2 Declarative Modular `ToolRegistry` (`sidecar/satz_tools/`)

Eliminate the monolithic manual wiring in `sidecar/satz_web_harness.py` (`_active_tools_spec` + `_dispatch_tool_call_inner` `if/elif` chains) by introducing a lightweight declarative registry:

```text
sidecar/satz_tools/
├── __init__.py
├── registry.py              # @satz_tool decorator, ToolSpec dataclass, schema compiler, dispatcher
├── settings_status.py       # settings_get_summary, settings_inspect_staged_file, settings_set_appearance_hint
├── settings_profiles.py     # settings_list_profiles, settings_prepare_create_profile, settings_prepare_switch_profile
├── settings_oauth.py        # settings_configure_google_oauth, settings_start_google_oauth, settings_refresh_google_oauth
├── settings_models.py       # settings_get_model_roles, settings_set_model_roles, settings_stage_api_key_card
├── settings_mail.py         # settings_list_mail_accounts, settings_prepare_add_mail_account
└── settings_providers.py    # settings_list_providers, settings_infer_provider, settings_upsert_provider
```

Each registered tool defines:
- `name`, `domain` (`"settings"` | `"web"` | `"brain"` | `"mail"` | `"navigator"`), `description`, `parameters` (flat JSON Schema)
- `mode`: `"read"` | `"staged_write"` | `"confirm_gate"` | `"ui_prompt"`
- `redacted_args`: tuple of arg keys stripped/blocked from model logs
- `mcp_safe`: `bool` (whether safe for optional external MCP exposure)
- `handler(runtime, session, **kwargs) -> ToolResult` returning `{model_payload: dict, ui_cards?: list[dict], side_effects?: dict}`

One registry entry automatically drives:
1. `_active_tools_spec(scopes=[...])` for both cloud SDK formats and local Gemma addendum generation.
2. Dispatcher routing (`ToolRegistry.dispatch(name, args, runtime, session)`), validating types and enforcing `send_gate` tokens uniformly.
3. Optional HTTP route forwarding and unit testing via `pytest`.

### 3.3 Clean MCP Boundary Path (Phase 4)

Because every tool is isolated behind `ToolSpec` metadata:
- **Outbound MCP Server (Optional later):** When external agents (e.g., Antigravity, Claude Code) should inspect or manage non-secret Satz configuration, a thin ~60-line adapter (`sidecar/satz_mcp_bridge.py`) can expose `ToolRegistry.list_tools(mcp_safe=True)` via the `mcp` Python SDK, keeping secret-handling tools inside Satz only.
- **Inbound MCP Client (Optional later):** User-added third-party MCP servers (GitHub, Jira, Obsidian, local CLI scripts) can be wrapped as `domain="external_mcp"` entries in `ToolRegistry` behind the exact same Read/Act and `send_gate` rules.

---

## 4. Settings Tool Catalog & Security Classification

| Tool Name | Domain / Mode | Parameters (Flat Primitives) | Underlying Existing Logic (`satz_models.py` / helpers) | UI / Safety Behavior |
|---|---|---|---|---|
| `settings_get_summary` | `settings` / `read` | `section?: "all" \| "profiles" \| "models" \| "oauth" \| "mail" \| "providers" \| "theme"` | `/profile/status`, `/models/config`, `/oauth/google/status`, `/mail/accounts`, `/providers` | Never returns secret values; returns masked states & readiness dots |
| `settings_inspect_staged_file` | `settings` / `read` | `staging_id: string` | Ephemeral `_staged_files[staging_id]` + `parse_google_client_secret_json` | Returns file classification (`google_client_secret`, `env_secrets`), project/key names, masked prefixes |
| `settings_list_profiles` | `settings` / `read` | *(none)* | `/profile/status` (`ProfilePasswordManager`) | Lists profile ids, active state, keychain/Touch ID readiness |
| `settings_prepare_create_profile` | `settings` / `ui_prompt` | `profile_name: string`, `enable_keychain?: boolean` | Prepares onboarding card hitting `POST /profile/create` | Renders inline `profile_create_card` with masked `.input.pin` + confirm PIN; LLM never sees PIN |
| `settings_prepare_unlock_or_switch` | `settings` / `confirm_gate` | `profile_id: string`, `use_keychain?: boolean` | Prepares switch/unlock card hitting `POST /profile/unlock` or `/profile/unlock_keychain` | If switching away from an unlocked profile, gates via `confirm_token` or Touch ID / PIN card |
| `settings_configure_google_oauth` | `settings` / `staged_write` | `staging_id: string`, `scopes_preset?: "gmail" \| "calendar" \| "drive" \| "basic"` | `GoogleOAuthManager.save_client_config` (`POST /oauth/google/config`) | Validates `staging_id` is `google_client_secret`, saves to `vault.enc`, then prompts login step |
| `settings_start_google_oauth` | `settings` / `ui_prompt` | `provider_label?: string` | `GoogleOAuthManager.start_login` (`POST /oauth/google/start`) | Spawns localhost PKCE/loopback listener and emits `google_oauth_connect_card` with `Open Google sign-in` tab button |
| `settings_refresh_or_disconnect_google` | `settings` / `confirm_gate` | `action: "refresh" \| "disconnect"`, `clear_client_config?: boolean` | `POST /oauth/google/refresh` / `/oauth/google/disconnect` | `refresh` runs immediately; `disconnect` requires clicking `Confirm` with `confirm_token` |
| `settings_stage_api_key_or_env` | `settings` / `ui_prompt` | `provider_id?: "gemini" \| "anthropic" \| "openai" \| "mistral"`, `staging_id?: string` | `POST /models/config` (`save_vault_env` / provider key save in `vault.enc`) | If `staging_id` has recognized `env_secrets`, asks 1-click confirmation card; otherwise renders masked `.input` password card |
| `settings_set_model_roles` | `settings` / `staged_write` | `chat_model?: string`, `reader_model?: string`, `planner_model?: string` | `POST /models/config` (`roles`) | Validates against configured local + cloud models; triggers `sidecarGetModelConfig()` refresh |
| `settings_prepare_add_mail_account` | `settings` / `ui_prompt` | `email?: string`, `label?: string`, `provider_hint?: "gmail" \| "imap" \| "outlook" \| "icloud"` | `POST /mail/accounts/test`, `POST /mail/accounts/add`, or `POST /oauth/google/connect_gmail` | Renders `mail_account_card` (pre-filled host/port defaults + masked app password input or Gmail OAuth shortcut) |
| `settings_infer_and_prepare_provider` | `settings` / `staged_write` | `url_or_name: string`, `category?: string` | `POST /providers/infer` -> `POST /providers/upsert` | Infers domain/URL/actions locally and returns preview `.card` (`Save provider`) |
| `settings_delete_resource_confirm` | `settings` / `confirm_gate` | `resource_type: "profile" \| "mail_account" \| "provider"`, `resource_id: string` | `/profile/delete`, `/mail/accounts/remove`, `/providers/delete` | Always renders high-visibility `.banner.danger` + `.draft` confirm card with `confirm_token` |

*(Action-provider secrets, mail sync intervals, and UI theme/layout toggles map into the same pattern and can be added in 1 function each under `satz_tools/`.)*

---

## 5. Design System & Inline Card Specification (`DESIGN_SYSTEM.md` v1.1)

Every Settings chat element follows `docs/design/DESIGN_SYSTEM.md` and `src/design-system/components.css`:

1. **Shell & Address Bar:**
   - Rail `.row` in Pinned accordion: `settings` icon + `Settings` + optional status `.dot.warn` when profile locked or active provider key missing.
   - `#region-top` uses `.addr.addr-static-box` showing `lock` icon + `satz://settings` in `--font-mono`.
   - `#region-tab-strip` shows `.tab` items (`Chat`, `Profiles & Vault`, `Models & Keys`, `Google & Mail`, `Providers`, `Sources & Sync`).
2. **Composer & Starter Prompts (`.composer` / `.cbox`):**
   - Attach `.chip` supports both images and config/secret files (`.json`, `.env`, `.txt`).
   - Staged files render as `.pill` inside `.composer-ctx` (`staging_id` badge + `x` remove).
   - Model `.chip` + `.menu` allows choosing local or configured cloud models on every turn with privacy line intact.
   - Suggestion `.sugg` row under `.cbox`: plain sentence case (`Connect a Google account`, `Create a profile`, `Add an API key`, `Configure mail account`).
3. **Inline Cards Rendered Inside `.thread`:**
   - Nested inside `.main-body` (`--panel` in floating layout), interactive cards use **`.card.inset` (`--sunk` fill, `1px solid var(--line)`, `--r-lg`, `padding: var(--sp-5)`, `gap: var(--sp-3)`)** so they visually separate cleanly in both themes:
     - **Profile Creation Card (`profile_create_card`):** `.card-h` (`Create profile` + `vault.enc` `.pill`), pre-filled profile name `.input`, `.input.pin` (PIN + confirm PIN), keychain checkbox row, security note in `--fs-xs --muted`, and `.btn.primary` (`Create & unlock`).
     - **Google OAuth Onboarding Card (`google_oauth_connect_card`):** `.card-h` (`Google OAuth`), `.kb-kv-row` diagnostics (`Client ID` masked mono, `Redirect URI`, `Scopes`, `Token status` with `.dot`), `.btn.primary` (`Open Google sign-in` -> opens OAuth URL in a browser tab in the active conversation or external consent flow as needed), auto-polls `/oauth/google/status` cleanly while pending, plus `Connect Gmail` action when Gmail scope is granted.
     - **Secret / Key Card (`vault_secret_input_card`):** `.card-h`, provider/service selector `.select`, masked password `.input`, `Save to vault.enc` `.btn.primary` (or `Confirm import (N keys)` when populated from staged `.env` via `staging_id`).
     - **Send Gate Confirm Card (`confirm_gate_card`):** Uses `.draft` styling (`1px solid var(--line)`, `--r-lg`), `--faint` warning label (`Review change · runs only after you confirm`), summary lines in `--fs-sm` + mono ids, optional `.banner.warn` / `.banner.danger` for destructive actions, and `Confirm` (`.btn.primary`) + `Cancel` (`.btn`).

---

## 6. Execution Milestones (`S1` to `S5`)

| Milestone | Scope | Primary Files | Done Checks |
|---|---|---|---|
| **S1 · Pinned `conv-settings` Shell & File Staging** (`M`) | Add `ensure_settings_conversation`, `settings` origin pin/ordering/guards, rail row + footer shortcut target, `satz://settings` top bar, `.tabs` switching between `Chat` and classic `knowledge.ts` lanes, `.json`/`.env` file staging (`POST /settings/stage_file` + `.pill`). | `src-tauri/src/db.rs`, `src-tauri/src/lib.rs`, `src/types.ts`, `src/api.ts`, `src/rail.ts`, `src/tabs.ts`, `src/knowledge.ts`, `src/chat.ts`, `src/main.ts`, `sidecar/satz_models.py` | `npm run build`, `cargo test`, `pytest sidecar`, both themes & layouts visual check |
| **S2 · Declarative `satz_tools/` Registry & Core Handlers** (`M`) | Create `sidecar/satz_tools/` (`registry.py` + `settings_*.py`), wire into `WebSearchSessionHarness._active_tools_spec` and dispatcher, enforce `origin === "settings"` scoped tool selection & route preservation, implement read/staged_write/ui_prompt/confirm_gate tools for Profiles, OAuth, Models, Mail, Providers. | `sidecar/satz_tools/*`, `sidecar/satz_web_harness.py`, `sidecar/satz_models.py`, `sidecar/test_settings_tools.py` | Unit tests covering all schemas, `staging_id` secret redaction, `send_gate` tokens, local + cloud formatting |
| **S3 · Interactive Inline UI Cards & Live OAuth/Profile Flows** (`L`) | Render `profile_create_card`, `google_oauth_connect_card`, `vault_secret_input_card`, `mail_account_card`, and `confirm_gate_card` inside `src/chat.ts` using `DESIGN_SYSTEM.md` v1.1 tokens/classes (`src/design-system/components.css`), handle post-submit `syncAfterProfileAuthChange` / `loadSettingsPanelData` refreshes cleanly. | `src/chat.ts`, `src/types.ts`, `src/api.ts`, `src/main.ts`, `src/design-system/components.css` | Light/Dark & Floating/Flush checks, interactive create-profile & Google OAuth walkthrough, `0` hex/inline-style violations |
| **S4 · Local Gemma + Cloud Reliability & Security Evals** (`M`) | Tune 1-shot Settings addendum and malformed-call card fallback for `gemma-4-e4b`; verify end-to-end flows with user-configured Cloud models (`gemini`/`anthropic`/`openai`/`mistral`); add red-team eval fixtures in `docs/evals/` (hostile page/email cannot invoke Settings tools or leak `vault.enc` / `staging_id`). | `sidecar/satz_web_harness.py`, `sidecar/satz_evals.py`, `docs/evals/eval_settings_*.json`, `sidecar/test_evals_and_redteam.py` | Dual-target eval pass (`local` + `cloud`), prompt-injection gate 0 failures |
| **S5 · Documentation Handover & Optional MCP Boundary** (`S`) | Update `docs/design/DESIGN_SYSTEM.md` §5 & §7 and `docs/NOTES_v0.8.md` with deviations/measurements; optionally scaffold `sidecar/satz_mcp_bridge.py` if external MCP interop is enabled. | `docs/design/DESIGN_SYSTEM.md`, `docs/NOTES_v0.8.md`, `sidecar/satz_mcp_bridge.py` *(optional)* | Full regression suite + smoke screenshots under `docs/smoke/v0.8/settings/windows/` |

---

## 7. Pre-Execution Verification Commands

Every milestone (`S1`–`S5`) is verified against:

```powershell
# 1. Frontend TypeScript + Vite build + zero-hex / style hygiene check
npm run build

# 2. Rust Tauri SQLite & IPC tests
cargo test --manifest-path src-tauri\Cargo.toml

# 3. Sidecar Python pytest suite
..\sgs\.venv\Scripts\python.exe -m pytest sidecar -v --tb=short
```
