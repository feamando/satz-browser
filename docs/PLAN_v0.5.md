# Satz v0.5: Parity, Trust, Agents (for Gemini in Antigravity)

Nikita Gorshkov · 2026-11-03 · Status: Ready to execute · SGS / Satz · Target: Windows 11 (4090 box) and macOS (M3 Pro) as equal targets · Follows `docs/PLAN_v0.4.md` (M8 to M15 done, last commit `4963e38`) · Inputs: `docs/REVIEW_v0.4_macos.md`, `docs/PLATFORMS.md`

**TL;DR.** v0.4 passes every test, but a hands-on macOS run showed the AI half doesn't work outside the 4090 box. Gemma loads on CPU (73 s first token). Live tab capture is Windows-only, so chat can't read pages. The site toolbar is covered by the page. Promotions land in the inbox with no codes. The Brain's passage store leaks mail text across profiles. Against the v0.2 goal, a browser that is also an agentic chat over a personal knowledge base, 0 of 5 agents exist. v0.5 does four things, in order. (1) **Parity:** the same build works on macOS and Windows, with real tab capture, a GPU model, a visible toolbar and per-OS defaults (M16). (2) **Honest and calm:** never cite an empty page; plain-language errors; unlock in place (M17). (3) **Trust the Brain, then use it:** profile-scoped storage, clean topics, a Brain view with search, and answers that cite memory as `[B1]` (M18 to M20). (4) **First agents:** one command bar, plus task cards with Comparer and Watcher, behind the existing confirm-gate pattern (M21, M22). Flow: `fix the floor → stop lying about context → make memory private and visible → let the chat do work you can watch and stop`. Gate: Nikita uses Satz as his only browser for 5 working days **on each platform**, and finishes 3 real compare tasks and 1 watch faster than in Chrome.

## 0. Rules for the executing agent

- Write repo: `satz-browser` (Windows: `C:\Users\feama\satz-browser`; macOS: `~/Documents/GitHub/satz-browser`). Read-only reference: `../sgs`. Do not edit `sgs`. Import from it.
- Work milestone by milestone (M16 to M23). Each milestone ends with its checks passing **on both platforms** and one commit. M16 must land first. If only one platform is available in a session, record it in `docs/NOTES_v0.5.md` and run the other platform's checks before the next milestone starts.
- Every milestone must pass: `npm run build`, `cargo check --manifest-path src-tauri/Cargo.toml`, `cargo test --manifest-path src-tauri/Cargo.toml`, and `python -m pytest sidecar -q` with the sgs venv.
- **New in v0.5: every milestone also passes the manual smoke script in Section 9** on each platform, with a screenshot per step saved to `docs/smoke/v0.5/<milestone>/<os>/`. A milestone whose tests pass but whose smoke script fails is not done. That gap is the main lesson of v0.4.
- No new Python dependencies beyond `sidecar/requirements.txt` (`cryptography`, `argon2-cffi`, `keyring`). No new frontend framework. New Rust crates are allowed only for M16 macOS capture (`objc2`, `objc2-foundation`, `objc2-web-kit`, `block2`); record versions in NOTES.
- Local models only. No cloud models, no API keys.
- UI rules stay: black and white terminal look, monospace, square corners, no em dashes, no emoji in UI copy.
- Record measurements and deviations in `docs/NOTES_v0.5.md` (create in M16). Update `docs/PLATFORMS.md` whenever a platform row changes.
- If a check here is wrong for a platform, stop, write what you found in NOTES, choose the simplest working option, and keep going.

## 1. What exists today (review of `4963e38`)

Full evidence in `docs/REVIEW_v0.4_macos.md` (F = UX finding, B = Brain finding).

| # | Finding | Where | Fix |
| :--- | :--- | :--- | :--- |
| 1 | Gemma loads on CPU without CUDA; 73 s first token on M3 Pro; the UI fetch dies with `TypeError: Load failed` (F1) | `satz_models.py:634-635`, `api.ts:990` | M16 |
| 2 | Live DOM capture is `#[cfg(windows)]` only; macOS posts an empty ingest and the sidecar fetches the URL unauthenticated. dw.com `0 / 0 chars` (F3) | `webview_manager.rs:789-843`, `satz_models.py:752` | M16 |
| 3 | Site toolbar covered by the page view on macOS (F2) | `tabs.ts:166-200`, `webview_manager.rs:267` | M16 |
| 4 | Default settings are Windows paths; fallback binary `python` does not exist on macOS | `lib.rs:47-58`, `:446-451` | M16 |
| 5 | Bare WKWebView user agent; zalando.de rejects it (F8) | no `user_agent` in `src-tauri` | M16 |
| 6 | `Mod+Shift+L` missing from the macOS menu accelerators | `lib.rs:493-513` | M16 |
| 7 | Empty captures are still sent and cited; the no-source prompt over-refuses ("The provided sources do not contain…") (F3) | sources pill, `STATIC_SYSTEM_PROMPT` | M17 |
| 8 | Developer errors (full paths, ring buffer covering the composer); menus ignore Esc (F9, F12) | `status.ts`, `rail.ts` | M17 |
| 9 | Locked features are dead ends; unlock PIN field may not accept input; Mail appears only after restart (F5-F7) | `mail.ts:633-643`, `knowledge.ts:115-123`, `mail.ts:367-372` | M17 |
| 10 | Seeded bookmarks, Wikipedia new tab, autocorrect on URL/search inputs (F10, F12) | `db.rs:338`, `main.ts:1192` | M17 |
| 11 | Planck passage store is shared across profiles; mail text readable after lock (B1); no-profile Brain writes go to a shared dir (B2); pipeline writes to whichever profile is active at processing time (B3) | `satz_models.py:65-71`, `satz_passwords.py:323-330`, `satz_mail_pipeline.py:1476` | M18 |
| 12 | Every bookmark gets entity "bookmark" (32/50 passages); digest repeats one URL (B4, B5) | `satz_models.py:1261`, `:980`, `:2204-2282` | M18 |
| 13 | Forget and delete leave orphan rows; mail forget path mostly no-ops; `$source` can render in BRAIN.md (B6-B8) | `satz_models.py:2347-2392`, `satz_brain.py:466-472` | M18 |
| 14 | Brain ranking silently falls back to `HashEncoder` when `planck13/best.pt` is missing | `satz_brain.py:135-160` | M18 |
| 15 | Promo cold start: heuristic needs `List-Unsubscribe`; Gemma confidence hardcoded `0.85`; relabel doesn't re-run extraction or Brain linking (F4) | `satz_mail_pipeline.py:1058-1099`, `:1328-1347` | M19 |
| 16 | Order cards say `ordered` although the Brain has `status:shipped`; no tracking on card; no `[new]` badge in send gate (F13, F14) | `mail.ts` | M19 |
| 17 | Brain is background only: not browsable, not searchable, never cited (B9) | `satz_models.py:1759-1763` | M20 |
| 18 | Four separate inputs (start, address, composer, mail search); routing invisible | `start.ts`, `state.ts:199-268` | M21 |
| 19 | No agents: one request, one answer. Compare view tiles with no table; no watches | `main.ts`, `planck3` compare/watch families unused | M22 |

## 2. Parity (M16)

### 2.1 Model host

- Pick the device at load: `cuda` if available, else `mps` if `torch.backends.mps.is_available()`, else `cpu`. On MPS load in `torch.float16`, `model.to("mps")`. Keep `device_map="auto"` for CUDA.
- Status line shows the device: `gemma [warm · mps]`.
- `/chat` SSE sends `{"phase":"heartbeat"}` every 5 s during prefill and generation. The client treats no event for 30 s as a stall, aborts, and shows: `gemma stopped responding after 30 s. [retry] [use planck instead]`.
- When the request has no sources, `stream_chat` uses a no-sources variant of the system prompt that answers from general knowledge and says so, instead of "The provided sources do not contain".
- Check: on the M3 Pro, warm first token < 5 s over a 2,000-char source; 50-token answer < 20 s. On the 4090, no regression vs M9 (`< 3,000 ms`).

### 2.2 Live tab capture on macOS

- Implement the `#[cfg(target_os = "macos")]` branch of `trigger_dom_capture_with_completion` with `with_webview` → `WKWebView evaluateJavaScript:completionHandler:` (objc2-web-kit). Run the same capture script as the WebView2 path, so both get `{title, visible_text, html, findings}` and post it with the same `post_ingest_to_sidecar` call.
- Do not use a page-reachable channel (custom scheme, `fetch` to the sidecar, IPC): page scripts could forge captures. Pages still get no IPC.
- Keep the shared 800 ms deadline from M9. On timeout, post `capture_mode: "timeout"` (never an empty ingest that pretends to be a capture).
- Check: dw.com, en.wikipedia.org and github.com each capture > 1,000 chars on macOS. A logged-in page (any webmail in a test account) captures text that the unauthenticated fetch can't see.

### 2.3 Browser floor

- Fix the toolbar overlap. Measure `webview-slot-<id>` against `.site-tab-toolbar` on macOS. The child view must start below the toolbar on both OSes (logical vs physical pixels, title bar inset). Add a `cargo test` or frontend unit test for the bounds computation.
- Set a current Safari UA on macOS and a current Edge UA on Windows for child webviews (`WebviewBuilder::user_agent`). Record the strings in NOTES.
- Add `Mod+Shift+L` (fill login) to the macOS menu accelerators.
- Check: zalando.de, amazon.de and a Google login page render without "unsupported browser" on both OSes.

### 2.4 Per-OS defaults and doctor

- `SatzSettings::default()` resolves per OS: `sgs_root = ../sgs`; `python` = `../sgs/.venv/Scripts/python.exe` (Windows) or `../sgs/.venv/bin/python` (macOS), falling back to `python3` then `python`.
- New `GET /doctor` (token-gated) returns per role: `{role, model, state: ready|missing|cpu_only, fix}`, covering Gemma weights, Planck web reader, Hertz reader, Planck reader and the Brain encoder (`planck13/best.pt` + tokenizer). `fix` is a one-line instruction, e.g. `copy checkpoints/planck13/best.pt from the Windows box`.
- Bump versions to `0.5.0`: `package.json`, `tauri.conf.json`, `Cargo.toml`, sidecar `/health` version.
- Check: a clean macOS checkout with only `npm install` and the sgs venv starts the sidecar with no `settings.json` edits.

## 3. Honest and calm (M17)

### 3.1 Sources you can trust

- A source pill shows its capture state: `[1] dw.com · 4,210 chars`, `[1] dw.com · empty [recapture]`, `[1] dw.com · public fetch` (when the fallback fetch was used).
- Empty sources are excluded from the prompt and from citation numbering. If every source is empty, the composer says `no readable page in context. [recapture] [ask without pages]`.
- Answer footer: `read 2 sources · 6,402 chars · 1 cut`.
- One source per URL per conversation (dedupe on normalised URL; keep the newest capture).

### 3.2 Errors and overlays

- Every user-facing error has a cause and one action: `gemma is not downloaded [how to install]`, `reuters.com refused the bookmark fetch (401). [remove bookmark] [ignore]`. No filesystem paths in the UI.
- The ring buffer moves behind `[debug]` in the status line (off by default). The `[N errors]` badge only counts errors with a user action.
- Esc and click-away close every menu, popover and overlay. Navigating closes the rail menu.
- The agent rail gets a minimum width of 360 px, with toggles and suggestion chips wrapping as rows, not one word per line. On an email tab, it opens focused on that email (`summarize · draft reply · extract dates`).

### 3.3 Unlock in place

- Any locked surface (Mail lanes, vault, Brain) shows an inline PIN sheet with a numeric field and `[unlock]`, and returns to the same view on success.
- On macOS, offer Touch ID through `LocalAuthentication` as an alternative to the PIN, gating the existing keychain device key. Windows Hello is out of scope (Section 6).
- Reproduce F6 by hand first (unlock field not taking input). Fix if real; record either way.
- After adding or removing a mail account, reload the conversation list so Mail appears or disappears at once (F7).

### 3.4 First run

- No seeded bookmarks. Empty `For you` says `browse or bookmark pages to build your digest`.
- `[ + ]` opens an empty tab with the address bar focused, not Wikipedia.
- `spellcheck="false" autocorrect="off" autocapitalize="off"` on the start input, address bar, mail search and command bar.

Check: the smoke script steps 1 to 6 (Section 9) show no developer strings and no stuck overlays.

## 4. Trust the Brain (M18)

- **Profile-scoped passage store:** move `planck_store.sqlite` to `profiles/<id>/planck_store.sqlite` while a profile is unlocked. With no profile, use an ephemeral in-memory store that is never written to disk. Migrate: passages with `question LIKE '[conv:mail]%'` move to the profile that owns `mail.sqlite`; everything else moves to the first profile unlocked after upgrade. Record counts in NOTES.
- **No-profile guard:** with no unlocked profile, Brain writes (`upsert_entity`, proposals, mail linking) are refused with `unlock a profile to save to your Brain`, and the knowledge view says so. Fix the copy at `knowledge.ts:147` to say what is scoped.
- **Pipeline binds the Brain at enqueue:** each queued mail job carries `profile_id`. The worker opens that profile's Brain and drops the job if the profile is locked or deleted.
- **Bookmark entities:** set the entity from the page `<title>` or domain, never from the `[Bookmark]` prefix. Store the `[Bookmark]` marker in `question` only. Rebuild entities for existing bookmark passages in the migration.
- **Digest dedupe:** at most 1 item per URL per digest build, at most 2 per domain. `changed:` items replace, not add to, the same URL.
- **Forget and delete cascade:** `delete_passage` also removes matching `satz_conv_passages`, orphan `edges` and `queries`. `/forget` for mail deletes by message id. Add tests for both.
- **Hide internal attributes:** skip keys starting with `$` when rendering `BRAIN.md`.
- **Webmail accounts:** the entity name is the provider; the address goes in `attributes.email`. Upsert by `(provider, email)`.
- **Encoder visibility:** `/doctor` reports `brain ranking: lexical (planck13 missing)`, and the knowledge view shows it.
- Check: the Brain check script from the review (`docs/REVIEW_v0.4_macos.md` §4) is turned into `test_m18_brain_integrity` and passes 13/13, plus: (a) lock `demo`, create `other`, query "contract review" → 0 passages; (b) top topics contain no `bookmark`; (c) a digest over 7 bookmarks has no repeated URL.

## 5. Mail cold start (M19)

- **Promo heuristic:** without `List-Unsubscribe`, classify as `promotion` when at least 2 of these are true: a code pattern (`[A-Z0-9]{5,}` next to code/gutschein/voucher), a discount pattern (`\d+\s?%` or `\d+\s?(EUR|€) off`), unsubscribe text in the body, a sender local-part in (`newsletter`, `news`, `deals`, `promo`, `marketing`, `noreply` + discount). Keep the 0.90 model threshold for the trained classifier.
- Gemma labels return a confidence from the logits of the four label tokens instead of the fixed `0.85`. Below 0.75 → `email` (safe direction).
- **Relabel re-runs the pipeline tail:** moving a message to a lane re-runs extraction and Brain linking for that message, then refreshes the lane.
- **Onboarding:** on first sync with `model_version = cold`, the promos lane header offers `[help sort 10 emails]`, which shows y/n cards that write `corrections`. The lane header shows `classifier: learning · 12 / 50 labels`.
- **Order cards:** status from the latest extract (`ordered → shipped → out for delivery → delivered`), tracking number with `[track]`, total.
- **Send gate:** `[new]` badge when the recipient has never received mail from this account.
- **Codes pill:** with the toolbar fixed (M16) and extraction re-run, `[codes (N)]` shows on merchant domains.
- Check: the 12-email fixture from the review (3 personal, 4 pings, 2 orders, 3 promos, no `List-Unsubscribe`) gives 3/3 promos in promos, 0 personal emails misfiled, `ZALANDO25AUTUMN` with expiry on the Zalando card, and `[codes (1)]` on zalando.de.

## 6. A Brain you can use (M20)

- Split `[knowledge · profile]` into **Settings** (profiles, vault, mail accounts, pause learning) and **Brain** (`Mod+B`).
- Brain view: a search box over entities, passages and mail (FTS5 + encoder rank); entity cards by type (people, organizations, orders, promotions, places, notes) with source links and `[forget]`; a "this week" timeline of what was read and received; top domains with trust.
- **Trust sliders:** per domain, personal score blended `0.7 × system + 0.3 × yours` (v0.2 decision #3: 30% hard cap, not adjustable). Show the system score and the reason when one exists.
- **Cite memory:** Brain items used in a prompt are numbered `[B1]`, `[B2]` in a separate list and rendered as links to the entity card. The citation check covers them.
- Check: ask "when does my Zalando order arrive?" with no tabs open → the answer cites `[B1] Zalando Order 104099887712`; clicking it opens the card.

## 7. One command bar (M21)

- `Mod+K` opens one bar (replacing filter-conversations). It routes a line to: open URL, ask the model, search mail, search Brain, run command (`new conversation`, `bookmark`, `compare`, `lock`). It reuses `classifyStartInput`.
- Before Enter, the bar lists the routes with the default first. The route says whether anything leaves the machine (`web search · duckduckgo`).
- The start screen input becomes the same component.
- Check: the 6 example lines in NOTES (URL, URL + question, question, mail term, Brain term, command) each route correctly by default.

## 8. First agents (M22)

### 8.1 Task card

- A task is a typed object in the conversation: `{goal, steps[], status, started_at, stop_token}`. It renders as a card with live steps (reuse the M9 status log), `[stop]`, and a final result block.
- Any step that would commit (send, submit, buy, sign in) renders as a send-gate line with `[confirm] [cancel]` and a single-use token. None of M22's agents need one; the plumbing lands now so later agents can't skip it.

### 8.2 Comparer

- In compare view (2 to 4 tiles) and in chat (`compare these`), the Comparer reads each tile's capture, extracts a table (reuse the Planck compare family), and pins it in the chat with one column per source and a row per attribute, each cell cited `[n]`.
- Check: 3 product pages → table with price, key specs and source, 0 uncited cells.

### 8.3 Watcher

- Any answer or page can become a watch: `[watch]` stores `{query or url, cadence, condition}` (reuse M10 bookmark change detection and the Planck `watches` table). Results land in `For you` and as a badge on the conversation.
- Check: watch a price on a test page served locally; changing the price fires one `For you` item within one cadence.

### 8.4 Out of scope for M22

Navigator (multi-step search forms) and Actor (any commit). The Actor waits for the v0.2 phase 4 red-team gate.

## 9. Smoke script (both platforms, every milestone)

Fictional data only. Use the 12-email local IMAP fixture (`docs/smoke/mail_fixture/`, add in M16) and a throwaway profile.

1. Launch from a clean app-data dir. Screenshot.
2. Start: `dw.com what are the top stories today?` → answer with ≥ 1 cited source. Screenshot.
3. New tab, type a URL in the visible address bar, go back. Screenshot.
4. Compare 2 tabs. Screenshot.
5. Create profile, lock, unlock in place from the Mail lane. Screenshot.
6. Mail: inbox / pings / orders / promos counts match the fixture. Screenshot each lane.
7. Mail chat: `what do I need to deal with today?` → cited answer. Screenshot.
8. Reply → send gate shows `[new]` → cancel. Screenshot.
9. Brain (from M20): search `zalando`, open the order card. Screenshot.
10. Record first-token latency and capture char counts in NOTES.

## 10. Milestones

| M | Scope | Effort |
| :--- | :--- | :--- |
| M16 | Parity: model device + heartbeat, macOS capture, toolbar, UA, per-OS defaults, `/doctor`, version 0.5.0 | M |
| M17 | Honest sources, plain errors, overlays, inline unlock (+ Touch ID), first-run cleanup | S-M |
| M18 | Brain integrity: profile-scoped store + migration, guards, bookmark entities, digest dedupe, cascades | M |
| M19 | Mail cold start: heuristic, Gemma confidence, relabel re-run, onboarding cards, order cards, `[new]`, codes pill | S-M |
| M20 | Brain view, search, trust sliders, `[B]` citations | M |
| M21 | Command bar | M |
| M22 | Task cards, Comparer, Watcher | M-L |
| M23 | README, `NOTES_v0.5.md`, `PLATFORMS.md`, gate summary | XS |

### Checks per milestone

- All automated suites from Section 0, on both platforms.
- The smoke script, with screenshots committed under `docs/smoke/v0.5/`.
- Any latency or accuracy number in a check is measured on both machines and written to NOTES with the machine name.

## 11. Decisions made in this plan (change if Nikita disagrees)

| # | Question | Decision |
| :--- | :--- | :--- |
| 1 | Gemma backend on macOS | PyTorch MPS first (no new deps). If the M3 Pro misses the 5 s first-token target, note it and propose MLX in NOTES; don't add it in v0.5. |
| 2 | macOS capture channel | Native `evaluateJavaScript` completion handler. No page-reachable channel. |
| 3 | Biometric unlock | Touch ID on macOS in M17. Windows Hello deferred. |
| 4 | Passage store migration | Mail passages go to the mail owner's profile; the rest to the first unlocked profile. No-profile store becomes in-memory only. |
| 5 | Agents in v0.5 | Comparer and Watcher only. Navigator and Actor deferred. |
| 6 | Command bar vs existing inputs | Replaces the start input and the rail filter; the address bar and composer stay. |
| 7 | Trust cap | 30% hard maximum (v0.2 decision #3), not exposed as a setting. |

## 12. Out of scope for v0.5

Cloud models, the Planck search home with bands and "In depth" (v0.6, after M20's trust sliders), Navigator, Actor, Windows Hello, OAuth mail sign-in, mobile.

## 13. Gate after v0.5

- Satz is the only browser for 5 working days on **each** platform (logged in NOTES as days and fallbacks to Chrome).
- 3 real compare tasks and 1 real watch are done faster than by hand in Chrome, with the same or a better answer.
- 0 empty sources cited across the 5 days (logged by the sidecar).
- Mail: on 200 hand-labelled own emails, real email misfiled as promotion ≤ 1%, promotion recall ≥ 90%, code extraction ≥ 90% (carried from v0.4, still not measured).

## Risks & Mitigations

| Risk | Mitigation |
| :--- | :--- |
| Tests pass while the app fails (the v0.4 failure mode) | Smoke script with screenshots on both platforms is part of done (Sections 0, 9) |
| MPS is too slow or unstable for Gemma 4 E4B | Measure in M16; heartbeat and plain stall message keep the UI honest; MLX proposal in NOTES |
| objc2 capture code is brittle across macOS versions | Keep the capture script shared; on failure post `capture_mode: "timeout"` and show `empty [recapture]`, never fake success |
| Store migration loses or misplaces passages | Backup `planck_store.sqlite` before migrating; log counts per profile; test with the review's 50-passage store |
| Agents arrive before the read/act boundary covers them | Task cards ship with the send-gate step type in M22, even though no v0.5 agent commits anything |
| Command bar hides where text goes | Route list always shows destination and whether anything leaves the machine |
