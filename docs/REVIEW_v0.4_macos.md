# Satz v0.4 Review: macOS Field Test and Brain Check

Nikita Gorshkov · 2026-11-03 · Status: Input to `docs/PLAN_v0.5.md` · SGS / Satz · Build `4963e38` (debug) on macOS 15, M3 Pro

**TL;DR.** Satz was built from source and used for about 90 minutes like a new user, with 45 screenshots: start screen → conversation → site tabs → compare → knowledge and profile → Mail (12 fictional emails on a local IMAP server) → compose and send gate → Gemma chat. The shell, Mail lanes, triage overview, send gate and Brain storage work. On this Mac, the AI path fails: Gemma runs on CPU (73 s first token, in-app chats die), live tab capture isn't implemented outside Windows (`0 / 0 chars`), the site toolbar is covered by the page, and promotions land in the inbox with no codes extracted. Against the v0.2 goal (agentic chat + real browser + personal knowledge base + agents), 0 of 5 agents exist and the Brain is collected but not usable from the UI. Of 25 plan goals: 7 shipped, 7 partial, 5 broken on macOS, 6 missing. Platform differences are in `docs/PLATFORMS.md`.

## 1. Setup

- MacBook M3 Pro 18 GB. Rust via rustup, `npx tauri build --debug --no-bundle` (57 s).
- Sidecar in a temporary venv with the sgs deps. Gemma 4 E4B downloaded to `sgs/models/gemma-4-e4b-it`.
- Reader checkpoints and `planck13/best.pt` are not on the Mac, so `planck3 (web)`, `hertz (reader)`, `planck (reader)` report `missing` and the Brain uses `HashEncoder`.
- Mail: local pymap IMAP server, 12 fictional messages (3 personal, 4 pings, 2 orders, 3 promos). No SMTP server, so the send gate was cancelled.
- Throwaway profile `demo`. Tests: `pytest` 13/13, `cargo test` 9/9, `npm run build` ok.

## 2. Scorecard vs. plans

| Goal | Plan | State | Evidence |
| :--- | :--- | :--- | :--- |
| Conversations replace tabs; pages are sources | v0.2 §2.1 | shipped | Rail holds conversations with chat + site tabs |
| Focus mode as good as Safari/Chrome | v0.2 §2.2 | broken (macOS) | Toolbar covered; zalando.de rejects the UA |
| Agent rail can highlight and pull items into the thread | v0.2 §2.2 | partial | `Cmd+J` rail reads only |
| Compare view + comparison table | v0.2 §2.2 | partial | Tiling works, no table |
| Agents (Reader, Navigator, Comparer, Watcher, Actor) | v0.2 §2.3 | missing | One request, one answer |
| Planck search home, bands, In depth | v0.2 §3 | missing | Free text goes to chat or DuckDuckGo (`state.ts:234`); `depth.sources` unrendered |
| Trust settings, 30% cap, settings diff | v0.2 §3.1 | missing | Read-only `trust` number |
| Model picker per role | v0.2 §5.1 | missing | One dropdown |
| One personal index across reading and mail | v0.2 §5 | partial | Stored, not browsable; no Brain citations |
| Read/act boundary | v0.2 §5 | shipped | Send gate, Brain proposals |
| Terminal UI | v0.3 M1 | shipped | Consistent |
| Start screen URL / question / both | v0.3 M4 | shipped | `dw.com what are the top stories today?` |
| No demo seeds | v0.3 §1 #2 | partial | 6 seeded bookmarks (`db.rs:338`); new tab = Wikipedia (`main.ts:1192`) |
| Tabs → context with [n] citations | v0.3 M6 | partial | Empty captures on macOS, cited anyway |
| Local models | v0.3 M5 | broken (macOS) | CPU Gemma, readers missing |
| Knowledge base feeds For you | v0.3 M7 | partial | Same bookmark 3x; top topic "bookmark" |
| v0.3 gate: only browser 5 days | v0.3 | missing | "not measured" in NOTES_v0.4 |
| Token auth, encrypted vault, lockout | v0.4 M8 | shipped | `vault.enc`, keychain device key |
| Gemma warm < 3 s | v0.4 M9 | broken (macOS) | 73 s |
| Pinned Mail, four lanes | v0.4 M11-13 | shipped | Pings and orders lanes good |
| Promos out of inbox, codes by company | v0.4 M12 | broken | 3/3 promos in inbox; 0 codes after relabel |
| Mail triage with citations | v0.4 M14 | shipped | Cites all 8 emails |
| `[codes (N)]` on merchant sites | v0.4 M14 | broken | Not shown on zalando.de |
| Send gate with `[new]` badge, undo | v0.4 M13 | partial | Gate ok; no `[new]` badge |
| v0.4 gate: own mail 5 days, 200 labelled | v0.4 | missing | Fixtures only |

## 3. Findings

| # | Sev | Finding | Evidence |
| :--- | :--- | :--- | :--- |
| F1 | P0 | Gemma on CPU on macOS: `device_map="auto" if torch.cuda.is_available() else None`. 73 s first token, ~11 s per streamed chunk; UI fetch dies with `TypeError: Load failed`, sidecar logs `Broken pipe`. A no-source question started "The provided sources do not contain…" (grounding prompt over-refuses). | `satz_models.py:634-635`, `api.ts:990` |
| F2 | P0 | Site toolbar covered by the native page view on macOS (address bar, back, reload, `[codes]`, `[fill login]`) | `tabs.ts:166-200`, `webview_manager.rs:267` |
| F3 | P0 | Live DOM capture is Windows-only. `#[cfg(not(windows))]` posts an empty ingest, so the sidecar fetches the URL unauthenticated. dw.com `0 / 0 chars`, cited anyway | `webview_manager.rs:835-843`, `satz_models.py:752` |
| F4 | P0 | Promo cold start: the heuristic needs `List-Unsubscribe` + a promo word, otherwise `email`; Gemma confidence is hardcoded `0.85`. After a manual relabel to promos, extraction is not re-run (`extracts` has 0 rows), so `0 active codes` | `satz_mail_pipeline.py:1058-1066`, `:1099`, `:1328-1347` |
| F5 | P1 | Locked states are dead ends; Mail says "unlock in [knowledge · profile]" with no PIN field | `mail.ts:633-643` |
| F6 | P1 | Unlock PIN field did not accept input in 4 attempts (create-profile PIN field did). Synthetic input; verify by hand | `knowledge.ts:115-123` |
| F7 | P1 | Mail conversation appears in the rail only after restart (account added via API) | `mail.ts:367-372`, `main.ts:318` |
| F8 | P1 | Sites reject the bare WKWebView UA | no `user_agent` in `src-tauri` |
| F9 | P1 | Menus and the error overlay don't close on Esc or navigation | n/a |
| F10 | P1 | macOS autocorrect on URL, start and search inputs | 1 `spellcheck` attr in `src/` |
| F11 | P1 | Agent rail too narrow; on email tabs it repeats the whole triage | n/a |
| F12 | P2 | Noisy first run: seeded bookmarks (reuters 401), developer error paths, Wikipedia new tab | `db.rs:338`, `main.ts:1192` |
| F13 | P2 | Duplicate sources; order cards say `ordered` for shipped orders (Brain has `status:shipped`); no tracking on card | n/a |
| F14 | P2 | Reply cursor below quote; search only on Enter; no `[new]` badge; native select for model | n/a |

## 4. Brain / knowledge base check

Run against copies of the live profile data (`/tmp`), not the real store. Script: store, recall, isolation, scale, delete, injection.

| Check | Result | Notes |
| :--- | :--- | :--- |
| Mail orders written to `BRAIN.md` with merchant, order number, tracking, status | PASS | `zalando-order-104099887712 ... status:shipped` |
| No `person` from a single email (threshold: ≥ 2 emails or a reply) | PASS | `satz_mail_pipeline.py:1526` |
| Promotion entity after relabel to promos | **FAIL** | Extraction and Brain linking are not re-run on relabel |
| `upsert_entity` writes the index | PASS | n/a |
| Recall: birthday, home address, Zalando order, "who works at Northwind" | PASS 4/4 | 8-10 ms each |
| Prompt block ≤ 3,000 chars | PASS | n/a |
| Profile isolation (Brain dir) | PASS | `profiles/<id>/brain` |
| Recall with 150+ entities | PASS | 89 ms |
| Delete removes from `BRAIN.md` and from recall | PASS | `satz_brain.py:424-440` |
| Page `<brain_store>` neutralized | PASS | `‹brain_store›` |
| Model directive without store intent → proposal only | PASS | stored 0, proposals 1 |
| "remember …" stores directly and is recalled | PASS | n/a |
| Semantic ranking | **DEGRADED** | `planck13/best.pt` missing → `HashEncoder`; "which days do I work out" hit only because the entity was recent, alongside unrelated filler notes |

Code-level issues found (not observable in the UI yet):

| # | Issue | Evidence |
| :--- | :--- | :--- |
| B1 | **Planck passage store is not profile-scoped.** Mail text from the `demo` profile (10 passages: contract, dinner, order) sits in the shared `planck_store.sqlite`, readable after lock and by other profiles | `satz_models.py:65-71`, `store_path`; observed 10 `[conv:mail]` rows |
| B2 | With no profile unlocked, Brain writes go to a shared `base/brain` without any guard; the UI copy says data is "strictly scoped to a profile" | `satz_passwords.py:323-330`, `knowledge.ts:147` |
| B3 | In-flight mail pipeline work reads `runtime.brain` live, so after a profile switch queued messages land in the new profile's Brain | `satz_mail_pipeline.py:1476` |
| B4 | Bookmark ingest title `[Bookmark] lowercase` makes `main_entity` return "Bookmark" for every bookmark: 32 of 50 passages and 10 of 41 queries have entity `bookmark`, which tops "top topics" and floods the digest | `satz_models.py:1261`, `candidates.py:253-267`; observed |
| B5 | Digest repeats one URL: up to 6 passages per ingest plus 2 recent + 2 adjacent per interest, no URL dedupe | `satz_models.py:980`, `:2204-2282` |
| B6 | `/forget` for mail matches `satz_conv_passages.text_norm` (4,000-char blobs) against sentence-level `passages.text_norm`, so only the `[conv:mail]` prefix path deletes anything | `satz_mail_pipeline.py:1656-1660`, `satz_models.py:2359-2392` |
| B7 | `delete_passage` leaves `satz_sources`, `satz_conv_passages`, `edges`, `queries` rows behind | `satz_models.py:2347-2353` |
| B8 | Internal `$source` attribute can render into `BRAIN.md` | `satz_brain.py:466-472` |
| B9 | Brain content is background only: never a numbered, citable source, so users can't see when an answer came from memory | `satz_models.py:1759-1763` |
| B10 | Webmail account entities embed the email in the name, so a second account makes a duplicate instead of an update | `satz_brain.py:792` |

**Verdict.** The Brain store, recall, isolation of the Markdown Brain, delete and the read/act boundary all work. Three things stop it from being trustworthy as a *personal* knowledge base: the passage store leaks across profiles (B1, B2), ranking is lexical on any machine without `planck13` (degraded), and bookmark noise dominates topics and the digest (B4, B5). And it isn't usable: no browse, search or citation surface (B9).

## 5. Gaps against the AI-native goal

| Pillar | Score (this Mac) | Gap |
| :--- | :--- | :--- |
| A real browser | 3/10 | Toolbar hidden, UA rejected, new tab can't take a destination |
| Chat that sees your browsing | 5/10 | One direction only: it reads, but can't highlight, extract or act; empty captures cited |
| A personal knowledge base you use | 3/10 | Collected, not browsable or citable; leaks across profiles |
| Agents that work for you | 1/10 | No tasks, plans, background runs or watches beyond bookmark re-index |

Satz is chat beside browsing, not chat that browses. `docs/PLAN_v0.5.md` turns this into milestones.

## 6. Not tested

Planck 3 web answers and readers (no checkpoints on Mac), real SMTP send and undo, autofill (toolbar hidden), POP3, eval mode with < 200 emails, `[n?]` citation flags (needs a working answer).
