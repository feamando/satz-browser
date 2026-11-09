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
