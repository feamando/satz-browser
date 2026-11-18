# Satz v0.7 Plan: Design System Migration

Author: Nikita Gorshkov (with Claude) · 2026-11-18 · Status: Ready for execution · Executor: Gemini / Antigravity · Follows: `docs/PLAN_v0.6_satz_news.md`

**TL;DR.** Move every screen from the v0.5 terminal look to the v1 design system (`docs/design/DESIGN_SYSTEM.md`) in 9 milestones (D1 to D9), one commit each. The tokens, component CSS, logo and icons already exist in `src/design-system/`, so this plan is about rewiring markup, not inventing styles: `tokens.css → components.css → shell → composer → home → mail → news → chat/brain/compare → cleanup`. No behavior changes. Every IPC call, element id the code queries, shortcut, privacy disclosure and send gate stays as it is. Done means `npm run build` passes, both themes and both layouts are checked, and the per-milestone screenshots are committed.

## 0. Read first

1. `docs/design/DESIGN_SYSTEM.md` section 1 (rules) and the section for the screen you are touching. The class you need is almost always already there.
2. `docs/design/components.html` (open in a browser): every v1 component, rendered from the real CSS. If your markup does not look like the gallery, your markup is wrong, not the CSS.
3. `docs/design/satz-directions.html`: full-screen mocks of Home, News and Mail in both themes and both layouts. This is the target look.
4. `src/design-system/components.css`: the only place component styles live. Add to it if a component is missing; do not add styles to `src/style.css` except during the D1 to D8 transition.

## 1. Non-negotiables

- **No behavior changes.** Same IPC, same state, same event bindings. If a binding uses an element id (`getElementById`, `querySelector("#...")`), keep that id on the new element. If it uses a class selector (for example `[data-chat-suggest]`, `.rail-row[data-conv-id]`), keep the `data-*` attribute; classes may change only if you update the selector in the same commit.
- **Native webviews are not DOM.** Live sites render in native WebView2 or WKWebView windows positioned from `.webview-slot` via `getBoundingClientRect()` (`src/tabs.ts:259-268`, `scheduleWebviewLayoutSync`). CSS radius cannot clip them. Keep `.webview-slot` rectangular, keep its id and keep calling `scheduleWebviewLayoutSync()` after any layout change (agent fold, sidebar accordion, theme switch, layout switch). In floating layout the slot sits inside the `--r-lg` main card with its top edge flush against the address bar and an 8px inner inset on the other three sides, so the square corners do not poke out.
- **Tokens only.** No hex values in `src/*.ts`. The 26 inline `style=` attributes listed in section 4 go away as you touch each file.
- **Copy.** No em or en dashes, no emoji. Bracket labels like `[open reader]` become plain words (`Open reader`). Keep every `title` tooltip and every privacy line.
- **Local only.** No new dependencies. Fonts are bundled in `public/fonts/` (Inter and Besley variable, latin and latin-ext). Do not load Google Fonts in the app.
- **Checks per milestone:** `npm run build`, `cargo check --manifest-path src-tauri/Cargo.toml`, the sidecar tests (`python -m pytest sidecar`), then the screenshot set in section 3 on your platform. Record deviations in `docs/NOTES_v0.7.md`.

## 2. Milestones

### D1. Tokens and fonts in (S)

- `index.html`: load `/src/design-system/tokens.css`, then `/src/design-system/components.css`, then `/src/style.css` (the order matters).
- `src/style.css`: delete the `:root` palette block (lines 17-25) and the `border-radius: 0;` and `box-shadow: none;` lines from the `*` reset (lines 27-33). Keep `box-sizing`, `margin` and `padding`. The aliases at the end of `tokens.css` (`--bg`, `--surface`, `--border`, `--fg`) keep the old rules working on the new palette.
- `html, body, #app`: `font-family: var(--font-ui)`; `input, button, textarea, select`: `font-family: inherit`. Keep the JetBrains Mono `@font-face` blocks.
- Add `<body class="ds">` in `index.html`.
- Settings: add Theme (System, Light, Dark) and Layout (Floating, Flush) controls as `.seg` in the existing settings or knowledge view, writing `data-theme` and `data-layout` on `<html>` and persisting to the profile settings store. Default: theme follows the OS, layout floating.
- Check: the app looks like v0.5 with paper or violet-black colors and Inter. Nothing is broken. This is the safety net for D2 to D8.

### D2. Shell, sidebar and telemetry (L)

Files: `src/main.ts` (`mountShellSkeleton` at line 703 and the `render*Region` functions), `src/rail.ts`, `src/status.ts`, `src/state.ts` (new UI state keys).

- New skeleton:
  ```html
  <div class="shell" id="region-shell">
    <aside class="side" id="region-rail"></aside>
    <main class="main" id="region-main">
      <header class="top" id="region-top"></header>
      <nav class="tabs" id="region-tab-strip"></nav>
      <div class="main-body" id="region-viewport"></div>
    </main>
    <aside class="agent" id="region-agent"></aside>
  </div>
  ```
  Keep `region-rail`, `region-tab-strip`, `region-viewport`. `region-status-bar` is removed; `renderStatusLine()` now renders into the telemetry popover (below), so keep the function name and every call site.
- `renderRail` (`rail.ts:28`): rebuild per DESIGN_SYSTEM 5.2. Brand row draws the wordmark with `drawWordmark(canvas, { height: 22, theme, variant: "backdrop" })` after `await fontsReady()` (redraw on theme change). Quick actions become three `.icon-btn` with the existing ids `rail-home-btn`, `rail-open-command-bar-btn`, `rail-new-conv-btn`, shortcuts in `title`. The brand keeps `rail-brand-home-btn` (now a `<button>` around the canvas). Keep `rail-toggle-archived` on the Archived accordion header, `rail-open-brain-btn` and `rail-open-knowledge-btn` on the footer buttons, and `rail-empty-pinned` / `rail-empty-recent` on empty states (text "No pinned conversations", "No recent conversations"). Groups become `.acc` sections Pinned, Conversations, Sources (bookmarks), Archived; store open or closed state in `state.railAccordion` and persist it. Pinned order: Mail, News, `.sep`, user pins. Rows use `.row`; keep `data-conv-id`, `data-mail-rail-all`, `data-remove-bookmark`, `data-menu-conv-id` and the rename input id pattern. The `[pin]` and `...` text become the `more` icon button opening a `.menu`. The running `[...]` badge becomes `<i class="dot live">`. `[watch !]` becomes `<i class="dot warn" title="watched value changed">`. Mail accounts render as `.row.sub` (drop the `branchGlyph`).
- Footer: `.icon-btn` for Brain (keep the existing Brain and Knowledge toggle handlers), Settings, Telemetry (`id="rail-telemetry-btn"`), profile chip with avatar initial and the lock action in its menu.
- `status.ts`: `renderStatusLine()` renders the `.telemetry-pop` content per DESIGN_SYSTEM 5.4 into `#region-telemetry` (an absolutely positioned child of `.side`, hidden unless `state.telemetryOpen`). It also sets the dot class on `#rail-telemetry-btn` (`good`, `warn`, `danger`). `renderErrorLogOverlay()` becomes the error log panel (5.12) opened from the popover's Log row. Escape and outside clicks close the popover.
- Agent panel: create `#region-agent` and move the `right-panel` rails into it (`chat-sources-rail`, `site-tab-agent-rail`, `compare-agent-rail` are created inside `renderViewportRegion` today, at `main.ts:1313`, `1441`, `1557` and `1621`). Header per 5.10 with the fold button. `state.agentFolded[viewKey]` toggles `.shell.agent-folded`; defaults: home folded, everything else open. Call `scheduleWebviewLayoutSync()` after the 220ms transition ends (`transitionend` on `.shell`).
- Check: rail, telemetry popover, fold and unfold, accordion open and close, rename, pin and unpin, archive and delete, mail account switching, all shortcuts (⌘K, ⌘N, ⇧⌘H, ⌘B, ⌘D).

### D3. Top bar and tab strip (M)

Files: `src/tabs.ts` (`renderTabStrip` at line 16), `src/main.ts` (`renderSiteTabViewport` at line 1350, `.site-tab-toolbar` at lines 1482, 1584 and 1594).

- `#region-top`: back, forward, reload `.icon-btn` and the `.addr` bar (5.3), then bookmark `star` (moves `rail-bookmark-current-btn`, ⌘D, keep the id) and compare `compare`. The address input keeps its current id and handlers. The leading icon follows the active view (`home`, `news`, `lock` for mail, `globe` for sites).
- `#region-tab-strip`: conversation lane tabs and open site tabs as `.tab` (5.5). Keep `data-tab-id` and close handlers; `selected-compare` becomes `.tab.compare-pick`. Hide the strip when the view has only one tab (Home).
- Remove the per-viewport `.site-tab-toolbar`; its controls are now in `#region-top`.
- Check: open 4 site tabs, close one, switch tabs, compare-select two tabs, and confirm the native webview still lines up with `.webview-slot` in both layouts and after resizing the window.

### D4. Composer (M)

Files: `src/chat.ts` (`renderChatPanel` composer at lines 298-330, suggestions at 212-225), `src/start.ts` controls rows (lines 332-354 and 536-556).

- Build one helper `renderComposerHtml({ inputId, placeholder, suggestions, showAttach, showModel })` in `src/chat.ts` per 5.6 and use it in chat, mail chat, news chat and the agent panel. Keep `#chat-composer-input` and the `data-chat-suggest` attribute on suggestion buttons.
- The model `<select>` (`#chat-model-select`, `#start-model-select`, `#overlay-model-select`) becomes a model `.chip` opening a `.menu` of models grouped Local and Cloud, each item with its privacy summary in `.end`. Keep the ids on the chip buttons and the same change handler (dispatch the same state update).
- Context pills (`composer-context-row`) render inside `.cbox` before the input. More than 3 collapse into `+N`.
- Remove `.composer-meta-row`. Its text (`models [ok] · privacy`) moves to the model chip `title`.
- Send becomes `.send`. If chat streaming already has a cancel path, show the stop state (`.send.stop`) while streaming and reuse it; if not, keep send disabled while streaming. Do not add a new cancel IPC in this plan. Task cards keep their own stop and cancel (`data-task-stop`, `data-task-cancel`).
- Check: send, stop, Enter versus Shift+Enter, suggestions, attaching tab context, switching models, and the privacy text in the tooltip.

### D5. Home and command bar (M)

File: `src/start.ts` (`renderStartScreen` at line 221, `renderCommandBarOverlay` at line 490, `renderProfileUnlockOverlay` at line 729, `renderDigestItemsHtml` at line 59).

- Start screen per 5.8: date line, Besley greeting, `.bigbar` with the existing input id `start-main-input` (line 320) and box id `start-command-bar-box`; drop the `>` prompt and the `caret-blink` span, two `.home-cols` (For you uses `.digest`, Resume uses `.row`). Keep `data-resume-id` and the digest click handlers. `updateStartDigestInPlace` must target the new list container id.
- Digest kind (`mail`, `news`, `bookmark`, `page`) maps to the `.digest-src` icon. Thumbnails become `.digest-thumb` / `.digest-thumbs`.
- Profile unlock card (line 243) and the startup modal (line 758) per 5.8 and 5.12, using `.card`, `.form-row`, `.input.pin`, `.btn.primary`. Remove all 14 inline styles in this file.
- Command bar overlay per 5.7: `.cmd-backdrop > .bigbar` with `.cmd-results` grouped by `.label`. `renderRoutesListHtml` (line 189) renders `.menu-item`s; the selected route gets `aria-selected="true"`, and the privacy disclosure goes in `.end`.
- Check: ⌘K from every view, arrow-key route selection, Enter, Escape, unlock with PIN, create profile, Touch ID button on macOS.

### D6. Mail (L)

File: `src/mail.ts` (`renderMailLaneView` at line 655, `renderInboxRowsHtml` at line 1238, `renderEmailTabHeaderHtml` at line 1281, `renderMailAccountsSectionHtml` at line 187, `renderMailEvalPanelHtml` at line 547, `renderEmailAgentRailCardsHtml` at line 1367, `renderComposeTabView` at line 1427).

- Account filter `.acct-bar` with `.pill.round` (All mail plus accounts) and `Sync now`.
- Inbox: `.mail-split` with `.mail-list` of `.mail-row` (5.13) and the reading pane `.mail-read`. Keep `data-*` attributes on rows. Unseen maps to `.dot.accent` and bold; selected maps to `.on`.
- Email tab header becomes `.mail-subject` + `.mail-from`; the HTML body iframe becomes `.email-frame` (keep the sandbox attributes and CSP exactly). Set the iframe's `color-scheme` from the active theme.
- Extracted actions (dates, tracking) become `.extract` with one primary button.
- Pings, Orders, Promos lanes: grouped `.card`s; promo codes in a mono `.pill`; tracking as `Track` `.btn`.
- Accounts section: `.table` in a `.table-wrap` plus an add-account `.card` with `.form-row`s. Eval mode per 5.13 with `.seg` labels and the existing keyboard shortcuts.
- Compose and reply drafts use `.draft` with the send-gate line. The send button still requires the explicit click; do not change the confirm flow.
- Locked state: `.banner` plus the inline PIN form.
- Check against the fixture (`docs/smoke/mail_fixture/`): all lanes render, selecting rows, reply draft, attachments preview, eval labelling with keys 1 to 4 and y or n.

### D7. News (L)

File: `src/news.ts` (`renderStoryCardsHtml` at line 83, `renderBandPillHtml` at line 77, `renderPerspectivesLaneHtml` at line 178, `renderTopicsLaneHtml` at line 267, `renderSourcesLaneHtml` at line 311, `renderReaderOverlayHtml` at line 399, `renderNewsLaneView` at line 432).

- **Story card exactly per DESIGN_SYSTEM 5.14 and the gallery.** This layout was reviewed and fixed, so do not improvise:
  - `.story` grid with `.story-thumb` (drop the grayscale filter) and `.story-c`.
  - Meta line: status, topic, `.conf` pushed right. `renderBandPillHtml` returns `.conf` with `--c` set to the confidence percentage; low bands add `.conf.low`.
  - Headline `.story-title`, bullets `ul` (max 3), Brain match line `.story-match` with `.flag` for outside usual sources.
  - `.story-foot`: at most 2 family `.pill`s plus `+N` (title lists the rest), then 3 actions (`Open reader` as `.btn-text.pri`, then Perspectives, Translate or Ask in chat by availability, then `Save`), then a `more` `.icon-btn` whose `.menu` holds Compare, Ask in chat, Less like this and Hide. Keep every `data-news-*` attribute on the moved buttons.
- Perspectives: `.persp-grid` with `--cols` set from `gridCols` (replaces the inline `grid-template-columns`), each family a `.card`, agreed facts and blind spots as `.section`s.
- Reader: `.reader` inside a `.card`; translate action as `.btn`; audit as a `.section`.
- Topics and Sources lanes: `.form-row`, `.table`, `.slider` with the 30% cap note. Personal trust must still show next to system trust wherever it changes a result.
- Remove the 6 inline styles in this file.
- Check: Top stories with 1, 2 and 4+ families, a German story (translate), perspectives with 2 and 4 columns, reader open and close, track and remove a topic, a slider change, and confirm the system-only value is still shown.

### D8. Chat details, Brain, Knowledge, Compare (M)

Files: `src/chat.ts` (`renderMessageBlock` at line 454, `renderAnswerMetaSectionHtml` at line 808, `renderChatEmailCardsHtml` at line 906, `renderTaskCardBlock` at line 1028, `formatCitationsInText` at line 1123, `renderMarkdownTablesInHtml` at line 1085), `src/sources.ts`, `src/knowledge.ts` (`renderKnowledgeView` at line 48, `renderBrainView` at line 909), `src/main.ts` (`renderCompareViewport` at line 1571).

- Messages: `.thread`, `.msg-you`, `.msg-bot` with `.msg-meta`, `.msg-text`, `.msg-sources`. Streaming status as `.stream` (keep the ids `updateStreamingStatus` and `tickStreamingElapsed` write to). Errors become `.banner.danger` with Retry.
- `formatCitationsInText` emits `.cite` (and `.cite.flagged` for flagged); keep the click data attributes.
- Findings, page previews, videos, attachments, inline email bodies, task cards and drafts per 5.9. Markdown tables use `.table` inside `.table-wrap`. Answer meta tables (inline styles at `chat.ts:835-866`) become `.card` + `.table`.
- Sources panel (`sources.ts`) renders `.source-row`s into the agent panel's Sources tab.
- Brain and Knowledge: `.view-h`, `.card`, `.table`, proposals with Accept and Reject, vault JSON in `.textarea.mono`. Memory citations `[B1]` become `.cite`.
- Compare: `.compare-grid` with `.compare-tile > .tile-h` + `.webview-slot`. Re-run the webview layout sync.
- Check: a cited answer, a streaming answer, an error, findings, a video, a PDF attachment, a task card confirm, Brain entity view, accept and reject a proposal, compare with 2, 3 and 4 panes.

### D9. Cleanup and handover (S)

- Delete every v0.5 class in DESIGN_SYSTEM section 7 that `grep -rn "<class>" src/` no longer finds, then remove the matching rules from `src/style.css`. Goal: `style.css` keeps only the JetBrains Mono `@font-face` and anything section 7 marks Keep that is not already in `components.css`; move those, then delete `style.css` and its link.
- Remove the compatibility aliases at the end of `tokens.css`.
- Confirm `grep -nE "#[0-9a-fA-F]{3,6}\b" src/*.ts` returns nothing and `grep -n 'style="' src/*.ts` returns only computed values (`--c`, `--v`, `--cols`).
- Update DESIGN_SYSTEM section 7 if any mapping changed during the work, and bump its version line.
- Write `docs/NOTES_v0.7.md`: what changed, deviations, open issues.

## 3. Screenshot set per milestone

Save to `docs/smoke/v0.7/<milestone>/<os>/`, using the mail fixture and a throwaway profile (fictional data only):

1. `01_home_light_floating.png`, `02_home_dark_flush.png`
2. `03_news_top_stories_light.png`, `04_news_top_stories_dark.png`
3. `05_mail_inbox_light.png`, `06_mail_inbox_dark.png`
4. `07_chat_cited_answer.png`
5. `08_site_tab_agent_open.png`, `09_site_tab_agent_folded.png`
6. `10_telemetry_popover.png`
7. `11_command_bar.png`
8. `12_compare_3_panes.png`

D1 takes all 12 as the baseline. Later milestones retake only the ones that changed and the ones the milestone's checks list.

## 4. Inline styles to remove

| File | Lines | Replace with |
|---|---|---|
| `src/start.ts` | 195, 204, 210 | `.cmd-results`, `.menu-item[aria-selected]`, `.end` |
| `src/start.ts` | 243, 282 | `.card`, `.form-row` gap |
| `src/start.ts` | 514, 515, 536 | `.cmd-backdrop > .bigbar` |
| `src/start.ts` | 758, 759, 765, 771, 772, 797 | `.modal-backdrop > .card`, `.card-h`, `.banner`, `.form-row`, `.sep` |
| `src/news.ts` | 231, 258 | `.section` |
| `src/news.ts` | 236 | `.persp-grid` with `style="--cols:N"` |
| `src/news.ts` | 252 | `ul` inside `.card` |
| `src/news.ts` | 343, 452 | `.form-row`, `.card-h` |
| `src/chat.ts` | 835, 839, 849, 866 | `.card` + `.table-wrap > .table` |
| `src/knowledge.ts` | 185 | `.form-row` |
| `src/rail.ts` | 49 | Brand row button with the wordmark canvas |

## 5. Effort shape

| Piece | Reuse vs. new | Rough effort |
|---|---|---|
| D1 Tokens and fonts | Reuse `tokens.css`, aliases keep v0.5 working | XS |
| D2 Shell, sidebar, telemetry, agent | Reuse `components.css` 5.2, 5.4, 5.10; new state keys | L |
| D3 Top bar, tabs | Reuse 5.3, 5.5; move toolbar out of viewports | M |
| D4 Composer | Reuse 5.6; one shared helper replaces three copies | M |
| D5 Home, command bar | Reuse 5.7, 5.8 | M |
| D6 Mail | Reuse 5.13 | L |
| D7 News | Reuse 5.14, card layout already fixed | M |
| D8 Chat, Brain, Compare | Reuse 5.9, 5.11, 5.15, 5.16 | M |
| D9 Cleanup | Delete | S |

## 6. Recommendations

1. Execute D1 to D9 in order, one commit each, and never batch two milestones. D1 is the rollback point.
2. Before each milestone, open `docs/design/components.html` and the matching mock in `satz-directions.html` side by side with the running app.
3. When a component is missing from `components.css`, add it there with tokens and a gallery entry (`scripts/build_components_gallery.py`), and add a line to DESIGN_SYSTEM section 5. Do not style it locally.
4. Ask before changing anything listed in section 1. Those are product decisions, not design decisions.

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Native webview misaligned after layout changes (fold, accordion, theme) | Call `scheduleWebviewLayoutSync()` on `transitionend` and after every region render; screenshot 08 and 09 in both layouts |
| Event bindings break when markup changes | Keep ids and `data-*` attributes; grep each removed class for selectors in `main.ts` before deleting it |
| Email HTML bodies unreadable in dark mode | Set iframe `color-scheme`; keep the sandbox CSP; offer the existing plain-text view as a fallback |
| Telemetry hidden means users miss errors | Status dot on the telemetry icon (`warn` or `danger`), plus a `.banner.danger` in the view when the sidecar is offline |
| Fonts fall back silently | Fonts are bundled; check `document.fonts.check('700 16px Besley')` once at startup and log to the error ring if false |
| Scope creep into behavior | Section 1 non-negotiables; PRs that change IPC or state shape get split out |
