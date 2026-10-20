# **Satz: AI-Native Browser Planning File**

Nikita Gorshkov · 2026-10-19 · Draft v0.2 · Prototype (public later) · SGS · Mac \+ Windows · Builds on Planck 3.0 and memail  
**TL;DR.** Satz is a browser where conversations replace tabs. You open a conversation with an intent. Agents browse for you inside your own logged-in sessions, read and weigh the pages, and answer with citations. At any point you can focus the conversation on the live page and keep browsing normally, with the agent still beside you. Two surfaces are always there. **Search** is the home screen, built on Planck 3.0's read → weigh → write pipeline: hand-scored source trust, a system-only answer computed every time, and a 30% cap on how far your preferences can tilt a result. **Mail** is a pinned tab built from memail: you connect POP3 or IMAP accounts, and a local classifier keeps promotions out of the inbox while filing their codes by company. Every model role can use any model the user picks: SGS models (Planck, Hertz), local open models (Gemma) or cloud models. Local is the default. Everything personal (what you read, your mail, your trust scores) stays on the machine. Satz targets Mac and Windows, ships as a prototype first and goes public later, and is Planck 3.0's consumer surface (it reuses the Satz name and roadmap row from SGS). Sequence: shell and focus mode first, then Search, then Mail, then multi-site agents. Actions come last, behind confirm gates.

## **1\. Why**

**Customer:**

> * Comet, Dia, Atlas and Ecosia keep the tab and the URL bar and add a chat sidebar. Researching across 10 sites still means 10 tabs and copy-paste.  
> * AI search answers repeat whatever ranks highest. The user can't see how trustworthy each source is, or how much their own preferences shaped the answer.  
> * Most of the inbox is promotions, and the codes you'd actually want later are hard to find.

**Commercial / strategic:**

> * Satz gives Planck 3.0 its first real consumer surface. This closes SGS open item 5 ("consumer surface: owner's call"); the browser takes over the Satz name and roadmap row (11-satz-0-1, previously a local chat demo).  
> * Local-first is a position Comet and Atlas can't take: your browsing index and mail never leave the machine.  
> * Planck's G2 target is ≤1% of base-chat cost per correct answer, which makes a free or low-cost tier realistic.

## **2\. The model: conversations instead of tabs**

| Chrome-shaped (Comet, Atlas, Dia) | This browser   |
| :---- | :---- |
| URL bar → page | Intent → conversation |
| Tabs are the unit | Conversations are the unit; pages are attached sources |
| History \= list of URLs | History \= a local, searchable index of everything you read and received |
| AI summarizes the current page | Agents read N pages, weigh them, and answer with citations |
| Gmail is a website | Mail is a built-in tab and an input stream to the same agents |
| You fill forms | Agents fill forms, behind confirm gates (last phase) |

### **2.1 A conversation is a tab**

> * Each conversation is the entry point for one intent, for example "flights Berlin → Lisbon, mid-March, under €200" or "what's new on the Greenland story".  
> * A conversation holds the thread, the pages agents opened (attached as sources), the live pages you visited, and any running tasks or watches.  
> * Conversations sit in a searchable left rail. They can be pinned, archived, or resumed days later with their sources intact.  
> * Every run starts agents that browse as you: they fetch, render, scroll and follow links in a headless engine that shares your cookie jar. That gets them past login walls and paywalls the way you would.

### **2.2 Focus mode: still a browser**

> * One keystroke switches the conversation's viewport to the live page. It behaves like a normal browser: address bar for that page, back/forward, scrolling, clicking.  
> * The agent stays in a side rail. It sees the same page and can highlight things, pull items into the thread ("add this fare to the table") and open more sites in background panes.  
> * Compare view tiles 2-4 live pages next to the agent's comparison table, for airlines, hotels or product specs.  
> * Leaving focus mode drops you back into the thread with nothing lost.  
> * Bar: for plain reading, focus mode has to be as good as Safari or Chrome. Otherwise people go back within a week (risk 2).

### **2.3 Agents inside a conversation**

| Agent | Job | Builds on | Can act?   |
| :---- | :---- | :---- | :---- |
| Reader | Fetch and read N pages, extract candidate answers | Planck's typed action vocabulary (SEARCH, OPEN, FOLLOW, EXTRACT, VERIFY, ANSWER, ABSTAIN) | No |
| Navigator | Multi-step browsing across sites: search forms, filters, pagination | Headless engine \+ your cookies | Search and filter inputs only |
| Comparer | Turn what was collected into a table (price, dates, specs, source) | Planck "compare table" family | No |
| Watcher | Re-check a page or query on a schedule (price drop, story update) | Planck "watch" family, digest.py | No, notifies |
| Actor | Submit, book, buy, send | New | Yes, every commit confirmed (phase 4\) |

Search and filter inputs (a flight search box, a date filter) count as reading. Anything that commits you does not: paying, booking, sending, submitting personal data, logging in.

## **3\. Search (the home screen)**

> * The landing screen is a search bar with a "For you" digest underneath. The digest is Planck's digest.py: updates on what you searched, plus "explore" items drawn only from trusted domains.  
> * Each query runs Planck's read → weigh → write:  
  * **Read:** the reader scores each candidate answer. It never sees trust scores, so your preferences can't leak into reading.  
  * **Weigh:** equivalent values are merged and copies count once (Wikipedia and its mirrors are one family). Confidence is itemized on a 0-10 scale from source trust, independent agreement, conflicts, reader doubt and question type, then shown as a band.  
  * **Write:** a template writer, or a model writer that must pass a faithfulness check and falls back to the template if it doesn't.  
> * The result has two layers: a direct answer, and an "In depth" panel with ranked passages, sources and any conflicting values side by side.  
> * A follow-up question turns the search into a conversation (2.1).

### **3.1 Neutral by default, rebalanceable by you**

**Already in Planck (round 5 design):**

> * A hand-scored source registry by category. Examples: DW/ARD/ZDF score 10, BBC 7, media in pressure jurisdictions 4, state media 2\. Unknown sites score 5 and are flagged "unscored".  
> * Your personal score blends as 0.7 × system \+ 0.3 × yours, so you can move any source by at most 3 points.  
> * The system-only answer is computed every time. If your scores change the value or the band, the card says so and shows the system answer.  
> * A "you disagree" badge appears where you and the system differ by 3+ points.  
> * Rule E passed in round 5\. The worst-case personal profile (every source scored 10 minus the system score) changed accuracy by \+0.4 pts, and every answer that moved band (47%) was flagged on the card.

**New for the browser:**

> * A settings surface: scores per source and per category, the reason behind each score, and an "explore sources I'd normally skip" control.  
> * Perspective spread for contested topics, mostly news. Show at least 2 independent source families and where they differ, and name what's missing (for example, no source from the region concerned). This needs its own check in the style of rule E.  
> * "How your settings changed this answer": a per-answer diff between the system answer and yours.

### **3.2 What the models can do today (same 243-question Brave benchmark)**

| Reader | Accuracy | Notes   |
| :---- | :---- | :---- |
| Round 5 Planck reader \+ template (ships today) | 51.4% | Round 6 baseline |
| Hertz 1.2 reader, int8 on CPU | 60.5% | Round 8: 1.33 s/question, 888 MB; round 9 confirms on fresh questions |
| Gemma (reference) | 63.4% | Too large for a laptop default |

> * Proposed default: the local Hertz int8 reader, if round 9 confirms it. Answers below band 7 escalate to the next model the user has enabled (section 5.1).  
> * Search backend: Brave, adopted in round 5 (new questions 46% vs ddgs 10%). The API quota and cost per user are open commercial questions.

## **4\. Mail (always-on tab)**

**Carried over from memail** (PoC Jan-Feb 2026, \~/Documents/GitHub/memail):

> * **Accounts:** POP3 (server, port, username, app password, TLS), connection test, several accounts. Backend: node-pop3 \+ mailparser. IMAP is new (below).  
> * **Local pre-parse:** a DistilBERT classifier fine-tuned on the machine, with 4 labels: email / ping / information / promotion.  
  * Below 0.75 confidence it falls back to an LLM. Cold start also uses the LLM.  
  * It retrains after 20 user corrections.  
  * Results are cached, so each mail is classified once.  
> * **Rule-based extraction, no LLM:**  
  * the platform behind a ping, from a sender-domain map (LinkedIn, Slack, GitHub, Jira...)  
  * order and tracking numbers (Amazon, UPS, FedEx/USPS patterns)  
  * voucher codes  
> * **Views:**  
  * **Inbox:** real email only.  
  * **Pings:** grouped by platform and author.  
  * **Information:** orders and receipts, shown as an order dashboard with status and tracking.  
  * **Promotions:** never in the inbox. Stored per company with active codes, expiry dates and a copy button; expired codes are marked.  
  * **AI overview:** the default view, covering what came in since your last visit.  
> * **Entity graph:** person, company, order, thread and promotion, with typed relationships.

**Changes for the browser:**

> * Mail becomes a pinned default tab and an input stream for the same agents. "What do I need to deal with today?" covers the inbox, pings and watched pages in one answer.  
> * Promotions meet browsing: when you're on a shop's site in focus mode, the agent shows the codes you have stored for that company (new).  
> * The LLM fallback moves from the Mistral API to a local model. Cloud stays opt-in.  
> * Credentials move to the OS keychain.  
> * Open from memail, per its repo docs:  
  * thread view, full bodies and reply/SMTP were specified but still pending  
  * the email-loading bug was diagnosed, not fixed  
  * classifier accuracy on real mail was never measured  
> * **POP3 and IMAP from day one.**  
  * IMAP is the recommended default: read state and folders sync with the server and other devices. Satz files promotions locally and never moves or deletes mail on the server unless the user turns that on.  
  * POP3 stays for providers without IMAP. "Leave messages on server" is forced on; read state doesn't sync.  
  * Both need app passwords for Gmail and Outlook personal accounts. OAuth sign-in is a later step.

## **5\. Shared layers**

> * **Personal index.** One local store for everything you read or received. It merges Planck's graph store (passages, co-mention edges, interest log, feedback) with memail's entity graph (people, companies, orders, promotions). Search, conversations and mail all query it, and it never leaves the machine.  
> * **Harness.** One tool set for every agent: search, read, render, extract, mail, index, and act (gated).  
> * **Read/act boundary.**  
  * Text from a page or an email never authorizes an action.  
  * An action is checked against what the user asked for and shown as a concrete line, for example "Book TP 555, 2026-03-12, €142, card ending 4242". Nothing runs until the user confirms.

### **5.1 Models: the user chooses**

Every model role has a picker. The default is local, and the choice can be set globally or per conversation.

| Role | Default | Options   |
| :---- | :---- | :---- |
| Reader (search) | Hertz int8 (if round 9 confirms), otherwise the round 5 Planck reader | Any SGS reader (Planck 1.3, Planck 1.5, Hertz, later Planck 2.0), Gemma, cloud models |
| Writer (search) | Template | Hertz or Planck writer, Gemma, cloud models |
| Agent planner (Navigator, Comparer, Watcher, Actor) | Gemma where the hardware allows | Cloud models |
| Mail classifier | Local DistilBERT | No change |
| Mail low-confidence fallback | Local model | Cloud models |
| Synthesis (long answers, "In depth" summaries) | Local model | Cloud models |

> * Cloud providers are opt-in per provider, with the user's own API key: Anthropic, OpenAI, Mistral, Google. Same pattern as memail's provider setting.  
> * The same safeguards hold whatever model is picked. Weighing is plain arithmetic, so the trust scores and the 30% cap don't depend on the model. Model writers still pass the faithfulness check or fall back to the template. The read/act boundary still applies.  
> * The card shows which model read and which wrote each answer. Comparing models on the same question is one click, carrying over the model hotswap planned for Satz and Raum in SGS.  
> * When a conversation uses a cloud model, the content sent to it (question, page passages, and mail text if mail is involved) is listed for the user to see. The personal index itself is never uploaded.

Shell (keyboard-first, tiling; Mac \+ Windows)  
  ├─ Search (home)   ├─ Mail (pinned)   ├─ Conversations (left rail)  
  │                                         └─ Focus mode: live page pane \+ agent rail  
  ▼  
Harness (one tool set, read/act boundary)  
  ├─ Agents: Reader · Navigator · Comparer · Watcher · Actor (gated)  
  ▼  
Tools  
  ├─ Brave search API          ├─ Headless engine (shares your cookie jar)  
  ├─ System webview (page pane) ├─ Mail classifier  
  ├─ POP3 / IMAP fetch          ├─ Local personal index  
  └─ Model runtime (user picks per role: SGS, local open models, cloud)

## **6\. Effort shape (reuse, don't rebuild)**

| Piece | Reuse vs. new | Rough effort   |
| :---- | :---- | :---- |
| App shell, both platforms | Reuse a cross-platform wrapper over the system webview (Tauri or similar): WKWebView on Mac, WebView2 on Windows | S |
| Page pane / focus mode | Reuse the system webview | S |
| Headless reader with your cookies | Reuse Playwright or headless WebKit; cookie-jar sharing is new | S-M |
| Shell: conversation rail, tiling, focus mode | New (this is the product) | M |
| Search: read → weigh → write | Reuse Planck 3.0 (serve.py, registry, consolidate.py, writer) | S-M (integration) |
| Trust settings \+ perspective spread | Reuse the registry and 30% blend; perspective spread is new | M |
| "For you" digest | Reuse digest.py | S |
| Mail tab | Reuse memail (server, ml-service, extraction rules, views); port from Chrome extension to a native tab | M |
| IMAP | Reuse an IMAP library; new sync of read state and flags | S-M |
| Model picker \+ provider keys | Reuse memail's provider setting and the SGS hotswap idea; new per-role picker | S-M |
| Personal index | Merge Planck's graph store with memail's entity graph | M |
| Navigator, Comparer, Watcher | Reuse Planck's typed actions and compare/watch families; multi-step navigator is new | M-L |
| Action layer \+ confirm gates | New, and the hardest to make safe | L |

Lesson from mchromium (the Mistral Browser Chromium fork, Oct 2025): forking an engine meant hours of gclient sync and 30-60 minute builds, and the demo never became a browser anyone used daily. Don't fork an engine. Wrap the system webview.

## **7\. Phases and gates (gates are proposed)**

| Phase | Scope | Gate to move on   |
| :---- | :---- | :---- |
| 0\. Shell | Conversations as tabs, focus mode, compare view, no AI beyond basics; Mac and Windows builds | Used as the only browser for 5 working days, on each platform |
| 1\. Search | Home screen on Planck; trust settings; digest | Band 9-10 ≥90% right on fresh questions; local reader within 5 pts of Gemma on the same set; ≤5 s per answer on laptop CPU |
| 2\. Mail | memail ported as the pinned tab; POP3 \+ IMAP; local fallback model | On 500 hand-labelled own emails: real email misfiled as promotion ≤1%, promotion recall ≥90%, extracted codes correct ≥90% |
| 3\. Agents (read-only) | Navigator, Comparer, Watcher; mail as an input stream | On 10 real tasks (flights, product compare, news story): faster than by hand in Chrome, with the same or a better answer |
| 4\. Actions | Actor behind confirm gates | Injection red-team suite (pages and emails with planted instructions): 0 unauthorized actions |

## **8\. Metrics**

> * **Use:** days the browser was used with no fallback to Chrome; share of sessions that touch focus mode.  
> * **Search:** accuracy and band calibration on fresh questions; cost per correct answer vs base chat; share of answers resting on 2+ independent source families.  
> * **Balance:** worst-case-profile accuracy change (rule E, ≤10 pts); share of answers flagged as changed by personal settings.  
> * **Mail:** misfiled real emails (the costly error), promotion recall, code extraction accuracy, corrections per week (should fall).  
> * **Agents:** time-to-answer vs manual on the task set; unauthorized actions (must be 0).

## **9\. Risks & Mitigations**

| Risk | Mitigation   |
| :---- | :---- |
| Prompt injection: an agent reads a hostile page or email and acts on it | Strict read/act split; page and mail text never authorizes an action; every commit confirmed against the user's own request; red-team gate before phase 4 |
| Plain browsing is worse than Chrome, so users leave | Phase 0 gate is daily use with no AI; use the system webview rather than a custom engine |
| Bot blocking and ToS friction, even through your own session | Read as the user at human pace; no evasion; fall back to search snippets (Planck is snippet-first) |
| Latency over 10-30 sources | Stream partial answers; snippet-first; local reader at \~1.3 s/question; escalate only low-confidence answers |
| A real email gets filed as a promotion and is missed | Promotions view is one click away and searchable; low-confidence mail stays in the inbox; misfile rate is the phase 2 gate |
| The trust registry reflects one person's rubric, and Satz goes public later | Scores and reasons visible; system answer always shown; registry review before public launch (section 11\) |
| Small-model reading gap vs Gemma (60.5% vs 63.4% on the same set) | Escalate below band 7; round 9 confirms on fresh questions before the reader is the default |
| POP3 limits (no sync, server-side deletion risk) | IMAP as the default; POP3 forces "leave on server"; Satz never moves or deletes server mail unless the user opts in |
| Cloud models see private content | Local default; per-provider opt-in with the user's own key; what is sent is shown per conversation; the index never leaves the machine |
| WebView2 on Windows is Chromium underneath | Accepted: the product is the conversation model, not the engine; the "not Chrome" argument is about how you browse, not what renders |
| Credential handling (memail kept them in extension storage) | OS keychain; app passwords; no credentials in the index |

## **10\. Recommendations**

> 1. Build phase 0 first, and keep it free of AI. If the shell and focus mode don't hold up as a daily browser, nothing built on top will be used.  
> 2. Make Search the home screen on the Planck stack that already ships. Swap in the Hertz int8 reader only after round 9 confirms it. Ship the model picker with Search, so other readers can be compared from the first version.  
> 3. Port memail as the Mail tab before building any multi-site agents. Mail is read-only and the hard work (classifier, extraction, views) already exists.  
> 4. Merge Planck's graph store and memail's entity graph into one local index early. It's what makes search, mail and conversations one product.  
> 5. Build actions last, behind the read/act boundary and the red-team gate.  
> 6. Don't fork an engine (lesson from mchromium).

## **11\. Decisions (owner, 2026-10-19)**

| \# | Question | Decision   |
| :---- | :---- | :---- |
| 1 | Platform | Mac and Windows |
| 2 | Planck's consumer surface | Yes, Satz is it. Every model role is user-selectable (section 5.1) |
| 3 | Personal-trust cap | 30% hard maximum, not user-adjustable |
| 4 | Mail protocol | POP3 and IMAP |
| 5 | Audience | Prototype now, public later |
| 6 | Name | Satz (reused from the SGS roadmap) |

**Before going public:**

> * Review the registry's PROPOSED rows and decide how default scores are governed and explained (already SGS open item 3).  
> * Search API cost and quota per user (Brave).  
> * Privacy policy covering cloud model use and the local index.  
> * Code signing and notarization for Mac and Windows.

## **Sources**

> * Planck 3.0: feamando/sgs → SETUP\_092026\_planck3.md, SETUP\_planck\_20261009.md (round 5 design and results), SETUP\_planck\_20261012.md (round 6), SETUP\_planck\_20261015.md (round 8), SETUP\_planck\_20261019.md (round 9), roadmap.md rows 1-planck-3-0\*  
> * memail: \~/Documents/GitHub/memail → MEMAIL\_POC\_PLAN.md, HANDOVER.md, BEADS\_CATEGORIZATION\_CACHE.md, BEADS\_RHS\_DETAIL\_PANELS.md, BEADS\_BRAIN\_GRAPH\_IMPLEMENTATION.md, ml-service/app/config.py, server/metadataRules.js  
> * mchromium: \~/Documents/GitHub/mchromium → DEMO\_STATUS.md, START\_MISTRAL\_BROWSER.md