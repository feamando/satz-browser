# Satz v0.3: Working Browser Plan (for Gemini in Antigravity)

Nikita Gorshkov · 2026-10-20 · Status: Ready to execute · SGS / Satz · Target: Windows 11 (4090 box) first, macOS second · Supersedes the Phase 0 lock in `.gemini/antigravity.md`

**TL;DR.** The Phase 0 Tauri shell works: fast, responsive, focus and compare panes are good. v0.3 turns it into a browser Nikita can use daily with real local models, before any Mail work. Seven changes, in order: (1) a black and white, monospace, terminal-style UI; (2) one "Conversations" list in the left rail (pinned + recent) with bookmarks under it, and the word "intent" removed everywhere; (3) every new conversation starts from a chat start screen ("where do you want to start?") that accepts a URL, a question, or both; (4) browser tabs inside each conversation, where every tab is a source of context for that conversation's chat; (5) a local model sidecar wiring in Gemma 4 E4B (chat), the Planck 3.0 answer pipeline (web answers, Hertz reader int8) and the Hertz / Planck readers, with no Gemini or cloud models; (6) sources flow into the chat as context with citations; (7) everything browsed and asked is processed in the background into a local knowledge base that feeds a "For you" digest on the start screen. Flow: `start screen → URL or question → conversation (chat tab + site tabs) → sources → local model answers with [n] citations → background ingest → knowledge base → start screen gets more relevant`. Gate: Nikita uses Satz as his only browser for 5 working days and chats over his tabs with local models.

## 0. Rules for the executing agent

- Write repo: `C:\Users\feama\satz-browser`. Read-only references: `..\sgs`, `..\memail`. Do not edit `sgs`. Import from it.
- Work milestone by milestone (M1 to M7). Each milestone ends with its checks passing and one commit. Do not start the next milestone with a failing check.
- Every milestone must pass: `npm run build` and `cargo check --manifest-path src-tauri/Cargo.toml`. Milestones that touch Rust storage add `cargo test`.
- Reuse before building. The SGS repo already has the answer pipeline, readers, page text extraction, the personal store and the digest. Section 5 lists exact entry points.
- No cloud models. No Gemini, no Bedrock, no API keys in this version. The model picker lists local models only.
- No new frontend framework. Stay on vanilla TypeScript + Vite, but split `src/main.ts` into modules (M1).
- No em dashes in UI copy. No emoji in the UI.
- If a check in this plan turns out to be wrong for the platform (for example a Tauri API behaves differently), stop, write what you found in `docs/NOTES_v0.3.md`, choose the simplest working option, and keep going.

## 1. What exists today (review of commit db985fc)

Works and stays: Tauri v2 multi-webview shell, child webviews positioned over HTML slots (`src-tauri/src/webview_manager.rs`), Focus and Compare layouts, SQLite in WAL mode (`src-tauri/src/db.rs`), keyboard-first rail.

Problems to fix in v0.3:

| # | Finding | Where | Fix (milestone) |
|---|---------|-------|-----------------|
| 1 | Webviews are 4 global slots (`pane-0`..`pane-3`), shared by all conversations. Switching conversation renavigates the same 4 webviews, so page state (scroll, login flow, video position) is lost. | `webview_manager.rs:65`, `:193`; `types.ts` `pane_index` | One webview per tab, label `tab-<id>`, LRU-capped (M3) |
| 2 | New conversations get 4 hardcoded demo URLs (Wikipedia, HN, Tauri docs, DW). The frontend has its own copy of the defaults. The DB seeds 3 demo conversations. | `db.rs:128`, `db.rs:402`; `main.ts:197` | Remove all defaults and seeds. Empty state = start screen (M1, M4) |
| 3 | "Pinned Intents" vs "Active Conversations" are two names for one thing. `intent_title` is used in DB, Rust, TS and UI copy. | `main.ts:397`, `:407`; `db.rs` schema | One "Conversations" list, rename to `title` (M1, M2) |
| 4 | `history_log` gets a new row on every title change as well as every navigation, so history holds duplicates. | `db.rs:515` | Write history only when the URL changes (M2) |
| 5 | The whole UI re-renders through one `innerHTML` and re-syncs every webview on each render. Token streaming would re-render the rail and move webviews ~20 times a second. | `main.ts:339`, `:478-479` | Region renders: rail, tab strip, chat, sources. Sync webviews only on layout change (M1, M3) |
| 6 | Shortcuts are `Ctrl` only. macOS is a target. `Ctrl+F` is taken by focus mode, so find-in-page is lost. | `main.ts:48-123` | `Mod` = Cmd on macOS, Ctrl on Windows. Free `Mod+F` for find (M1, M3) |
| 7 | Keydown is handled in the main webview only. When focus is inside a child webview (a page), app shortcuts probably do not fire. | `main.ts:48` | Check, then fix with app-menu accelerators (M3, see 3.4) |
| 8 | The capability file lists `pane-0`..`pane-3`, so web pages are in scope of the app's core permissions. Web pages should have no IPC. | `capabilities/default.json` | Capability applies to `main` only (M3) |
| 9 | 19 inline `style="..."` attributes and 21 hardcoded colours, so the theme cannot be changed in one place. | `main.ts`, `style.css` | All colour and font from CSS tokens (M1) |
| 10 | The thread view is a dashboard of 3 cards (sources grid, notes, history). It is not a chat. "Notes" have no roles and no model. | `main.ts:528-620` | Chat tab with messages + sources panel (M3, M6) |
| 11 | `.gemini/antigravity.md` says "zero AI models until the Phase 0 gate passes". That blocks M5-M7. | `.gemini/antigravity.md` | Already updated next to this plan |

## 2. Target experience

### 2.1 Look: terminal, black and white

- Background `#000`, text `#e8e8e8`. Greys for structure only: `#0d0d0d` (surfaces), `#1a1a1a` (hover), `#333` (borders), `#777` (muted text). No blue, no other hue. State is shown with inverse video (white block, black text) for active or selected items and with text markers for status, `[ok]`, `[loading]`, `[offline]`, `[err]`.
- One font everywhere, monospace: `"JetBrains Mono", "Cascadia Mono", "Cascadia Code", Consolas, "SF Mono", Menlo, monospace`. Bundle JetBrains Mono as a local woff2 in `public/fonts/` (no network fonts). 13px base, 1.5 line height, tabular numbers.
- Square corners (`border-radius: 0`), 1px borders, no shadows, no gradients, no animations except a block caret `▌` blinking in the chat composer and while streaming.
- Labels are lowercase and short, terminal-style: `conversations`, `pinned`, `recent`, `bookmarks`, `sources (4)`, `model: gemma-4-e4b [ok]`.
- A bottom status line (one row, like a terminal status bar): active model and state, sidecar state, number of sources in context, knowledge base ingest queue length.
- Dark only in v0.3.

### 2.2 Left rail

```
satz                       [mod+k]
> filter conversations_
[+ new conversation]       [mod+n]

pinned
  * Berlin → Lisbon flights   3 src
recent
  Greenland story             5 src
  youtube.com                 1 src
  ...
bookmarks
  youtube.com
  news.ycombinator.com
  [+ bookmark current]     [mod+d]
```

- One list called `conversations`, with two groups: `pinned` and `recent` (recent = not pinned, sorted by last activity). Archived conversations are hidden behind a `show archived` toggle at the bottom of the list.
- Each row: title, source count, and on hover the relative time of the last activity. Right-click or a `…` button: pin, rename, archive, delete.
- `bookmarks` sits below the conversation list. Clicking a bookmark opens it directly (2.5).

### 2.3 Start screen (every new conversation)

A plain AI chat start screen, in the spirit of Claude, Gemini or Le Chat, but in the terminal look:

```
where do you want to start?

> paste a url, ask something, or both_
                                         model: gemma-4-e4b ▾   web: off

for you                       resume
  ...digest items...            Greenland story (2 new pages)
```

One input. Its content decides what happens:

| Input | Result |
|-------|--------|
| URL only (`youtube.com`, `https://...`) | Direct browsing: open a conversation with that site as tab 1, switch to the site tab, agent rail collapsed (2.5) |
| Text only (`what's new on the Greenland story`) | Conversation with the chat tab active. If `web: on`, the Planck 3.0 pipeline searches and reads, and every source it cites is offered as `[open as tab]` |
| URL + text (`nytimes.com/... summarize the main argument`) | Open the URL as a tab (it becomes a source), stay on the chat tab, send the text as the first message with that source in context |

URL detection reuses the rule already in `normalize_url` (`webview_manager.rs:34`). Move it to one shared function so frontend and backend agree. The conversation title is the first message (first 60 characters) or the page title for URL-only starts. The user can rename it.

### 2.4 Inside a conversation: chat tab + site tabs

```
[ chat ] [ nytimes.com · Greenland… ] [ dw.com · … ] [ + ]          compare: select tabs
```

- **Tab 1 is always `chat`.** It cannot be closed. It shows the message thread, the composer, and a `sources` panel on the right.
- **Site tabs are normal browser tabs:** address bar, back, forward, reload, scrolling, clicking, logins. A site tab has a collapsible agent rail on the right (the current Focus mode), which shows the same chat thread and composer. Toggle with `Mod+J`.
- **Every site tab is a source by default.** The sources panel lists every page that has been part of the conversation, newest first:

```
sources (5)                         in context
  [x] nytimes.com  Greenland vote…    tab 2 · 14:02
  [x] dw.com       Denmark responds…  tab 3 · 14:05
  [ ] reddit.com   r/worldnews …      closed · 14:09
  ...
```

  - Each row: checkbox `in context`, domain, title, where it is (tab number, or `closed`), when it was added. Click to jump to the tab (or reopen it if closed).
  - Navigating inside a tab adds the new page as a new source, so the context grows as you browse. Earlier pages from that tab stay listed as `earlier`.
  - Closing a tab keeps its pages as sources (unchecked by default). Unchecking a source removes it from context without deleting it.
- **Compare** stays: select 2 to 4 tabs in the tab strip (`Mod`+click) and press `Mod+M`. The tiles reuse the existing compare grid. The agent rail stays available.
- The answer cites sources as `[1]`, `[2]`. Clicking a citation switches to that tab, or opens it if closed.

### 2.5 Direct browsing (bookmarks and URL-only starts)

The user who wants YouTube should get YouTube. A bookmark click or a URL-only start creates a conversation flagged `origin = direct`, titled by the domain, with one site tab and the agent rail collapsed. It behaves like a normal browser window. If the user never types into the agent rail, the conversation is auto-archived 24 hours after its last activity. One model (everything is a conversation) and no extra concept for the user.

### 2.6 Knowledge base and proactivity

- In the background, every page the user reads in Satz (not only checked sources) and every message they send is processed into a local knowledge base. Nothing leaves the machine.
- The start screen shows `for you` (digest from the knowledge base) and `resume` (conversations with recent activity, most recent first).
- A `knowledge` view, reachable from the rail footer, shows what was learned: top domains, top topics, recent passages, with a delete per item, and a `pause learning` switch. Deleting a conversation deletes its passages.

## 3. Architecture changes

### 3.1 Data model (SQLite, `src-tauri/src/db.rs`)

Add `schema_version` (table `meta`). Migrate from v1 (current) to v2 in code, mapping existing data, so nothing Nikita has saved is lost:

```sql
conversations(id, title, status /*active|archived*/, pinned, origin /*chat|direct*/,
              created_at, last_active_at)
tabs(id, conversation_id, position, url, title, is_open, created_at)       -- one live webview each
sources(id, conversation_id, tab_id NULL, url, title, domain, in_context,
        added_at, captured_at NULL, text_chars NULL)                       -- one row per page visited
messages(id, conversation_id, role /*user|assistant|system*/, content, model NULL,
         source_ids_json NULL, created_at)
bookmarks(id, title, url, position, created_at)
history_log(id, conversation_id, tab_id, url, title, visited_at)           -- only on URL change
```

Migration v1 → v2: `conversations.intent_title` → `title`; `attached_pages` → `tabs` (position = pane_index) plus one `sources` row each; `thread_notes` → `messages` (`author` user→user, system→system); drop the seed rows if they are still the untouched seeds (ids `conv-1`..`conv-3` with no user notes). Add `cargo test` cases for the migration on a fixture DB.

Rust commands (replace the pane commands): `list_conversations`, `get_conversation`, `create_conversation {title, origin}`, `rename/pin/archive/delete_conversation`, `open_tab {conversation_id, url}`, `close_tab`, `reorder_tabs`, `navigate_tab`, `control_tab {back|forward|reload}`, `sync_tab_webviews {visible: [{tab_id, x, y, w, h}]}`, `set_source_in_context`, `add_message`, `list/add/remove_bookmark`.

### 3.2 Webviews: one per tab

- Label `tab-<tab_id>`. Created on first show, kept alive when hidden.
- Cap live webviews at 8 (setting). When over the cap, close the least recently shown hidden webview and mark the tab `suspended`. It reloads its URL when shown again.
- `sync_tab_webviews` shows only the listed tabs at the given bounds and hides every other `tab-*` webview. The frontend calls it on layout changes only (tab switch, rail toggle, compare, window resize), never on chat updates.
- Page events (`load_started`, `load_finished`, `title_changed`) carry `tab_id`. On URL change: update `tabs`, add a `sources` row, add a `history_log` row, then queue a capture (3.5).
- Native webviews draw above the HTML. Keep every HTML popover (model picker, menus, rename field) out of the page area: put them in the rail, the tab strip, the agent rail, or the status line.

### 3.3 Frontend modules

Split `src/main.ts` (1,002 lines) into `api.ts` (invoke + sidecar HTTP), `state.ts`, `rail.ts`, `start.ts`, `tabs.ts` (tab strip + webview sync), `chat.ts` (thread, composer, streaming), `sources.ts`, `knowledge.ts`, `keys.ts`, `status.ts`. Each region renders into its own container. Streaming appends to the current assistant message element only.

### 3.4 Keyboard

`Mod` = Cmd on macOS, Ctrl on Windows.

| Keys | Action |
|------|--------|
| Mod+N | New conversation (start screen) |
| Mod+K | Filter conversations |
| Mod+T | New tab in this conversation (address bar focused) |
| Mod+W | Close tab (chat tab cannot be closed) |
| Mod+1 | Chat tab |
| Mod+2 … Mod+9 | Site tab 1 … 8 |
| Mod+L | Address bar of the current site tab |
| Mod+J | Toggle agent rail on a site tab |
| Mod+M | Compare the selected tabs (2 to 4) |
| Mod+D | Bookmark the current page |
| Mod+F | Left to the page (find in page). No longer used by Satz |
| Esc | Leave compare / close start-screen input |

Check: put focus inside a page and press `Mod+1`. If the main webview does not receive it (likely, because the child webview has focus), register the shortcuts as accelerators on a Tauri app menu (works on macOS and Windows while the window is focused). If WebView2 still swallows them on Windows, handle `AcceleratorKeyPressed` on the WebView2 controller through `with_webview`. Record which option worked in `docs/NOTES_v0.3.md`.

### 3.5 Page capture (sources need text)

Two paths, in this order:

1. **DOM capture (preferred, works on logged-in pages):** on `load_finished`, Rust runs a script in the tab webview that returns `{url, title, html}` of the rendered document, and gets the result back without giving the page any IPC. On Windows use `webview.with_webview` → WebView2 `ExecuteScript` (result arrives in the completion handler). On macOS use `WKWebView evaluateJavaScript:completionHandler:`. Cap html at 2 MB.
2. **Server-side fetch (fallback):** if DOM capture is not available on the platform yet, or fails, the sidecar fetches the URL itself with the SGS `Web.fetch` + cache. This works for public pages only. Mark such sources `captured: fetch`.

Rust posts the capture to the sidecar `POST /ingest`. Extraction to main text happens in the sidecar with SGS `extract_main_text` (trafilatura).

## 4. Local models: the sidecar

### 4.1 Shape

A small Python service in this repo, `sidecar/satz_models.py`, stdlib `http.server` (same approach as `sgs/src/planck3/serve.py`: no new dependencies on the box), bound to `127.0.0.1:8020`. It adds `..\sgs` to `sys.path` and imports from it.

- **Started by Tauri** in `setup` with `std::process::Command` (no shell plugin needed), killed on app exit. Settings in `%APPDATA%\com.satz.browser\settings.json`:

```json
{ "sgs_root": "..\\sgs", "python": "..\\sgs\\.venv\\Scripts\\python.exe",
  "gemma_path": "models/gemma-4-e4b-it", "port": 8020, "max_live_tabs": 8 }
```

- If the sidecar is not running, the app still works as a browser. The status line shows `models [offline]` and the chat composer says so.
- The frontend calls the sidecar directly with `fetch` (CSP is null) and reads streams with `ReadableStream`.

### 4.2 Endpoints

| Endpoint | Does | Reuses |
|----------|------|--------|
| `GET /health` | Lists models with state `not_loaded / loading / ready / missing` and why (missing checkpoint path) | `sgs/src/planck3/doctor.py` checks where useful |
| `POST /chat` `{model, messages, sources:[{id,url,title}], web:false}` → stream | Chat answer, streamed as server-sent events (`data: {"delta": "..."}`, final `{"done": true, "source_ids": [...], "ms": ...}`) | Gemma loader from `policies.py` `GemmaPolicy` (same path and dtype), but with `TextIteratorStreamer` and a larger `max_new_tokens` (1,024). Do not reuse `GemmaPolicy` itself: it is fixed at 48 new tokens |
| `POST /answer` `{question, session}` | Web answer: search → read → weigh → write, with sources and the confidence band | `scripts/planck3.py` `_chat_harness_factory(args)` (it already picks the shipped reader from `results/planck3/r10_product.json` / `r9_product.json`: Hertz reader int8 on CPU + template writer) and `chat.ChatSession` |
| `POST /read` `{model, question, source_ids}` | Answer a factual question from the conversation's own sources with a reader model | `readers.make_reader("x-hertz" | "x-planck")`, `answer.Answerer` pools over given pages |
| `POST /ingest` `{conversation_id, source_id, url, title, html | null}` | Queue page for capture and knowledge base (4.4) | `web.extract_main_text`, `web.extract_jsonld`, `store.Store.add_passages` |
| `GET /digest` | "For you" for the start screen | `digest.build_digest(store)` |
| `POST /forget` `{conversation_id}` | Delete that conversation's passages | new, small |

### 4.3 Model picker (local only)

| Picker entry | What it is | Good for | Behaviour on a free-form chat message |
|--------------|-----------|----------|----------------------------------------|
| `gemma-4-e4b` (default) | Gemma 4 E4B, `models/gemma-4-e4b-it`, bf16 on the 4090 | Chat, summarise and compare sources, plan | Streams a normal answer with [n] citations to sources in context |
| `planck3 (web)` | The Planck 3.0 answer pipeline as shipped (round 9 product: Hertz reader int8 + template writer; picks up round 10 automatically if it passes rule R) | Factual questions answered from the web, with sources and confidence | Runs `/answer`. Cited pages are offered as `[open as tab]` |
| `hertz (reader)` | Hertz cross-reader, `checkpoints/xreader_hertz_rc/reader.pt`, int8 on CPU | Factual questions over the sources in this conversation | Runs `/read` over checked sources. Not a chat model: for non-factual messages it answers `hertz reads facts from sources; switch to gemma for chat` |
| `planck (reader)` | Planck cross-reader, `checkpoints/xreader_planck*/reader.pt` | Same as Hertz, for side-by-side testing | Same as Hertz |

- The `web: on/off` switch on the composer: with Gemma, `on` first runs `/answer` for the message, adds its sources to the conversation (unchecked tabs are not opened automatically), then lets Gemma answer with them in context.
- Models load lazily on first use and stay loaded. Gemma on GPU, readers on CPU, so both fit at once.
- No Gemini, no Bedrock, no cloud keys. The `bedrock` option in SGS stays unused.

### 4.4 Sources as context (prompt rules for Gemma)

- Context = checked sources only. Order: sources in open tabs first (current page of each tab), then other checked sources, newest first.
- Budget: active tab pages in full up to 6,000 characters each. Other checked sources contribute the best 3 passages each (lexical overlap with the message, reuse `web.query_keys`), until a total budget of 24,000 characters is reached. Make the budgets settings.
- System prompt (short): answer from the sources when they are relevant, cite as `[n]` using the numbers given, say plainly when the sources do not contain the answer.
- The assistant message stores `model` and `source_ids_json` so the user can see which sources it used.
- Read/act boundary from the v0.2 plan stays: models only produce text in v0.3. They do not click, type into pages, or open tabs by themselves. The user opens tabs (or clicks `[open as tab]`).

### 4.5 Knowledge base (background)

- One SGS `Store` per user at `%APPDATA%\com.satz.browser\planck_store.sqlite` (pass it as `--store`; do not reuse the SGS dev store in `results/planck3/`). This is the same graph the Planck digest reads, so `for you` works without new code.
- The sidecar runs one worker thread over an ingest queue (a table in the store file). Per page: extract main text → `add_passages` (entity = page title or the conversation title) → co-mention edges follow from the store. Per user message: `log_query`. Per explicit thumbs up or down on a source row: `feedback("source", domain, ±1)`.
- Preference signals, deterministic, no model: visits and dwell time per domain (from tab show/hide timestamps sent with `/ingest`), topics from the store's interests (`Store.interests`).
- `pause learning` skips the queue (pages still work as sources in the conversation). `delete conversation` calls `/forget`.
- Proactive v0.3 = `for you` and `resume` on the start screen. Watchers, notifications and agent-initiated browsing are later phases.

## 5. Milestones

| M | Piece | Reuse vs. new | Rough effort |
|---|-------|---------------|--------------|
| M1 | Terminal theme, mono font, CSS tokens, remove inline styles, rail = one `conversations` list + `bookmarks` placeholder, rename intent → conversation in UI copy, remove demo defaults, `Mod` key, split `main.ts` into modules | Reuse layout and rail; new tokens and module split | M |
| M2 | Schema v2 + migration + `cargo test`, history dedupe, new Rust commands | Reuse `db.rs` patterns; new tables | M |
| M3 | Tabs in conversations: tab strip, chat tab, site tabs with agent rail (old focus mode), compare from selected tabs, one webview per tab with LRU cap, shortcut check (3.4), capability limited to `main` | Reuse `webview_manager.rs` bounds and event code; new per-tab labels | L |
| M4 | Start screen, URL / question / both routing, direct browsing, bookmarks (add, list, open, remove), auto-archive of untouched direct conversations | Reuse `normalize_url`; new screen | S |
| M5 | Sidecar: spawn and kill from Tauri, `/health`, `/chat` with Gemma streaming, `/answer`, `/read`, model picker, status line | Reuse SGS harness factory, readers, Gemma path; new HTTP wrapper | M |
| M6 | Sources as context: page capture (DOM on Windows, fetch fallback), `/ingest` extraction, sources panel, in-context checkboxes, prompt assembly, citations that switch tabs | Reuse `extract_main_text`, `query_keys`; new capture via `with_webview` | M |
| M7 | Knowledge base: ingest worker into a Satz-owned Planck store, `/digest` on the start screen, `resume`, knowledge view, pause learning, forget | Reuse `Store`, `digest.build_digest` | S |
| End | Update README (screenshots, shortcuts, sidecar setup), `docs/NOTES_v0.3.md` with what worked per platform | | XS |

### Checks per milestone

- **M1:** builds pass. Screenshot of rail + empty state in `docs/screenshots/m1.png`. `grep -ri intent src/` returns only the migration mapping. No colour literal outside `:root` in `style.css`. No `style="` in `src/`.
- **M2:** `cargo test` covers v1 → v2 migration on a fixture with the 3 seed conversations plus one user conversation; the user conversation and its notes survive, seeds are dropped. A title change does not add a history row.
- **M3:** script in `NOTES_v0.3.md`: open conversation A with 3 tabs, play a YouTube video in tab 2, switch to conversation B and back: tab 2 is still at the same position (not reloaded). Open 10 tabs: at most 8 webviews alive. `Mod+1` works with focus inside a page. `Mod+F` opens find in page.
- **M4:** the 3 input types in 2.3 each produce the documented result. A bookmark click opens the site in under 1 second on a warm app.
- **M5:** `/health` shows all 4 models with correct state. Gemma streams its first token in under 3 seconds when loaded. `planck3 (web)` answers "What is the capital of Australia?" with a source. Killing the sidecar shows `models [offline]` and the browser keeps working.
- **M6:** open 3 news tabs on one story, ask Gemma "what do these sources disagree on?": the answer cites at least 2 of the 3 tabs with `[n]`, and clicking a citation switches to that tab. Unchecking a source removes it from the next answer's `source_ids`.
- **M7:** after 1 day of use, `/digest` returns items drawn from browsed pages. Deleting a conversation removes its passages (count before and after in `NOTES_v0.3.md`). With `pause learning` on, the ingest queue does not grow.

## 6. Out of scope for v0.3

Mail (memail), cloud models and the cloud-key flow, agents that click or type into pages (Navigator, Actor), Watchers and notifications, image understanding with Gemma, bookmark import from Chrome, a light theme, macOS DOM capture if WKWebView needs more than a day (fetch fallback is enough for the prototype).

## 7. Decisions made in this plan (change if Nikita disagrees)

| Topic | Decision | Why |
|-------|----------|-----|
| Focus mode shortcut | Focus mode becomes "being on a site tab". `Mod+F` goes back to find in page | Daily-driver gate: losing find in page sends people back to Chrome |
| Direct browsing | Creates a conversation flagged `direct`, auto-archived after 24h if the agent was never used | One concept for the user, no clutter in `recent` |
| Existing data | Migrate, do not reset | Real conversations may exist from Phase 0 use |
| Hertz and Planck in the picker | Shown as reader models with an explicit message for non-factual chat | They are trained to read and extract facts, not to chat. A silent fallback to Gemma would hide which model answered |
| Knowledge base store | Satz-owned copy of the SGS `Store`, not the SGS dev store | Keeps test data and real browsing apart |

## 8. Gate to start Mail (Phase 2)

- Satz is Nikita's only browser for 5 working days, 0 Chrome fallbacks (unchanged from v0.2).
- On at least 10 real conversations, chat answers over his own tabs with Gemma cite the right tab, with no fabricated citations he notices.
- The knowledge view shows what was learned, and deleting works.
