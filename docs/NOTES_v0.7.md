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

