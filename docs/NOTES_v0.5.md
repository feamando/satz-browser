# Satz v0.5 Execution Notes

Owner: Nikita Gorshkov · Date: 2026-11-09 · Spec: `docs/PLAN_v0.5.md` · Platforms: Windows 11 (RTX 4090 box) + macOS (M3 Pro, 18 GB)

## 1. Overview & Starting State

- Starting commit: `1c09462` (`docs: add v0.5 plan (Parity, Trust, Agents)`).
- Primary repository: `feamando/satz-browser` (`0.5.0`). Read-only sibling repository: `../sgs`.
- Repeatable 12-message mail fixture committed at `docs/smoke/mail_fixture/fixture_12.json` (2 order threads with status change `shipped -> delivered`, 2 OTP/2FA pings, 3 promotions including 1 without `List-Unsubscribe`, 4 real emails, 1 receipt).

---

## 2. Milestone 16 (M16): Platform Parity & Model Doctor

### 2.1 Changes Implemented
- **Site Toolbar Non-Overlap (`src/tabs.ts`, `src-tauri/src/webview_manager.rs`):**
  - `syncWebviewsNow()` measures both `#webview-slot-<id>` and the preceding `.site-tab-toolbar` / `.email-tab-header` (plus `#region-tab-strip`), clamping `y = Math.max(Math.round(rect.top), toolbarBottom)` and passing `toolbar_bottom` and `viewport_h` in `TabBoundsSpec`.
  - Added `compute_child_webview_bounds(spec, titlebar_inset)` and `window_titlebar_inset(window)` in `src-tauri/src/webview_manager.rs`. On macOS, `wry` positions child `WKWebView` instances inside `NSThemeFrame` (which includes the 28 pt window titlebar), whereas DOM `getBoundingClientRect()` is relative to the content layout rect below the titlebar; adding `titlebar_inset` (`outer_height - inner_height` in logical points, 28 pt default on macOS, 0 pt on Windows) prevents the child webview from riding 28 pt up over `.site-tab-toolbar`.
  - Also updated `navigate_and_capture_tab_impl` so off-screen/initial child webviews spawn at `(220.0, 70.0 + inset)` instead of `(0.0, 0.0)`.
  - Verified by Rust unit test `webview_manager::tests::test_child_webview_bounds_never_overlap_toolbar` across single-tab, compare 2-up, compare 4-up, and window resize.
- **macOS Live Tab DOM Capture & Realistic User Agent (`src-tauri/Cargo.toml`, `src-tauri/src/webview_manager.rs`, `sidecar/satz_models.py`):**
  - Added `[target.'cfg(target_os = "macos")'.dependencies]` (`objc2 = "=0.6.5"`, `objc2-foundation = "=0.3.2"`, `objc2-web-kit = "=0.3.2"`, `block2 = "=0.6.2"`).
  - Implemented `#[cfg(target_os = "macos")]` branch in `trigger_dom_capture_with_completion` calling `WKWebView::evaluateJavaScript_completionHandler` with `DOM_CAPTURE_JS` and serializing the returned `NSString` via `NSJSONSerialization` (`FragmentsAllowed`).
  - When a live tab capture times out against the shared 800 ms deadline or fails to evaluate JS, `post_ingest_to_sidecar` posts `capture_mode: "timeout"`. In `SatzSidecarRuntime.ingest_page`, `capture_mode == "timeout"` records `capture_mode = "timeout"` and **never** falls back to unauthenticated `self.web.fetch(url)`.
  - Added `STATIC_SYSTEM_PROMPT_NO_SOURCES` in `sidecar/satz_models.py` so when `SOURCES` is empty, the system prompt explicitly forbids fabricating tab/email content or fake `[1]` citations.
  - Set a realistic desktop browser User-Agent via `.user_agent(default_browser_user_agent())` on every `WebviewBuilder::new` (Edge 131 UA on Windows, Safari 18.2 UA on macOS) so sites like `zalando.de` never serve a "browser not supported" page.
- **Gemma Device Selection (`cuda` / `mps` / `cpu`), 5 s SSE Heartbeat & 30 s Stall Watchdog (`sidecar/satz_models.py`, `src/api.ts`, `src/status.ts`, `src/chat.ts`, `src/main.ts`):**
  - `_detect_gemma_device()` selects `"cuda"` (`torch.bfloat16`, `device_map="auto"`), `"mps"` (`torch.float16`, `.to("mps")`), or `"cpu"` (`torch.float32`).
  - `GET /health` reports `version: "0.5.0"` and `device` on each model entry; status bar displays `gemma [warm · cuda]` / `gemma [warm · mps]`.
  - `stream_chat` emits `{"phase": "heartbeat"}` every 5 seconds during model load, prefill, and generation whenever no SSE event has been yielded for 5 s.
  - `sidecarStreamChat` in `src/api.ts` enforces a 30-second stall watchdog (reset on any SSE event including `heartbeat`). On timeout, it cancels the stream and renders `gemma stopped responding after 30 s.` with working `[retry]` and `[use planck instead]` buttons.
- **Per-OS Sidecar Spawn Defaults, `/doctor` Endpoint & `Cmd+Shift+L` (`src-tauri/src/lib.rs`, `sidecar/satz_models.py`, `src/knowledge.ts`):**
  - `SatzSettings::default()` and `resolve_python_executable()` use `..\sgs` + `..\sgs\.venv\Scripts\python.exe` on Windows and `../sgs` + `../sgs/.venv/bin/python` (with `/opt/homebrew/bin/python3` -> `python3` -> `python` fallback) on macOS/Unix.
  - Added token-gated `GET /doctor` returning `{ok, version: "0.5.0", roles: [{role, model, state, device, path, fix}]}` for all 5 model roles (`chat`, `web_answer`, `reader_hertz`, `reader_planck`, `brain_encoder`) and rendered the **Models (`/doctor`)** panel in Settings/Knowledge view.
  - Added `("fill_login", "Fill Login Credentials", "CmdOrCtrl+Shift+L")` to `setup_app_menu_accelerators` on macOS.
  - Bumped version to `0.5.0` across `src-tauri/Cargo.toml`, `src-tauri/tauri.conf.json`, `package.json`, and `SATZ_SIDECAR_VERSION`.

### 2.2 M16 Verification & Measurements (Windows 11 RTX 4090 Reference Box)
- `npm run build`: **PASS** (`dist/` built in `482 ms`, 0 TypeScript errors)
- `cargo check --manifest-path src-tauri/Cargo.toml`: **PASS**
- `cargo test --manifest-path src-tauri/Cargo.toml`: **PASS** (`11/11` unit tests passing, including `test_child_webview_bounds_never_overlap_toolbar` and `test_settings_default_and_cross_platform_path_normalization`)
- `..\sgs\.venv\Scripts\python.exe -m pytest sidecar -q`: **PASS** (`17/17` tests passing: `13` in `test_satz_models.py` + `4` in `test_m16.py`)
- `/health` & `/doctor` check on Windows 11 (RTX 4090):
  - `GET /health` (unauthenticated): `{"ok": true, "version": "0.5.0"}`
  - `GET /health` (authenticated): `gemma-4-e4b` reports `device: "cuda"`
  - `GET /doctor`: all 5 roles (`chat`, `web_answer`, `reader_hertz`, `reader_planck`, `brain_encoder`) report `state: "ready"` (`chat` on `cuda`, readers & `planck13` encoder on `cpu`).

---

## 3. Milestone 17 (M17): Honest Sources & Shell Polish

### 3.1 Changes Implemented
- **Honest Source Pills, Empty-Source Exclusion & Answer Footer (`sidecar/satz_models.py`, `src/state.ts`, `src/chat.ts`, `src/sources.ts`):**
  - Updated `get_source_text` and added `get_source_capture_mode` in `sidecar/satz_models.py` so timed-out captures (`capture_mode == "timeout"`) never fall back to an unauthenticated `self.web.fetch(url)` during chat context assembly.
  - `assemble_chat_context` excludes `0`-char sources from `used_source_ids` and `SOURCES` (preventing empty tabs from receiving `[1]` citation numbers), while `stream_chat` still includes `0`-char sources in `source_stats` with `chars_captured: 0` and `capture_mode: "timeout"`.
  - Context pills in `src/chat.ts` and rows in `src/sources.ts` display:
    - Live DOM capture (`chars_captured > 0 && capture_mode === "dom"`): `[1] domain · title · 4,820c`
    - Public fallback fetch (`chars_captured > 0 && capture_mode === "fetch"`): `[1] domain · title · public fetch · 3,100c` (tooltip `"captured from public URL, not your logged-in tab"`)
    - Empty capture (`chars_captured === 0`): `domain · title · empty [recapture]` (dimmed, no `[n]` badge, clickable `[recapture]` button).
  - Pre-send banner when all open tabs have `0` captured chars and `web` is off: `no readable page in context · [recapture] · [turn on + web] · [ask without pages]`.
  - Answer footer under each assistant message that used sources: `read N sources · X chars · Y cut`.
- **Source URL Deduplication & Unseeded Bookmarks (`src-tauri/src/db.rs`):**
  - Added `pub fn canonicalize_source_url(raw_url: &str) -> String` (strips `#fragment`, `utm_*` query parameters, and trailing slash) and deduplicated `sources` rows per `(conversation_id, canonical_url)` in `open_tab_with_kind` and `record_tab_navigation_or_title` (`test_canonical_source_url_dedupe`).
  - Removed the 6 seeded bookmarks (`bm-1`..`bm-6`) on first run and added one-time `v05_unseeded_bookmarks` cleanup (`test_bookmarks_and_direct_conversation_auto_archive`).
- **Plain-Language Errors, `[debug]` Drawer & Ordered Overlay Dismissal (`src/state.ts`, `src/chat.ts`, `src/status.ts`, `src/main.ts`, `src/style.css`):**
  - Added `formatPlainErrorMessage` and `stripFilesystemPaths` in `src/state.ts` so user-facing error bubbles show a one-line summary with `[retry]`, `[use planck instead]`, and a `[debug]` toggle for the raw error detail.
  - Replaced `[N errors]` in the status bar with `[log (N)]` (hidden when `0`) and capped `#region-error-log-overlay` at `max-height: 200px` so it never covers the chat composer.
  - Ordered `Esc` and click-outside dismissal: open popover/menu -> open overlay/panel -> Compare View.
  - Widened `.right-panel` to `360px` (`min-width: 320px; max-width: 480px`) and focused the email tab (`tab.kind === "mail"`) right rail on sender card, extracted items, `[save to brain]`, `[ask about this email]`, and `summarize · draft reply · extract dates`.
- **Inline Mail Unlock (+ macOS Touch ID / Keychain) & First-Run Input Cleanup (`sidecar/satz_passwords.py`, `sidecar/satz_models.py`, `src/mail.ts`, `src/knowledge.ts`, `src/start.ts`, `src/rail.ts`, `src/main.ts`):**
  - Added `unlock_with_keychain` and `POST /profile/unlock_keychain` (with macOS `LocalAuthentication` Touch ID evaluation gating the keychain secret).
  - Rendered an inline PIN unlock / profile creation sheet directly inside locked Mail lanes (`src/mail.ts`), unlocking in place and immediately refreshing `state.conversations` (`apiEnsureMailConversation` + `refreshLists()`).
  - Updated `[ + ]` new tab to open `about:blank` with `#address-input-<id>` focused and empty (`placeholder="enter a url or search query_"`), and added `spellcheck="false" autocorrect="off" autocapitalize="off"` across URL, start, rail filter, chat, mail search, and PIN inputs.

### 3.2 M17 Verification & Measurements (Windows 11 RTX 4090 Reference Box)
- `npm run build`: **PASS** (`dist/` built in `390 ms`, 0 TypeScript errors)
- `cargo check --manifest-path src-tauri/Cargo.toml`: **PASS**
- `cargo test --manifest-path src-tauri/Cargo.toml`: **PASS** (`12/12` unit tests passing, including `test_canonical_source_url_dedupe` and `test_bookmarks_and_direct_conversation_auto_archive`)
- `..\sgs\.venv\Scripts\python.exe -m pytest sidecar -q`: **PASS** (`19/19` tests passing: `13` in `test_satz_models.py` + `4` in `test_m16.py` + `2` in `test_m17.py`)
- Smoke script artifacts saved to `docs/smoke/v0.5/m17/windows/`.
