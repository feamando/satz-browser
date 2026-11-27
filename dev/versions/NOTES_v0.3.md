# Satz v0.3 Execution Notes

Owner: Nikita Gorshkov · Date: 2026-10-20 · Target: Windows 11 (4090 box) first, macOS second

## Milestone 1 (M1): Terminal Theme, Monospace Font, CSS Tokens, Module Split

- **Theme & Typography:**
  - Bundled `JetBrainsMono-Regular.woff2` and `JetBrainsMono-Bold.woff2` locally in `public/fonts/`.
  - All colour literals restricted to `:root` in `src/style.css` (`#000000`, `#0d0d0d`, `#1a1a1a`, `#333333`, `#777777`, `#e8e8e8`).
  - Zero inline `style="` attributes across `src/`.
  - Active/selected items use inverse video (`background: var(--fg); color: var(--bg)`).
- **Module Split:**
  - Split monolithic `src/main.ts` into 11 focused TypeScript modules: `types.ts`, `state.ts`, `api.ts`, `keys.ts`, `status.ts`, `rail.ts`, `start.ts`, `tabs.ts`, `chat.ts`, `sources.ts`, and `knowledge.ts`.
  - Replaced `intent` terminology with `conversation` across the UI; `src/api.ts` retains a single v1->v2 migration fallback line (`raw.title ?? raw.intent_title`).
  - Freed `Mod+F` (`Ctrl+F` on Windows, `Cmd+F` on macOS) for native find-in-page.

## Milestone 2 (M2): Schema v2, Migration, Conversation Actions, History Dedupe

- **Schema v2 & Migration (`src-tauri/src/db.rs`):**
  - Added `meta`, `conversations` (`title`, `status`, `pinned`, `origin`, `created_at`, `last_active_at`), `tabs`, `sources`, `messages`, `bookmarks`, and `history_log` (`tab_id` column).
  - Automatic `v1 -> v2` migration drops untouched Phase 0 seed conversations (`conv-1`..`conv-3`) while migrating user-created conversations, `attached_pages` (to `tabs` + `sources`), and `thread_notes` (to `messages`).
  - Verified by unit test `db::tests::test_v1_to_v2_migration_drops_seeds_and_preserves_user_conversations`.
- **History Deduplication:**
  - `record_tab_navigation_or_title` inserts a new `history_log` and `sources` row only when `url` changes. Title changes update the existing `tabs`, `sources`, and `history_log` rows in place.
  - Verified by unit test `db::tests::test_history_log_dedupes_title_changes`.

## Milestone 3 (M3): Per-Tab Webviews, Tab Strip, LRU Cap, Capabilities

- **Capabilities (`src-tauri/capabilities/default.json`):**
  - Scoped `"webviews": ["main"]` so loaded third-party `tab-*` child webviews have zero access to `window.__TAURI_INTERNALS__`.
- **Per-Tab Webviews & LRU Cap (`src-tauri/src/webview_manager.rs`):**
  - Each site tab uses a dedicated child webview `tab-<id>` preserving scroll position, DOM state, and back/forward history across tab switches.
  - Live child webviews are capped at `max_live_tabs = 8` via `select_lru_eviction_candidates` / `enforce_lru_cap`. Least-recently-shown hidden tabs are closed when the cap is exceeded and transparently reloaded when shown again.
  - Verified by unit test `webview_manager::tests::test_lru_cap_evicts_oldest_non_visible_tabs_at_8`.
- **Keyboard Shortcuts Inside Focused Child WebView2 (`src-tauri/src/webview_manager.rs` & `src-tauri/src/lib.rs`):**
  - On Windows 11, child WebView2 controllers register `ICoreWebView2Controller::add_AcceleratorKeyPressed` via `with_webview` (`attach_child_webview_accelerators`) and emit `menu-shortcut` events to the `"main"` webview for `Ctrl+N`, `Ctrl+K`, `Ctrl+T`, `Ctrl+W`, `Ctrl+L`, `Ctrl+J`, `Ctrl+M`, `Ctrl+D`, and `Ctrl+1`..`Ctrl+9` without attaching a Win32 menu bar to the multi-webview parent `HWND`. On macOS, Tauri app menu accelerators (`setup_app_menu_accelerators`) are used.
  - Enabled `default = ["custom-protocol"]` in `src-tauri/Cargo.toml` so launching `satz-browser.exe` directly from `src-tauri/target/debug/` or `src-tauri/target/release/` serves embedded `../dist` assets without requiring a running Vite dev server.
  - Added `ensure_default_desktop_on_windows` at the start of `run()` (`src-tauri/src/lib.rs`): if launched from a sandboxed non-`Default` Win32 desktop (such as `exebox-*`), `satz-browser.exe` re-spawns itself onto `WinSta0\Default` before initializing Tauri/WebView2 so `EBWebView` is never locked by a hidden desktop session.

## Milestone 4 (M4): Start Screen, Direct Browsing, Bookmarks

- **Start Input Classification (`src/state.ts` & `src-tauri/src/webview_manager.rs`):**
  - Shared URL vs prompt classification (`classifyStartInput` / `is_likely_url_token`) handles full URLs, bare domains (`dw.com`, `bbc.co.uk/news`, `github.com/feamando/sgs`), local dev servers (`localhost:3000`, `127.0.0.1:8010`), explicit query prefix (`?bbc.co.uk`), natural-language questions, and combined `URL + prompt` inputs.
  - Verified across all 10 test strings in both Node and Rust (`webview_manager::tests::test_url_classification_10_cases`).
- **Direct Browsing & Bookmarks (`src-tauri/src/db.rs`):**
  - Seeded 6 default bookmarks (`dw.com`, `bbc.com/news`, `reuters.com`, `en.wikipedia.org`, `news.ycombinator.com`, `github.com`).
  - Direct browsing opens the target site tab immediately with the agent rail collapsed (`origin = 'direct'`) and auto-archives untouched direct conversations after 24 hours (`auto_archive_stale_direct_conversations`).
  - Verified by unit test `db::tests::test_bookmarks_and_direct_conversation_auto_archive`.

## Milestone 5 (M5): Local Model Sidecar (`sidecar/satz_models.py`)

- **Process Lifecycle & Settings (`src-tauri/src/lib.rs`):**
  - Spawns `sidecar/satz_models.py` on `127.0.0.1:8020` using `%APPDATA%\com.satz.browser\settings.json` (`sgs_root: "..\\sgs"`, `python: "..\\sgs\\.venv\\Scripts\\python.exe"`, `gemma_path: "models/gemma-4-e4b-it"`, `port: 8020`, `max_live_tabs: 8`) and terminates the child process on `RunEvent::Exit`.
  - When the sidecar is offline, the status bar displays `models [offline]` and browser tabs continue working normally.
- **Verification on Windows 11 RTX 4090 Box:**
  - `GET /health` reports all 4 local models (`gemma-4-e4b`, `planck3 (web)`, `hertz (reader)`, `planck (reader)`).
  - `POST /read` non-factual guard: `"hello how are you"` -> `"hertz reads facts from sources; switch to gemma for chat"`.
  - `POST /answer` (`planck3 (web)`): `"What is the capital of Australia?"` -> `"Canberra. Britannica [1] and Wikipedia [2] report this."` (`band: "9.0/10 (High trust)"`, 6 sources).
  - `POST /chat` (`gemma-4-e4b`, `bfloat16` on CUDA): warm first-token SSE latency measured at **`229 ms`** (target `< 3,000 ms`).
  - Cross-readers (`hertz (reader)`, `planck (reader)`) load explicitly on `device="cpu"` with `quant="int8"` so readers and GPU Gemma coexist in memory without contention.

## Milestone 6 (M6): Sources as Context, DOM Capture, and Citations

- **Page Capture (`src-tauri/src/webview_manager.rs` & `sidecar/satz_models.py`):**
  - Windows WebView2 DOM capture uses `webview.with_webview` + `ICoreWebView2::ExecuteScript` on `PageLoadEvent::Finished` (capped at 2 MB HTML) and posts `{conversation_id, source_id, url, title, html}` to `127.0.0.1:8020/ingest`.
  - When DOM HTML is unavailable, `ingest_page` falls back to SGS `Web.fetch(url)` (`capture_mode: "fetch"`) and extracts main text via `trafilatura` (`web.extract_main_text`).
- **Context Budgets & Citation Verification:**
  - Active tab sources include up to `6,000` characters each; other checked sources include top 3 passages (`rank_passages` / `query_keys`) up to `24,000` characters total.
  - Tested 3 news sources on the Greenland mineral treaty story (`dw.com` `[1]`, `bbc.com` `[2]`, `reuters.com` `[3]`) with prompt `"what do these sources disagree on?"`:
    - Gemma cited all 3 sources inline (`{1, 2, 3}`) across mineral export levy percentage, timeline, and military base discussions, returning `source_ids: ["src-1", "src-2", "src-3"]`.
    - Unchecking `src-2` (`bbc.com`) removed it from the next response's `source_ids` (`["src-1", "src-3"]`).
    - Clicking `[n]` in the chat UI (`handleCitationClick` in `src/main.ts`) switches directly to the corresponding open tab (or reopens it if closed).

## Milestone 7 (M7): Background Knowledge Base, Digest, Pause Learning, and Forget

- **Satz-Owned Planck Store (`%APPDATA%\com.satz.browser\planck_store.sqlite`):**
  - Dedicated SQLite store separate from `..\sgs\results\planck3\`, with background worker thread indexing passages, co-mention entity edges, domain visit counts, and dwell time.
- **Verification Results:**
  - `GET /digest` returned 8 items drawn from browsed/queried pages (`australia`, `canberra`, and Greenland sources).
  - With `pause_learning` enabled (`POST /knowledge/pause {"pause_learning": true}`), posting a new page to `POST /ingest` returned `{"queued": false, "queue_len": 0}` (ingest queue did not grow).
  - Calling `POST /forget {"conversation_id": "conv-greenland-test"}` deleted the conversation's passages cleanly:
    - **`passages_before`: `12`**
    - **`passages_after`: `6`** (`deleted: 6`, removing all 6 passages belonging to `conv-greenland-test` while keeping passages from other sessions).
