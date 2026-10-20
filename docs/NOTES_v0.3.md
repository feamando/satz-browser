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
- **Keyboard Shortcuts Inside Focused Child WebView2 (`src-tauri/src/lib.rs`):**
  - Registered `CmdOrCtrl+N`, `CmdOrCtrl+K`, `CmdOrCtrl+T`, `CmdOrCtrl+W`, `CmdOrCtrl+L`, `CmdOrCtrl+J`, `CmdOrCtrl+M`, `CmdOrCtrl+D`, and `CmdOrCtrl+1`..`CmdOrCtrl+9` as Tauri app menu accelerators (`setup_app_menu_accelerators`), forwarding `menu-shortcut` events to the `"main"` webview so `Mod+1`..`Mod+9` work even when focus is inside a child WebView2 page.

## Milestone 4 (M4): Start Screen, Direct Browsing, Bookmarks

- **Start Input Classification (`src/state.ts` & `src-tauri/src/webview_manager.rs`):**
  - Shared URL vs prompt classification (`classifyStartInput` / `is_likely_url_token`) handles full URLs, bare domains (`dw.com`, `bbc.co.uk/news`, `github.com/feamando/sgs`), local dev servers (`localhost:3000`, `127.0.0.1:8010`), explicit query prefix (`?bbc.co.uk`), natural-language questions, and combined `URL + prompt` inputs.
  - Verified across all 10 test strings in both Node and Rust (`webview_manager::tests::test_url_classification_10_cases`).
- **Direct Browsing & Bookmarks (`src-tauri/src/db.rs`):**
  - Seeded 6 default bookmarks (`dw.com`, `bbc.com/news`, `reuters.com`, `en.wikipedia.org`, `news.ycombinator.com`, `github.com`).
  - Direct browsing opens the target site tab immediately with the agent rail collapsed (`origin = 'direct'`) and auto-archives untouched direct conversations after 24 hours (`auto_archive_stale_direct_conversations`).
  - Verified by unit test `db::tests::test_bookmarks_and_direct_conversation_auto_archive`.
