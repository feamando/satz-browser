# Satz v0.7 Notes: Design System Migration

Plan: `docs/PLAN_v0.7_design_system.md` · Spec: `docs/design/DESIGN_SYSTEM.md` · Platform verified: Windows (`1440x900`)

## Verification Environment & Harness Note
- Windows screenshots (`docs/smoke/v0.7/<milestone>/windows/`) are captured against compiled `dist/` in headless Chrome (`1440x900`) using an isolated throwaway profile seeded with `docs/smoke/mail_fixture/fixture_12.json` and fictional local sources/articles (never touching production profiles).
- Every milestone is verified with `npm run build`, `cargo check --manifest-path src-tauri/Cargo.toml`, and `python -m pytest sidecar`.

## Milestone Log

### D1 · Tokens, fonts & appearance switcher
- **Files:** `index.html`, `src/style.css`, `src/state.ts`, `src/status.ts`, `src/knowledge.ts`, `src/main.ts`
- **What changed:**
  - Loaded `src/design-system/tokens.css`, `src/design-system/components.css`, then `src/style.css` in `index.html`; added `<body class="ds">` and the pre-paint `<head>` script reading `satz.ui.theme` (`system` | `light` | `dark`) and `satz.ui.layout` (`floating` | `flush`) from `localStorage`.
  - Removed the legacy `:root` palette and `*` `border-radius: 0; box-shadow: none;` reset from `src/style.css`; switched `html, body, #app` to `var(--font-ui)` and form controls to `inherit`.
  - Added Theme and Layout `.seg` controls (`aria-pressed`) in Settings (`src/knowledge.ts`) calling `scheduleWebviewLayoutSync()` on change.
  - Added startup `document.fonts.check('700 16px Besley')` check in `src/main.ts`, surfacing any warning into `state.uiErrors` in `src/status.ts`.
- **Deviations / Notes:**
  - Scoped base v0.5 element styling inside `:where(input, textarea, select, button:not(.seg > button))` in `src/style.css` so `:not(...)` does not inflate specificity above `button.active` (`0,1,1`) while keeping `.seg > button` free of legacy borders/padding.
  - Recorded Besley font check warnings in `state.uiErrors` (merged with `state.sidecar.errors` in `status.ts`) rather than adding a new sidecar error POST endpoint, preserving the Section 1 zero-IPC-change rule.
- **Checks:** `npm run build` passed; `cargo check --manifest-path src-tauri/Cargo.toml` passed; `python -m pytest sidecar` (`42 passed`); `Besley 700` & `Inter 400` verified loaded with `0` console errors; 12 baseline screenshots committed under `docs/smoke/v0.7/d1/windows/`.


### D2 · Shell, sidebar, telemetry & agent panel
- **Files:** `src/style.css`, `src/state.ts`, `src/rail.ts`, `src/status.ts`, `src/main.ts`
- **What changed:**
  - Replaced `.shell-root` / `.left-rail` / `.status-line` / `.right-panel` shell frame with v1 `.shell` grid (`#region-shell`) holding `.side` (`#region-rail`), `.main` (`#region-top`, `#region-tab-strip`, `#region-viewport`), and persistent `.agent` (`#region-agent`).
  - Wired `.shell.agent-folded` with `220ms` `grid-template-columns` transition, `transitionend` WebView2 layout sync, and persisted fold state (`satz.ui.agentFolded`); Home, Settings, Brain, Mail/News lanes, and Compose automatically fold `.agent`, while Chat (`Sources`), Email (`Email context`), Site tabs, and Compare (`Assistant`) render in `.ag-h` + `.ag-body` with `#agent-fold-btn`.
  - Refactored `src/rail.ts` with Besley wordmark canvas (`drawWordmark`), 3 compact `.icon-btn` quick actions (`Home`, `Search`, `New`), slim filter input, persisted accordions (`satz.ui.railAccordion`: `Pinned`, `Conversations`, `Sources`, `Archived`), clean `.row` / `.row.sub` items (no ASCII tree glyphs or asterisk prefixes, `.dot live` streaming & `.dot warn` watch indicators, hover `.row-menu`), footer icon controls (`Brain`, `Settings`, `Telemetry`), and monogram `.prof` menu with lock/unlock.
  - Replaced the bottom `.status-line` with `#rail-telemetry-dot` + `.telemetry-pop` (`#telemetry-popover`) anchored inside `.side` (`position: relative`), showing active model, runtime count, context budget `.meter` bar, queue/memory state, and `#status-error-log-btn` opening `.err-log-pop`.
- **Deviations / Notes:**
  - During D2–D8 transition, `#region-agent` still hosts legacy `#chat-sources-rail`, `#site-tab-agent-rail`, and `#compare-agent-rail` contents and preserves `#toggle-agent-rail-btn` in toolbars until D3 moves the panel toggle into `.top` and D4/D8 migrate inner widgets.
  - Added `.shell.agent-folded > #region-agent` zero-width/zero-gap compensation in `src/style.css` so Floating mode's right grid gap collapses cleanly without leaving a right sliver.
- **Checks:** `npm run build` passed; `cargo check --manifest-path src-tauri/Cargo.toml` passed; `python -m pytest sidecar` (`42 passed`); Besley 700 + Inter 400 loaded with `0` console errors; 12 screenshots verified under `docs/smoke/v0.7/d2/windows/`.

### D3 · Top bar & tab strip
- **Files:** `src/tabs.ts`, `src/main.ts`, `src/mail.ts`, `src/style.css`
- **What changed:**
  - Added `renderTopBar` (`#region-top`, class `.top`) with navigation arrows (`back`, `fwd`, `reload`), centered `.addr` bar (lock/globe icon, `#address-input-${tabId}` on site tabs, promo codes `.pill` + `.menu` popover, or `Mod+K` command bar trigger on Chat/Mail/News), page actions (`Fill login`, `Watch`, `Compare`, `Exit`), and `#toggle-agent-rail-btn`.
  - Migrated `renderTabStrip` (`#region-tab-strip`, class `.tabs`) to v1 `.tab` items with `.count` badges and SVG close icons; hid `#region-tab-strip` cleanly when viewing Home, Settings, Brain, or zero-tab Chat conversations (moving `#tab-strip-add-btn` to `.top-actions` when hidden).
  - Removed the legacy `.site-tab-toolbar` from `renderSiteTabViewport`, the outer toolbar from `renderCompareViewport`, and the duplicate `#toggle-agent-rail-btn` from `renderEmailTabHeaderHtml`.
- **Deviations / Notes:**
  - During D3–D5, Mail account selector pills (`All mail` + accounts) remain in `#region-tab-strip` without `[brackets]` until D6 moves account selection into `.acct-bar` inside `src/mail.ts`.
  - `#region-top` hides (`display: none`) on Home, Settings, and Brain views so each surface leads cleanly with its own header.
- **Checks:** `npm run build` passed; `cargo check --manifest-path src-tauri/Cargo.toml` passed; `python -m pytest sidecar -q` (`42 passed`); 12 screenshots verified under `docs/smoke/v0.7/d3/windows/` with `0` console errors.

### D4 · Unified composer, model menu & context pills
- **Files:** `src/chat.ts`, `src/state.ts`, `src/main.ts`, `src/style.css`
- **What changed:**
  - Refactored the Chat / Agent-rail composer (`src/chat.ts`) into v1 `.composer` with suggestion chips `.sugg` and stacked `.cbox` (`composer-ctx`, borderless auto-resizing `<textarea id="chat-composer-input" class="cbox-input">`, `.cbox-foot`).
  - Collapsed composer context `.pill` items past 2 behind `#chat-context-expand-btn` (`+N more` / `Show fewer`), tracking state in `state.composerContextExpanded` (`src/state.ts`).
  - Replaced the legacy `<select>` and `.composer-meta-row` with `#chat-model-chip` `.chip`, `#chat-model-menu` `.menu` (`[data-select-model]`, `state.composerModelMenuOpen`, outside-click / `Escape` dismissal in `src/main.ts`), `Web` / `Mail` `.chip.on` toggles, and circular `.send` / `.send.stop` (`#chat-send-btn`) inside `.cbox-foot`.
  - Added `.cbox` flex-column stacking, `.composer-ctx`, `.cbox-foot`, `.model-chip-anchor`, and `:where(...)` exclusions for `.cbox-input` and `.composer-pill-close` in `src/style.css`.
- **Checks:** `npm run build` passed; `cargo check --manifest-path src-tauri/Cargo.toml` passed; `python -m pytest sidecar -q` (`42 passed`); Besley 700 + Inter 400 loaded with `0` console errors; 12 screenshots verified under `docs/smoke/v0.7/d4/windows/`.

### D5 · Home, command bar & profile unlock
- **Files:** `src/start.ts`, `src/state.ts`, `src/main.ts`, `src/style.css`
- **What changed:**
  - Refactored `renderStartScreen` (`src/start.ts`) to v1 `.home`: uppercase mono date line, Besley 700 `.home-greet` greeting personalized with the active profile name when unlocked, unified `.bigbar` (`#start-command-bar-box` with `.bigbar-in` input `#start-main-input`, `.model-chip-anchor` `#start-model-chip` + downward `.model-menu-pop`, `#start-web-toggle` `.chip.on`, `#start-submit-btn` `.send`, and `#start-routes` `.cmd-results` `.menu-item`s with `aria-selected` & right `.end` privacy disclosure), and stacked full-width `.home-cols` (`For you` `.digest` cards with icon tiles and thumbnails above `Resume` `.row` conversations).
  - Refactored `renderCommandBarOverlay` (`#command-bar-overlay`) to `.cmd-backdrop > .bigbar.cmd-bigbar` reusing the shared `.bigbar` markup plus compact `#overlay-foryou-slot` digest list, replacing inline styles and hex colors.
  - Refactored `renderProfileUnlockOverlay` (`#profile-unlock-overlay`) and `#start-profile-unlock-card` to v1 `.modal-backdrop > .card` / `.card` using `.card-h`, `.banner`, `.form-row`, `.input.pin`, `.select`, `.btn.primary`, and `.sep`.
  - Added `state.commandModelMenuOpen` (`"start" | "overlay" | null`) in `src/state.ts` with `Escape` and outside-click dismissal in `src/main.ts`, plus `.input`/`.select`/`.bigbar-input` `:where(...)` exclusions and `.chip.on` active styles in `src/style.css`.
- **Checks:** `npm run build` passed; `cargo check --manifest-path src-tauri/Cargo.toml` passed; `python -m pytest sidecar -q` (`42 passed`); Besley 700 + Inter 400 loaded with `0` console errors; 12 screenshots verified (and `01`, `02`, `11` visually checked) under `docs/smoke/v0.7/d5/windows/`.

### D6 · Mail split view, account bar & theme-aware reader
- **Files:** `src/mail.ts`, `src/tabs.ts`, `src/main.ts`, `src/style.css`
- **What changed:**
  - Moved mail account filtering out of `src/tabs.ts` (`renderTabStrip`) into `.acct-bar` (`.pill.round` `All mail`, per-account unread counts, `Add account`, `Sync now`, `Compose`, and `Sort 10 emails`) inside `renderMailLaneView` (`src/mail.ts`).
  - Migrated Inbox and search results to two-pane `.mail-split` (`.mail-list` with `.mail-row.unread` / `.read` / `.on` + inline `.mail-read` reading pane using `renderEmailTabHeaderHtml`, `.extract` action cards, and `.email-frame`), preserving `j`/`k`/`Enter`/`r`/`c`/`e`/`1-4`/`/` shortcuts and double-click/`Open tab` navigation.
  - Migrated Pings, Orders, Promos grouped `.card`s (`.extract` tracking bar, `.pill` promo copy chips), Accounts `.table-wrap > .table` and `.form-row` add-account card, Eval Mode `.seg` controls, `.banner.warn` locked-mail inline PIN unlock card, `#email-focused-rail-cards`, and Compose `.draft` two-step send-gate & undo banners.
  - Added `buildMailIframeSrcdoc` (`src/mail.ts`) reading computed CSS theme tokens (`--panel`, `--ink`, `--accent`, `--muted`, `--line`) with `<meta name="color-scheme">` and runtime stylesheet overrides over sidecar HTML, plus `MutationObserver` on `data-theme` in `src/main.ts` so `.email-frame` tracks light/dark transitions immediately; removed bracket labels in `src/main.ts` & `src/mail.ts`.
- **Deviations / Notes:**
  - Because `sidecar/satz_mail.py` injects a legacy terminal `<style>` block (`#000000` / `#e8e8e8`), `buildMailIframeSrcdoc` appends a computed theme override `<style>` block inside `srcdoc` rather than altering sidecar HTML sanitization tests.
- **Checks:** `npm run build` passed; `cargo check --manifest-path src-tauri/Cargo.toml` passed; `python -m pytest sidecar -q` (`42 passed`); Besley 700 + Inter 400 loaded with `0` console errors; 12 screenshots verified (`05`, `06` visually checked) under `docs/smoke/v0.7/d6/windows/`.

### D7 · News story cards, perspectives, reader, topics & sources
- **Files:** `src/news.ts`, `src/state.ts`, `src/main.ts`, `src/style.css`
- **What changed:**
  - Migrated News story cards (`src/news.ts`) to v1 `.story` grid (`DESIGN_SYSTEM.md` §5.14) with full-color `.story-thumb`, `.story-meta` + `.conf` bar (`--c` percentage + `.conf.low`), `.story-title`, max-3 bullet `ul`, `.story-match` with `.flag`, and single-line `.story-foot` (up to 2 family `.pill`s + expandable `+N`, 3 primary actions `Open reader` / next best action / `Save`, and overflow `more` `.menu` managed via `state.newsStoryMenuId` with Escape and outside-click dismissal in `src/main.ts`).
  - Migrated Perspectives lane to `.persp-grid` with computed `style="--cols:${gridCols};"`, Reader overlay to `.card` + `.reader`, Topics to `.source-row` + `.form-row`, and Sources trust registry to `.table-wrap > .table` with `.slider-row` / `.slider` displaying system-only trust alongside personal sliders and effective trust (`30%` max blend).
  - Removed all 6 non-computed inline `style=` attributes, hex colors, grayscale thumbnail filters, and bracket button copy from `src/news.ts`.
- **Checks:** `npm run build` passed; `cargo check --manifest-path src-tauri/Cargo.toml` passed; `python -m pytest sidecar -q` (`42 passed`); Besley 700 + Inter 400 loaded with `0` console errors; 12 screenshots verified (`03`, `04` visually checked) under `docs/smoke/v0.7/d7/windows/`.

### D8 · Chat thread, Sources, Brain, Settings & Compare tiles
- **Files:** `src/chat.ts`, `src/sources.ts`, `src/knowledge.ts`, `src/main.ts`, `src/style.css`
- **What changed:**
  - Migrated Chat thread (`src/chat.ts`) to `.chat-stage` > `.thread-scroll` > `.thread` with `.msg-you`, `.msg-bot`, `.msg-meta`, `.msg-sources`, `.stream` live status box (`.dot.live`, `.stream-step`), `.banner.danger` errors, `.cite` / `.cite.flagged` buttons (for sources and `[B#]` brain memory citations), `.findings` / `.finding`, `.preview-grid`, `.video-grid`, `.card.inset` + `.table-wrap > .table` audit & markdown tables (removing all 4 inline `style=` attributes), `.draft` task confirmation gates, and `.chat-inline-email` + `.attach-img` / `.attach-embed`.
  - Refactored `src/sources.ts` to render `.source-row` items inside `#region-agent` using icon toggles (`.src-ctx-btn`), `.cite` badges, and `.flag` cut markers.
  - Migrated Settings & Brain views (`src/knowledge.ts`) to `.kb-page` > `.view-h`, `.acc` accordions, `.form-row` / `.input` / `.select` / `.btn` / `.textarea.mono`, `.slider-row` / `.slider` domain trust table (preserving 30% max blend and system-only scores), and `.source-row` entity/passage/search results; removed the remaining inline `style=` attribute (`line 192`).
  - Migrated `renderCompareViewport` (`src/main.ts`) to `.compare-view` > `.compare-grid` with `.compare-tile > .tile-h` SVG navigation controls + `.tile-addr` inputs; added scrollable viewport rules for `.home` and `:where(button:not(..., .cite))` exclusion in `src/style.css`.
- **Checks:** `npm run build` passed; `cargo check --manifest-path src-tauri/Cargo.toml` passed; `python -m pytest sidecar -q` (`42 passed`); `0` hex literals across `src/*.ts`; Besley 700 + Inter 400 loaded with `0` console errors; 12 screenshots verified (`01`, `07`, `08`, `10`, `12` visually checked) under `docs/smoke/v0.7/d8/windows/`.
