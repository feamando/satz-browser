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
