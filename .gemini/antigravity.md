# Satz-Browser Workspace Rules & Architecture Memory (v0.2)

- **Owner:** Nikita Gorshkov (2026-10-19 · Draft v0.2)
- **Primary Write Repo:** `C:\Users\feama\satz-browser` (`feamando/satz-browser`)
- **Read-Only Reference Repos (for Phases 1–2):** `..\sgs` (`feamando/sgs`) and `..\memail` (`feamando/memail`)
- **Full Planning Spec:** `docs/PLANNING_v0.2.md`

## Active Phase Lock: Phase 0 (Shell)
- **Target:** Windows 11 (`WebView2` via `Tauri v2`) and macOS (`WKWebView`). Never fork an engine (lesson from `mchromium`).
- **Scope:** Phase 0 Shell ONLY. Zero AI models, zero search pipelines, zero mail fetching until the Phase 0 gate passes.
- **Phase 0 Gate:** Used as the only browser for **5 working days** ($N=5/5$, 0 Chrome fallbacks).
- **Architecture:** Tauri v2 `unstable` multi-webview API. One main UI webview (searchable left conversation rail + thread + controls) and dynamic child WebView2 instances (`pane-0`..`pane-3`) for **Focus Mode** (`Ctrl+F`) and **Compare View** (`Ctrl+M`, 2 to 4 tiled panes).
- **Storage:** Local SQLite (`%APPDATA%\com.satz.browser\satz.db`) for conversations, attached pages, thread notes, and browsing history.

## Full Product Architecture & Decisions (Memorized for Phases 0–4)

1. **Core Model — Conversations Replace Tabs:**
   - Entry point is an **intent** (e.g., *"flights Berlin → Lisbon, mid-March, under €200"*), not a URL tab.
   - Left rail holds searchable, pinnable, archivable conversations with attached source pages intact.
   - **Focus Mode (`Ctrl+F`):** One keystroke switches viewport to the live page (address bar, back/forward, scrolling/clicking) with the conversation/agent side rail alongside it.
   - **Compare View (`Ctrl+M`):** Tiles 2–4 live pages side-by-side next to comparison tables.

2. **Phase 1 — Search (Home Screen on Planck 3.0):**
   - Pipeline: **Read → Weigh → Write** (`serve.py`, `registry`, `consolidate.py`, `writer`) + **"For you" digest** (`digest.py`).
   - **Neutral by default, 30% hard cap:** Personal trust score blends as $0.7 \times \text{system} + 0.3 \times \text{user}$ (max $\pm 3$ points on 0–10 scale; not user-adjustable).
   - System-only answer is computed every time; diffs and $\ge 3$-point disagreements are badged on the card.
   - Perspective spread for contested news shows $\ge 2$ independent source families and names missing perspectives.
   - **Gate:** Band 9–10 $\ge 90\%$ right on fresh questions; local reader within 5 pts of Gemma; $\le 5\text{ s}$/answer on laptop CPU.

3. **Phase 2 — Mail (Always-On Pinned Tab from `memail`):**
   - **Protocols:** IMAP (default, syncs read state/flags; promotions filed locally without moving/deleting server mail unless opted in) + POP3 (forces "leave messages on server"). Credentials stored in OS keychain.
   - **Local Pre-Parse:** DistilBERT 4-label classifier (`email`, `ping`, `information`, `promotion`); $<0.75$ confidence or cold start falls back to local LLM; retrains after 20 user corrections; cached per mail.
   - **Rule-Based Extraction (no LLM):** Ping platform domain map, order/tracking numbers, voucher codes.
   - **Views:** Inbox (real email only), Pings, Information (order dashboard), Promotions (per company with active codes & copy button; surfaced in Focus Mode when browsing that shop), AI Overview.
   - **Gate:** On 500 hand-labelled own emails: real email misfiled as promotion $\le 1\%$, promotion recall $\ge 90\%$, extracted codes correct $\ge 90\%$.

4. **Phase 3 — Read-Only Agents & Shared Layers:**
   - **Personal Index:** Merges Planck's graph store (passages, co-mention edges, interest log, feedback) with `memail`'s entity graph (person, company, order, thread, promotion). Local-only, never uploaded.
   - **Agents:** `Reader` (Planck typed actions), `Navigator` (headless engine sharing cookie jar; search/filter inputs only), `Comparer` (compare tables), `Watcher` (scheduled re-checks).
   - **Model Picker:** User chooses model per role (Reader default: Hertz 1.2 int8 if Round 9 confirms, else Round 5 Planck reader; Writer default: Template; Planner: Gemma; Mail classifier: local DistilBERT). Cloud models (Anthropic, OpenAI, Mistral, Google) are opt-in with user's key and transparent payload inspection.
   - **Gate:** Faster than manual Chrome on 10 real tasks with equal or better answers.

5. **Phase 4 — Actions & Read/Act Boundary:**
   - **Strict Read/Act Split:** Page or email text never authorizes an action.
   - **Actor:** Every commit (pay, book, send, login, submit personal data) is verified against the user's explicit request and gated behind a concrete confirmation line.
   - **Gate:** 0 unauthorized actions on the prompt-injection red-team suite.
