# Satz v0.3 Execution Notes

Owner: Nikita Gorshkov · Date: 2026-10-20 · Target: Windows 11 (4090 box) first, macOS second

## Milestone 1 (M1): Terminal Theme, Monospace Font, CSS Tokens, Module Split

- **Theme & Typography:**
  - Bundled `JetBrainsMono-Regular.woff2` and `JetBrainsMono-Bold.woff2` locally in `public/fonts/`.
  - All colour literals restricted to `:root` in `src/style.css` (`#000000`, `#0d0d0d`, `#1a1a1a`, `#333333`, `#777777`, `#e8e8e8`).
  - Zero inline `style="` attributes across `src/`.
  - Active/selected items use inverse video (`background: var(--fg); color: var(--bg)`).
- **Module Split:**
  - Split monolithic `src/main.ts` into 11 focused TypeScript modules: `types.ts`, `state.ts`, `api.ts`, `keys.ts`, `status.ts`, `rail.ts`, `start.ts`, `tabs.ts`, `chat.ts`, `sources.ts`, and `knowledge.ts`.
  - Replaced `intent` terminology with `conversation` across the UI; `src/api.ts` retains a single v1->v2 migration fallback line (`raw.title ?? raw.intent_title`).
  - Freed `Mod+F` (`Ctrl+F` on Windows, `Cmd+F` on macOS) for native find-in-page.
