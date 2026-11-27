---
name: satz-ui-design-i18n
description: >-
  Use this skill for any edit to src/*.ts, src/design-system/*, CSS components,
  UI copy, localization strings, or RTL layout in satz-browser.
---

# Satz UI Design System & Localization Skill

Specs: [tokens.css](../../../../src/design-system/tokens.css) · [components.css](../../../../src/design-system/components.css) · [DESIGN_SYSTEM.md](../../../../docs/design/DESIGN_SYSTEM.md) · [catalog.ts](../../../../src/i18n/catalog.ts)

## Hard Rules
1. **CSS Tokens Only:** Reference CSS custom properties from `src/design-system/tokens.css` only. Never put hardcoded hex colors (`#RGB` / `#RRGGBB`) in `src/design-system/components.css` or component renderers.
2. **Copy Hygiene:** Zero em dashes (`\u2014`) or en dashes (`\u2013`) anywhere in UI strings or `EN_CATALOG`. Use `-`, `,`, or `:` instead.
3. **Localization Wrapping:** Every user-visible UI string belongs in `src/i18n/catalog.ts` (`EN_CATALOG`) accessed via `t()`, `tCount()`, or `tDynamic()`, wrapped in `escapeHtml(...)` for innerHTML templates.
4. **RTL & Layout Classes:** Preserve `[dir="rtl"]` mirroring and prefer `components.css` utility classes over non-computed inline `style=` attributes.

## Required Verification Commands
```powershell
node scripts/i18n_extract.mjs --check
npm run build
..\sgs\.venv\Scripts\python.exe -m unittest sidecar.test_i18n -v
```
