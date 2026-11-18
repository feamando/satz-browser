# Satz v0.6 Execution Notes: Satz News

Owner: Nikita Gorshkov · Date: 2026-11-17 · Spec: `docs/PLAN_v0.6_satz_news.md` · Research: `docs/RESEARCH_satz_news_reader.md` · Platform Verified: Windows 11

---

## 1. Overview & Architecture Delivered

Implemented **Satz News** (`M24`-`M29` core implementation + `M30` automated verification suite and Windows desktop release build) as a permanent, pinned conversation (`conv-news`, `origin = "news"`) ordered immediately below `* mail` in the left rail, wired to Planck 3.0's `read -> weigh -> write` primitives (`../sgs/src/planck3/`, kept strictly read-only), profile-isolated `SatzBrain` memory (`story`, `claim`, `topic`, `source`), multi-provider role routing, and monochrome terminal UI views.

---

## 2. Implemented Changes by Layer (`M24`-`M29`)

### 2.1 Rust SQLite & Tauri Commands (`src-tauri/src/db.rs`, `src-tauri/src/lib.rs`)
- Added `ensure_pinned_origin_conversation()`, refactored `ensure_mail_conversation()`, and added `ensure_news_conversation()` (`id = "conv-news"`, `origin = "news"`, `pinned = 1`) invoked automatically on `DbState::init()`.
- Ordered `list_conversations()` so permanent origins sort first (`'mail'` -> `'news'` -> user pinned -> recent).
- Protected `origin IN ('mail', 'news')` in `pin_conversation`, `archive_conversation`, and `delete_conversation`.
- Registered `ensure_news_conversation` in Tauri's `invoke_handler!`.
- Verified by Rust unit test `db::tests::test_pinned_news_conversation_ordering_and_protections`.

### 2.2 Python Sidecar (`sidecar/satz_news.py`, `sidecar/satz_models.py`, `sidecar/satz_brain.py`, `sidecar/config/news_registry_overlay.json`)
- **Overlay & Starter Feeds (`sidecar/config/news_registry_overlay.json`):** Added wire syndication family rules (`wire:ap`, `wire:reuters`, `wire:afp`, `wire:dpa`, `dw`) and 13 curated RSS/Atom starter feeds.
- **Common Brain & PII Scrubber (`sidecar/satz_brain.py`):** Extended `ENTITY_TYPE_DIRS` with `story`, `claim`, `topic`, and `source`; added `scrub_pii_for_external_query()` (with `BOOKING_OR_TRACKING_RE` and `MONEY_AMOUNT_RE`) so private entities from Mail/Brain do not leak PII tokens into external web queries.
- **News Engine (`sidecar/satz_news.py`):**
  - `SatzLLMReader` and `faithful_news` citation/number grounding gate.
  - Conditional RSS/Atom polling (`parse_feed_xml`, `refresh_news_feeds`) with `ETag`/`If-Modified-Since` `304` handling.
  - `resolve_article_family()` merging `planck3.registry` families with wire syndication markers.
  - `list_sources()` exposing `planck3.registry` domains/categories, `trust_record()` arithmetic (`0.7 * system + 0.3 * personal`), `[conflict]` detection, and RSS feed associations (`add_or_toggle_feed`).
  - `build_local_interest_signals()`, `recluster_and_rank()`, `get_stories()`, `translate_article()`, `get_perspectives()`, `answer_news_question()`, `reweigh_answer_meta()`, `list_topics()`, `manage_topic()`, `save_cluster_to_brain()`, and `get_status()`.
- **Role Matrix & Sidecar Endpoints (`sidecar/satz_models.py`):**
  - Extended `get_model_management_config` / `update_model_management_config` with `role_news_planner`, `role_news_capture`, `role_news_reader`, and `role_news_analyzer` across local models (`x-hertz`, `x-planck`, `gemma-4-e4b`) and dynamically discovered cloud models (`gemini`, `anthropic`, `openai`, `mistral`).
  - Added `_complete_role_prompt()`, updated `get_health()`, `set_domain_trust()`, `rank_command_bar_routes()` (`news:` / `open news` -> `search_news`), and added `/news/*` GET/POST HTTP endpoints (`SatzNewsEngine`).

### 2.3 Frontend Shell, Views & Styling (`src/*`)
- **Types, API & State (`src/types.ts`, `src/api.ts`, `src/state.ts`):** Added `ConversationOrigin |= "news"`, `NewsLane`, `AnswerMeta*`, `News*` models, 4 News role keys on `ModelManagementConfig`, `answer_meta` hydration from `extras_json`, `apiEnsureNewsConversation()`, `/news/*` API helpers, and `search_news` Command Bar routing (`news:` prefix).
- **Rail, Tabs & Settings (`src/rail.ts`, `src/tabs.ts`, `src/knowledge.ts`):**
  - Left rail displays `* news (N)` below `* mail` with unpin/rename/delete suppressed (`isPinnedSystem = isMail || isNews`).
  - Tab strip adds `[ top stories ]`, `[ for you ]`, `[ perspectives ]`, `[ topics ]`, and `[ sources ]` lanes alongside live tabs when viewing `conv-news`.
  - Settings Section 1 (`Role Routing Matrix`) persists `#kb-role-news-planner-select`, `#kb-role-news-capture-select`, `#kb-role-news-reader-select`, and `#kb-role-news-analyzer-select`.
- **News Views, Chat Cards & Styling (`src/news.ts`, `src/chat.ts`, `src/main.ts`, `src/style.css`):**
  - Implemented `[ top stories ]`, `[ for you ]` (with explore mode toggle), `[ perspectives ]` side-by-side matrix & Compare View launch, `[ topics ]` follow/watch controls, `[ sources ]` searchable registry with 30% personal trust sliders & RSS feed form, and Monochrome Reader Overlay with translation toggle.
  - Added `AnswerMeta` audit card in `src/chat.ts` (confidence Band pill, meter, counterfactual divergence banner, expandable `[ how i got this ]` table with inline `[+]` / `[-]` live reweigh, `[ in depth ]` passages, and `answer_meta` caching/persistence in `src/main.ts`).
  - Added monochrome CSS classes (`.news-*`) in `src/style.css`.

---

## 3. Verification & Build Results (2026-11-17)

### 3.1 Automated Tests
- `npm run build` (`tsc && vite build`): **PASS** (`19 modules transformed`, `dist/assets/index-BY9SQje3.js` `274.17 kB`, `0` TypeScript errors)
- `cargo test --manifest-path src-tauri\Cargo.toml`: **PASS** (`13 passed; 0 failed`, including `db::tests::test_pinned_news_conversation_ordering_and_protections`)
- `..\sgs\.venv\Scripts\python.exe -m pytest sidecar\test_satz_news.py -q`: **PASS** (`6 passed in 53.56s`)
- `..\sgs\.venv\Scripts\python.exe -m pytest sidecar -q`: **PASS** (`35 passed in 257.62s`)
- `cargo check --release --manifest-path src-tauri\Cargo.toml`: **PASS** (`0` warnings/errors)
- `git -C ..\sgs status --short`: **CLEAN** (`../sgs` untouched)

### 3.2 Desktop Release Binary
- Command: `npm run tauri build -- --no-bundle`
- Output: `C:\Users\feama\satz-browser\src-tauri\target\release\satz-browser.exe`
- Timestamp & Size: `11/17/2026 4:51:21 PM`, `11,659,264` bytes

### 3.3 Pending Live Runtime Checks (`M30` Interactive / Eval Benchmarks)
- Automated unit and sidecar integration suites pass across `test_satz_news.py` and the full Rust/Python suites.
- Interactive GUI smoke inspection in the freshly built `satz-browser.exe` and live 80-query `fresh9`/`fresh10` news benchmark runs were not executed in this build pass and remain ready for interactive testing.
