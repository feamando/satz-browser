# Satz (`feamando/satz-browser`)

**Satz** is a local-first, AI-native desktop browser where **conversations replace tabs**.

Instead of opening ten browser tabs and copy-pasting across sites, you open a conversation with an **intent** (for example, *"flights Berlin → Lisbon, mid-March, under €200"* or *"what's new on the Greenland story"*). Agents browse inside your own sessions, read and weigh pages, and answer with citations. At any point, one keystroke switches the conversation's viewport into **Focus Mode** (`Ctrl+F`) on the live native page—or **Compare View** (`Ctrl+M`) tiling 2 to 4 live pages side-by-side—with your conversation thread right beside you.

Satz is **Planck 3.0's consumer surface** (reusing the `Satz` name and roadmap row `11-satz-0-1` from [`feamando/sgs`](https://github.com/feamando/sgs)) and integrates the local email classification and extraction stack from [`feamando/memail`](https://github.com/feamando/memail). Everything personal—what you read, your mail, and your source trust scores—stays in a local index on your machine.

---

## Core Model: Conversations Instead of Tabs

| Chrome-shaped Browsers (Comet, Atlas, Dia) | Satz Browser |
| :--- | :--- |
| URL bar → page | Intent → conversation |
| Tabs are the unit | Conversations are the unit; pages are attached sources |
| History = list of URLs | History = a local, searchable index of everything you read and received |
| AI summarizes the current page | Agents read $N$ pages, weigh them, and answer with citations |
| Gmail is a website | Mail is a built-in pinned surface and an input stream to the same agents |
| You fill forms manually | Agents fill forms behind explicit confirmation gates (Phase 4) |

---

## Key Surfaces & Architecture

```
Shell (keyboard-first, tiling; Windows WebView2 + macOS WKWebView via Tauri v2)
  ├─ Search (home)   ├─ Mail (pinned)   ├─ Conversations (searchable left rail)
  │                                         ├─ Focus Mode: live page pane + thread/agent rail
  │                                         └─ Compare View: 2–4 live pages tiled side-by-side
  ▼
Harness (one tool set, strict read/act boundary)
  ├─ Agents: Reader · Navigator · Comparer · Watcher · Actor (confirm-gated)
  ▼
Tools & Local Storage
  ├─ Brave Search API           ├─ Headless engine (shares cookie jar)
  ├─ System WebView (page pane) ├─ Mail classifier (local DistilBERT + rules)
  ├─ POP3 / IMAP fetch          ├─ Local personal index (SQLite + graph store)
  └─ Model runtime (user-selectable per role: SGS Planck/Hertz, Gemma, or opt-in cloud)
```

### 1. Shell, Focus Mode & Compare View (Phase 0 — Current)
- **Wrapper over the System WebView:** Built on **Tauri v2** (`WebView2` on Windows, `WKWebView` on macOS) using Tauri's multi-webview API—never forking Chromium.
- **Searchable Left Rail:** Conversations hold the intent thread, attached source pages (`Pane 1`–`Pane 4`), notes, and local browsing history. Conversations can be filtered (`Ctrl+K`), created (`Ctrl+N`), pinned (`★`), or resumed anytime with their sources intact.
- **Focus Mode (`Ctrl+F`):** Switches the viewport between the conversation thread and a live native `WebView2` child pane with Back, Forward, Reload, and URL/Search bar controls (`Ctrl+L`), while keeping the conversation thread rail beside the page.
- **Compare View (`Ctrl+M`):** Tiles **2 to 4 live `WebView2` child panes** (`Alt+2`, `Alt+3`, `Alt+4`) side-by-side inside the active conversation.

### 2. Search Home Screen (Phase 1 — Built on Planck 3.0)
- **Read → Weigh → Write Pipeline:**
  - **Read:** Scores candidate answers without seeing source trust scores so user preferences cannot leak into reading.
  - **Weigh:** Merges equivalent values, deduplicates mirror families, and itemizes confidence on a `0–10` scale into bands.
  - **Write:** Uses a deterministic template writer or faithfulness-checked model writer with automatic fallback to template.
- **Neutral by Default, Rebalanceable up to 30%:**
  - Hand-scored source trust registry blended as $0.7 \times \text{system} + 0.3 \times \text{user}$ (hard 30% cap; max $\pm 3$ points).
  - The **system-only answer** is computed every time and displayed whenever personal settings change the value or band.
- **"For You" Digest & Perspective Spread:** Powered by Planck's `digest.py`, plus multi-family perspective comparison on contested topics.

### 3. Mail Pinned Tab (Phase 2 — Built on `memail`)
- **IMAP & POP3 from Day One:** IMAP is the default (syncs read state; files promotions locally without moving/deleting server mail unless opted in). POP3 forces *"leave messages on server"*. Credentials live in the OS keychain.
- **Local DistilBERT Pre-Parse:** Classifies mail into 4 labels (`email`, `ping`, `information`, `promotion`) with local LLM fallback below `0.75` confidence and retraining after 20 corrections.
- **Rule-Based Extraction (No LLM):** Extracts ping platforms, order/tracking numbers, and voucher codes.
- **Promotions Meet Browsing:** Promotions stay out of the inbox and are stored by company—when browsing a shop in Focus Mode, Satz surfaces active voucher codes for that merchant.

### 4. Agents, Model Picker & Read/Act Boundary (Phases 3–4)
- **Five Agents:** `Reader`, `Navigator`, `Comparer`, `Watcher` (read-only), and `Actor` (confirm-gated in Phase 4).
- **User-Selectable Models per Role:** Local defaults (`Hertz 1.2 int8` or `Planck` reader, `Template` writer, `Gemma` planner, `DistilBERT` mail classifier) with one-click model comparison and opt-in cloud providers using the user's own API keys.
- **Strict Read/Act Boundary:** Text from a web page or email **never** authorizes an action. Every commit action in Phase 4 is checked against the user's request and requires explicit user confirmation.

---

## Roadmap Phases & Verification Gates

| Phase | Scope | Gate to Advance |
| :--- | :--- | :--- |
| **0. Shell** *(Active)* | Conversations as tabs, Focus Mode (`Ctrl+F`), Compare View (`Ctrl+M`), local SQLite store, zero AI | Used as the only daily browser for **5 working days** ($N=5/5$, 0 Chrome fallbacks) |
| **1. Search** | Home screen on Planck 3.0, trust settings, *"For you"* digest | Band 9–10 $\ge 90\%$ accuracy on fresh questions; local reader within 5 pts of Gemma; $\le 5\text{ s}$/answer on laptop CPU |
| **2. Mail** | `memail` ported as pinned tab, IMAP + POP3, local fallback model | On 500 hand-labelled own emails: real email misfiled as promotion $\le 1\%$, promotion recall $\ge 90\%$, code extraction $\ge 90\%$ |
| **3. Agents (Read-Only)** | `Navigator`, `Comparer`, `Watcher`; mail as an input stream | Faster than manual browsing in Chrome on 10 real tasks with equal or better answers |
| **4. Actions** | `Actor` behind explicit confirm gates | Prompt-injection red-team suite (hostile pages & emails): **0 unauthorized actions** |

---

## Keyboard Shortcuts (Phase 0 Shell)

| Shortcut | Action |
| :--- | :--- |
| `Ctrl+K` | Focus the left rail search input to filter conversations |
| `Ctrl+N` | Create a new **Intent / Conversation** |
| `Ctrl+F` | Toggle **Focus Mode** (live native `WebView2` child pane + collapsible thread rail) |
| `Ctrl+M` | Toggle **Compare View** (tile 2 to 4 live `WebView2` child panes side-by-side) |
| `Alt+2` / `Alt+3` / `Alt+4` | Switch **Compare View** between 2, 3, and 4 tiled `WebView2` panes |
| `Ctrl+L` | Focus the active pane's URL / Search bar |
| `Escape` | Close inline New Intent creator |

---

## Repository Structure

```text
satz-browser/
├── .gemini/
│   └── antigravity.md           # Workspace rules & Phase 0 scope lock
├── docs/
│   └── PLANNING_v0.2.md         # Full Satz v0.2 planning specification
├── src/                         # TypeScript + Vite frontend (Main UI webview)
│   ├── main.ts                  # Conversation rail, Thread/Focus/Compare modes, IPC sync
│   ├── style.css                # Keyboard-first dark UI & multi-pane grid styles
│   └── types.ts                 # TypeScript interfaces for SQLite & WebView2 bounds
├── src-tauri/                   # Rust + Tauri v2 backend
│   ├── capabilities/
│   │   └── default.json         # Tauri v2 ACL permissions for main & child webviews
│   ├── src/
│   │   ├── db.rs                # Local SQLite store (WAL mode: conversations, pages, notes, history)
│   │   ├── webview_manager.rs   # Multi-webview child WebView2 manager (Focus & Compare panes)
│   │   ├── lib.rs               # Tauri commands & window setup
│   │   └── main.rs              # Windows application entry point
│   ├── Cargo.toml               # Rust dependencies (tauri v2 unstable, rusqlite bundled)
│   └── tauri.conf.json          # Window & bundle configuration
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

---

## Building & Running on Windows 11

### Prerequisites
- **Rust** (`cargo`, `rustc` with `x86_64-pc-windows-msvc`)
- **Node.js** (`v20+` / `v22+`) & `npm`
- **Microsoft Edge WebView2 Runtime** (pre-installed on Windows 11)

### Commands

```powershell
# 1. Install frontend dependencies
npm install

# 2. Build TypeScript & Vite frontend bundle
npm run build

# 3. Check or build the Rust / Tauri v2 backend
cargo check --manifest-path src-tauri/Cargo.toml
cargo build --manifest-path src-tauri/Cargo.toml

# 4a. Launch standalone debug executable (embeds dist/ via custom-protocol)
.\src-tauri\target\debug\satz-browser.exe

# 4b. Or run in Tauri live-reload development mode
npx tauri dev
```

### Local SQLite Database Location
On Windows, Satz automatically initializes its WAL-mode SQLite database at:
```text
%APPDATA%\com.satz.browser\satz.db
```
