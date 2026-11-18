# Satz Design System

Version 1.1 · 2026-11-19 · Status: migrated (D1-D9 complete) · Owner: Nikita Gorshkov

**TL;DR.** Satz moves from the v0.5 terminal look (black, monospace everywhere, square corners) to a calmer reading tool: paper light and violet-black dark themes, Inter for UI, Besley for display, JetBrains Mono kept only for data, and mildly rounded corners. Telemetry leaves the status bar and moves into a popover, the composer puts the prompt first, the sidebar becomes an accordion, and the on-tab agent folds to a strip. This file is the spec for every component the app uses today. Tokens live in `src/design-system/tokens.css`, the logo in `src/design-system/brand.ts`, icons in `src/design-system/icons.ts`. Component styles live in `src/design-system/components.css`, rendered in the gallery `docs/design/components.html` (regenerate with `python3 scripts/build_components_gallery.py`). Full-screen mocks are in `docs/design/satz-directions.html`. The step-by-step migration is `docs/PLAN_v0.7_design_system.md`.

This document is written for coding agents (Gemini / Antigravity) and humans. Section 1 is the rule set. Read it before touching any UI file.

## 1. Rules for agents

1. **Tokens only.** Components use semantic tokens (`--canvas`, `--panel`, `--sunk`, `--hover`, `--line`, `--ink`, `--muted`, `--faint`, `--accent`, `--accent-ink`, `--accent-soft`, `--good`, `--warn`, `--danger`). Never write a hex value, `rgb()` or `#000000` in `src/*.ts` or component CSS. The brand ramp (`--violet-*`, `--dither-*`) is for the logo and charts only.
2. **No inline `style="..."` for color, font, radius or spacing.** There are 26 inline styles today (`start.ts` 14, `news.ts` 6, `chat.ts` 4, `rail.ts` 1, `knowledge.ts` 1). Replace each with a class when you touch that file. Inline `style` is allowed only for computed values (grid column counts, progress widths via a CSS variable like `style="--c:78%"`).
3. **Three fonts, three jobs.**
   - `--font-ui` (Inter): everything by default.
   - `--font-display` (Besley 700): the wordmark, the home greeting, view titles, the email subject in the reader. Never body text, never buttons, never below 15px.
   - `--font-mono` (JetBrains Mono): data only. Timestamps, counts, trust scores, confidence, URLs and the address bar, keyboard hints, model ids, section labels (uppercase micro labels). If it is not a number, a URL, an id or a micro label, it is not mono.
4. **Radius by role** (section 2.4). Do not round everything the same. Rows 9px, pills 7px, cards and composer 12px, home bar 16px, count badges fully round.
5. **Both themes, always.** Every change is checked in light and dark. Light is the paper theme, never pure white. Dark is violet-black, never pure black.
6. **Bracket labels become text.** v0.5 used `[open reader]`, `[sync now]`, `[x]`. In v1, actions are plain words (`Open reader`, `Sync now`) styled as `.btn`, `.btn-text` or an icon button with a `title`. Brackets remain only for status inside mono data (none planned).
7. **Copy rules (unchanged).** No em dashes or en dashes. No emoji. Sentence case. Lowercase is no longer mandatory; use normal capitalization (`Mail`, `Sources in context`). Buttons say exactly what happens.
8. **Trust and privacy are never hidden.** Hiding telemetry means moving it, not deleting it. Privacy disclosures (on-device vs cloud), system-only vs personal trust, `[unsourced]` and `cut` badges, and the send gate stay visible where they are today.
9. **Keyboard shortcuts stay.** `MOD_LABEL` hints move from inline text into `title` attributes and the `.kbd` chip (section 5.1). Do not remove a shortcut.
10. **Accessibility.** Visible focus ring on everything focusable (`:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px }`). Icon-only buttons need `title` and `aria-label`. Hit targets at least 28px. `--faint` text only at 10.5px+ and never for anything the user must read to act.
11. **Reduced motion.** Use `--dur` and `--dur-fast` only. They drop to 0 under `prefers-reduced-motion`.
12. **Done means** `npm run build` passes, both themes checked, both layouts checked (floating and flush), and the component's row in section 7 still matches the code.

## 2. Foundations

### 2.1 Color

Semantic tokens, light (paper) and dark:

| Token | Light | Dark | Use |
|---|---|---|---|
| `--canvas` | `#e9e4da` | `#0b0a0e` | App background behind floating panels |
| `--panel` | `#fbf8f2` | `#16141b` | Content, agent panel, composer, cards |
| `--sunk` | `#f3efe7` | `#1b1821` | Recessed: address bar, pills, quotes, drafts |
| `--hover` | `#ede8de` | `#221f29` | Hover fill on rows, buttons, list items |
| `--line` | `#e2dbce` | `#2a2631` | All borders and hairlines (1px) |
| `--ink` | `#1f1b22` | `#e9e6ef` | Primary text |
| `--muted` | `#756d72` | `#8e8899` | Secondary text, previews, inactive tabs |
| `--faint` | `#a8a09f` | `#5f5a69` | Micro labels, meta, placeholders |
| `--accent` | `#5b3f99` | `#b79ef0` | Send button, active tab underline, unread dot, primary button |
| `--accent-ink` | `#ffffff` | `#17121f` | Text on `--accent` |
| `--accent-soft` | `#ebe3f3` | `#2a2238` | Selected row, active nav icon, citation chip |
| `--good` | `#2f8a5b` | `#5fc28d` | Ready, synced, healthy dot |
| `--warn` | `#b07a1f` | `#e0a94a` | Developing story, no key, degraded |
| `--danger` | `#b23a3a` | `#ef7d7d` | Errors, failed send, sidecar crash |
| `--glass` | 74% panel | 66% panel | Popover background with `backdrop-filter: blur(16px) saturate(1.3)` |

Rules:
- One accent. Purple marks "this is active / this is the primary action / this is Satz talking". Do not use it for decoration.
- Semantic colors (`good`, `warn`, `danger`) appear as 6px dots or text, never as large fills.
- Selected state is `--accent-soft` fill plus `--ink` text. The v0.5 inverted row (white fill, black text) is retired.

Brand ramp (logo and charts only): `--violet-900 #3f2775`, `--violet-700 #5b3f99`, `--violet-500 #8466c2`, `--violet-400 #ad95de`, `--violet-300 #cdbdec`, `--dither-200 #ddd6e8`, `--dither-100 #e7e5eb`.

### 2.2 Typography

| Token | Size | Typical use | Font |
|---|---|---|---|
| `--fs-micro` | 10.5px | Uppercase section labels (letter-spacing `--tracking-label`), kbd, counts in tabs | mono |
| `--fs-xs` | 11.5px | Meta lines, timestamps, card sublines | ui or mono |
| `--fs-sm` | 12.5px | List rows, pills, agent panel, mail list | ui |
| `--fs-base` | 13px | Default | ui |
| `--fs-md` | 13.5px | Composer input, email body, chat answers | ui |
| `--fs-lg` | 15px | Story headline, home command bar | ui 600 |
| `--fs-xl` | 20px | Email subject, view title | display 700 |
| `--fs-2xl` | 30px | Home greeting | display 700 |

Weights: Inter 400 body, 500 labels and buttons, 600 titles and unread senders. Besley 700 only. Line height `--lh-ui` (1.45) for UI, `--lh-read` (1.6) for email and article text, `--lh-tight` (1.25) for display. Reading columns max 62ch. Headlines get `text-wrap: balance`. Numbers that line up get `font-variant-numeric: tabular-nums` (mono already does).

### 2.3 Space

4px base: `--sp-1` 4, `--sp-2` 6, `--sp-3` 8, `--sp-4` 10, `--sp-5` 12, `--sp-6` 14, `--sp-7` 18, `--sp-8` 22, `--sp-9` 28. Use `gap` on flex and grid parents, not margins on children. Common pairs: rows `6px 8px`, cards `14px`, view body `18px 22px`, composer `8px 14px 12px`.

### 2.4 Radius

| Token | Value | Applies to |
|---|---|---|
| `--r-xs` | 4px | Citation chip `1` |
| `--r-sm` | 7px | Pills, chips, segmented items, small buttons, kbd |
| `--r-md` | 9px | Sidebar rows, inputs, icon buttons, address bar, send button, mail list selection |
| `--r-lg` | 12px | Composer, cards, story cards, popovers, floating panels |
| `--r-xl` | 16px | Home command bar |
| `--r-pill` | 999px | Count badges, account pills, avatar |

Thumbnails and images use `--r-md`. Tables and the compare grid stay square (they are grids, not objects).

### 2.5 Elevation

Two shadows only. `--shadow-bar` on the home command bar. `--shadow-pop` on popovers and menus. Everything else is flat with a 1px `--line` border.

### 2.6 Motion

`--dur-fast` (120ms) for hover and press. `--dur` (220ms) with `--ease` for the agent fold, accordion chevrons and popovers. No motion on page load. The v0.5 `.caret-blink` cursor is retired from inputs; keep it only inside the streaming status line.

### 2.7 Theme and layout switching

```html
<html data-theme="light">   <!-- or "dark", or no attribute to follow the OS -->
<html data-layout="floating"> <!-- or "flush" -->
```

- **A · Floating (default).** `--canvas` shows around the main area and agent panel, which are `--panel` cards with `--r-lg` and a `--shell-gap` (8px) gutter. The sidebar sits directly on the canvas.
- **B · Flush.** `--shell-gap: 0`. Sidebar uses `--sunk`, main and agent use `--panel`, separated by 1px `--line`. Radius remains on bars, inputs and chips only.

Store the user's choice in settings. Default: theme follows OS, layout floating.

## 3. Logo

Name: **Satz**. Typeface: Besley 700. The mark is a dithered dot disc (ordered 4x4 Bayer dither, deep purple top-left to light grey bottom-right, the "lock screen" ramp) sitting behind the S. Read as (S)atz.

Always draw it with `src/design-system/brand.ts`. Never export it as a PNG for in-app use, and never redraw the dither by hand.

```ts
import { drawWordmark, drawIcon, fontsReady } from "./design-system/brand";
await fontsReady();
drawWordmark(canvas, { height: 22, theme: "light", variant: "backdrop" });
drawIcon(canvas, { size: 32 });             // round
drawIcon(canvas, { size: 64, tile: true }); // app tile
```

| Variant | Disc | Use |
|---|---|---|
| `backdrop` (primary) | Centred on the S, about 2x cap height | Sidebar header, splash, About |
| `offset` | Up and left of the S | Marketing, docs headers |
| `grain` | Largest disc, finest dots | Large sizes (48px+ type) |

Rules:
- The word is one unit at normal Besley spacing. Do not add space between S and atz, and do not set "atz" separately.
- **Light:** letters in `#1f1b22` with a thin knock-out gap in the dots around each letter.
- **Dark:** letters in `#f4f1f8`, no outline or knock-out on the S.
- **Icon:** disc only, solid white S, no outline. Below 24px the dots get coarser automatically. Favicon, dock, collapsed sidebar and the telemetry popover header use the icon.
- Minimum wordmark height 18px. Below that, use the icon.
- Clear space around the mark: half the cap height on every side.
- Do not recolor the dither, rotate it, put it on a photo, or add a shadow.

## 4. Shell

```
┌ sidebar 232 ┬──── main (flex) ──────────────────┬ agent 318 / 44 ┐
│ wordmark    │ top bar: back fwd reload [address]│ agent header   │
│ quick icons │ lane tabs (mail / news only)      │ agent thread   │
│ accordion   │ view body                         │                │
│ ...         │ composer (prompt first)           │ agent composer │
│ footer icons│                                   │                │
└─────────────┴───────────────────────────────────┴────────────────┘
```

The bottom status bar (`.status-line`) is removed. Its content moves to the telemetry popover (section 5.4).

| Region | v0.5 class | v1 class | Notes |
|---|---|---|---|
| Root | `.shell-root` | `.shell` | `display: grid; grid-template-columns: var(--rail-w) minmax(0,1fr) var(--agent-w)`; floating adds `gap: var(--shell-gap); padding: var(--shell-gap) var(--shell-gap) var(--shell-gap) 0` |
| Main row | `.shell-main-row`, `.workspace-column`, `.workspace-body` | `.main` | One column: top bar, tabs, body, composer |
| Viewport | `.viewport-primary` | `.main-body` | `flex: 1; overflow: auto; padding: 18px 22px` |
| Right panel | `.right-panel` | `.agent` | Sources list becomes a tab inside the agent (section 5.10) |
| Status line | `.status-line`, `.status-segment`, `.status-item` | removed | Content in `.telemetry-pop` |

## 5. Components

Each entry: purpose, anatomy, states, tokens, and the v0.5 classes it replaces. Section 7 is the full class-by-class map.

### 5.1 Primitives

**Button `.btn`.** Height 28px, padding `6px 10px`, `--r-sm`, 1px `--line`, `--panel` fill, `--fs-sm` Inter 500. Hover `--hover`. Variants: `.btn.primary` (`--accent` fill, `--accent-ink` text, no border), `.btn.ghost` (no border, no fill), `.btn.danger` (text `--danger`). Disabled: 45% opacity, no hover. Replaces bare `button` styles and `button.active` / `.inverse`.

**Text action `.btn-text`.** No border, no fill, `--muted`, `--fs-sm`. Hover `--accent`. Used for card actions (`Open reader`, `Perspectives (3)`, `Save to Brain`). Replaces `.citation-link` when used as an action and `.rail-menu-btn` text actions.

**Icon button `.icon-btn`.** 28x28 (sidebar quick icons 32px tall, flex 1), `--r-md`, icon 16px in `--muted`. Hover `--hover` + `--ink`. Active `.on`: `--accent-soft` fill, `--accent` icon. Requires `title` and `aria-label`. Optional status dot: `.icon-btn > .dot` top-right 5px.

**Segmented control `.seg`.** Container `--panel`, 1px `--line`, `--r-md`, padding 3px. Items `--r-sm`, `--fs-sm` 500, `--muted`; pressed item `--ink` fill and `--panel` text. Use `aria-pressed`. For theme, layout, density and filter toggles.

**Input `.input`.** Height 30px, padding `0 10px`, `--r-md`, 1px `--line`, `--panel` fill, `--fs-base`. Focus: border `--accent` plus focus ring. Placeholder `--faint`, sentence case, no trailing underscore (v0.5 used `name_`). Variants `.input.pin` (width 145px, mono, letter-spacing .2em), `.textarea` (same, padding 8px, min-height 72px, mono only for raw JSON). Replaces `.kb-input`, `.vault-input`, `.vault-pin-input`, `.vault-textarea`, `.rail-rename-input`, `.rail-filter-input`, `.address-input` (address bar has its own style, 5.5).

**Select `.select`.** As `.input` plus a chevron icon on the right. The model picker is a `.chip` that opens a menu (5.7), not a native select.

**Slider `.slider`.** Native range with `accent-color: var(--accent)`, value shown to the right in mono `--fs-xs`. Replaces `.news-src-slider`, `.news-src-slider-val`.

**Pill `.pill`.** Inline label for a source or tag. `--fs-xs` mono, padding `5px 7px`, `--r-sm`, `--sunk` fill, 1px `--line`, `--muted` text, strong part in `--ink` 500. Clickable pills get hover `--hover`. Variant `.pill.round` (`--r-pill`, Inter `--fs-sm`, for account filters; selected = `--ink` fill, `--panel` text). Replaces `.context-pill`, `.news-band-pill`.

**Chip `.chip`.** Borderless control inside bars: `--fs-xs` mono, `--muted`, padding `5px 7px`, `--r-sm`, optional 11px icon. Hover `--hover`. Used for the model picker, attach, `tab` context. Replaces `.context-add-btn`.

**Badge `.badge`.** Count on the right of a row: mono 10.5px, padding `3px 6px`, `--r-pill`, `--accent` fill, `--accent-ink` text. `.badge.soft`: `--hover` fill, `--muted` text (for "4 new"). Never more than one per row.

**Status dot `.dot`.** 6px circle. `--good` default, `.dot.warn`, `.dot.danger`. Paired with text (`ready`, `no key`), never alone except on the telemetry icon.

**Citation chip `.cite`.** Inline `1` reference in answers: mono 10.5px, `--accent` text on `--accent-soft`, padding `1px 4px`, `--r-xs`. Hover underline, click opens source. Variant `.cite.flagged` (dashed `--warn` border, for weak or cut sources). Replaces `.citation-link` (when a reference), `.citation-flagged`.

**Flag `.flag`.** Small outline badge for system states inside data: `cut`, `unsourced`, `outside usual`, `translated`. mono 10px, 1px `--line`, `--r-xs`, `--muted`. Replaces `.source-cut-badge`.

**Keyboard hint `.kbd`.** mono 10.5px, 1px `--line`, `--r-sm`, padding `3px 6px`, `--muted`. Shown only in the command bar, menus and tooltips. Replaces `<span class="muted">[mod+k]</span>`.

**Banner `.banner`.** Full-width notice inside a view: padding `10px 12px`, `--r-md`, `--sunk` fill, 1px `--line`, `--fs-sm`, leading 16px icon. Variants `.banner.warn` and `.banner.danger` (icon and left text tinted, fill stays `--sunk`). Replaces `.profile-status-banner`, `.kb-status-banner`.

**Section label `.label`.** mono `--fs-micro`, uppercase, `--tracking-label`, `--faint`. Optional count after it in the same style without tracking, optional right-aligned text action. Replaces `.rail-group-label`, `.start-col-header`, `.kb-section-title`, `.kb-card-header`, `.panel-header` (as a label), `.msg-findings-header`.

**Divider `.sep`.** 1px `--line`, margin `4px 8px` inside lists. Between pinned system items (Mail, News) and user pins.

**Utilities (keep).** `.hidden`, `.truncate`, `.muted` (maps to `--muted`), new `.mono`, `.faint`. `.inverse` is retired.

### 5.2 Sidebar `.side`

Anatomy, top to bottom:

1. **Brand row.** Wordmark (`backdrop`, height 22) and the version in mono `--faint` right-aligned. Click opens Home.
2. **Quick actions.** Three `.icon-btn` in a row, equal width: Home (`home`, ⇧⌘H), Command bar (`cmd`, ⌘K), New conversation (`compose`, ⌘N). Home is `.on` when the start screen is active.
3. **Accordion sections** (`.acc`). Each has a header button `.acc-h` (section label + count + chevron that rotates -90° when closed) and a body `.acc-b`. Open state persists per profile.
   - **Pinned:** Mail (`mail` icon, unread `.badge`), News (`news` icon, `.badge.soft` "N new"), then `.sep`, then user pins (`pin` icon, `src` count). Mail and News cannot be unpinned.
   - **Mail accounts** render as indented sub-rows under Mail when Mail is selected (5.2.1).
   - **Conversations:** recent, `chat` icon, relative time on the right.
   - **Sources:** bookmarked, continuously indexed sites, `star` icon, sync state (`synced`, `2h`, `indexing`). The "bookmark this tab" action moves to the top bar and the command bar.
   - **Archived:** collapsed by default, one row "Show N archived".
4. **Footer.** `.icon-btn` for Brain (⌘B), Settings, Telemetry (`pulse` with a status dot, opens 5.4), then the profile chip (avatar initial + name) right-aligned. Locking the profile is in the profile chip's menu.

**Row `.row`.** Height 30px, padding `6px 8px`, gap 8px, `--r-md`. 14px icon in `--muted`, title flexes and truncates, right meta in mono `--fs-xs` `--faint`. Hover `--hover`. Selected `.on`: `--accent-soft`, icon `--accent`. Running generation: replace the meta with a 6px `--accent` dot pulsing at 1.2s (static under reduced motion). Watch alert: a `--warn` dot plus `title="watched value changed"`. Row menu: `more` icon button that appears on hover, opening a `.menu` (5.7) with Rename, Pin/Unpin, Archive, Delete. Rename turns the title into an `.input` in place.

**5.2.1 Mail account sub-rows.** Indented 22px, 1px `--line` left guide, `--fs-sm`, account name and unread count, no icon. Replaces `.rail-mail-tree`, `.rail-row-sub`, `.rail-sub-branch` (no ASCII branch glyphs).

Replaces: `.left-rail`, `.rail-header`, `.rail-controls`, `.rail-btn-full`, `.rail-scroll`, `.rail-group`, `.rail-group-label`, `.rail-row*`, `.rail-running-badge`, `.rail-menu-btn`, `.rail-popover-menu`, `.rail-rename-input`, `.rail-footer`, `.rail-filter-row`, `.rail-filter-input`, `.bookmark-btn-wrap`, `.bookmark-tooltip-hint`.

### 5.3 Top bar `.top` and address bar `.addr`

Row of back, forward, reload `.icon-btn`, then the address bar, then optional page actions (bookmark `star`, compare `compare`, open external).

**Address bar.** Height 30px, `--r-md`, `--sunk` fill (flush layout adds 1px `--line`), padding `0 10px`, mono `--fs-sm`. Leading icon shows the context: `globe` for web, `home` for `satz://home`, `news`, `lock` for mail (vault-backed). Host in `--ink`, path in `--muted`. Trailing `.kbd` ⌘L. Focus: `--panel` fill, `--accent` border.

Replaces: `.site-tab-toolbar`, `.address-input`.

### 5.4 Telemetry popover `.telemetry-pop`

Opens from the footer `pulse` button, anchored bottom-left above the footer, 276px wide. `--glass` fill with `backdrop-filter: blur(16px) saturate(1.3)`, 1px `--line`, `--r-lg`, `--shadow-pop`, padding 12px, gap 10px. Closes on Escape, outside click or a second click.

Groups, each with a `.label` heading and a two-column key/value grid (key Inter `--fs-sm`, value mono `--fs-xs` `--muted` right-aligned):

| Group | Rows (source in v0.5) |
|---|---|
| Model | Active model (`state.selectedModel`), Gemma state with dot (`warm` / `loading` / `off` + device), Privacy (`getModelPrivacySummary`) |
| Models | One row per local model and per cloud provider with dot (`ready`, `keys ok`, `no key`) |
| Context | Sources in context, KB queue (+ learn state), Mail processing `done / total` with a 4px `--accent` progress meter |
| Log | Sidecar errors count; click opens the error log panel (5.12) |

The telemetry icon's dot is `--good` when everything is healthy, `--warn` when degraded (loading model, no key on the selected provider), `--danger` when the sidecar is offline or the error ring has new entries.

Replaces: `.status-line`, `.status-segment`, `.status-item`, the `[log (n)]` button.

### 5.5 Lane tabs `.tabs`

Underlined tabs below the top bar for multi-lane conversations. Mail: Chat, Inbox, Pings, Orders, Promos. News: Chat, Top stories, For you, Perspectives, Topics, Sources. Each tab: padding `7px 11px 9px`, `--fs-sm`, `--muted`, count in mono `--faint`. Active: `--ink` text, 2px `--accent` bottom border.

**Open-site tabs** (live webviews of a conversation) use the same strip: favicon or `globe`, title truncated at 160px, close `x` icon on hover. Compare-selected tab: 1px `--accent` outline at `--r-sm`. The strip scrolls horizontally, never wraps.

Replaces: `.tab-strip`, `.tab-strip-left`, `.tab-strip-right`, `.tab-item`, `.tab-item.selected-compare`, `.tab-close-btn`.

### 5.6 Composer `.composer`

Prompt first. One bar, suggestions underneath.

```
[ prompt ...................................... (attach) (gemma-4 · local v) (→) ]
  suggestion · suggestion · suggestion
```

- `.cbox`: `--panel`, 1px `--line`, `--r-lg`, padding `5px 5px 5px 12px`, gap 6px. Focus-within: border `--accent`.
- Input: borderless, `--fs-md`, grows to 6 lines then scrolls.
- Right controls in order: attach `.chip` (opens context: tabs, files, mail), model `.chip` (opens model menu, shows privacy in its `title`), send button (30px, `--r-md`, `--accent` fill, `send` icon; disabled `--hover` fill while empty; becomes a stop square while streaming).
- Context pills (attached tabs or sources) appear as `.pill` inside the box before the input, each with an `x` on hover. More than 3 collapse into `+N`.
- Suggestions row: `--fs-xs`, `--faint`, plain text buttons separated by 12px gap, hover `--muted`. One row, overflow hidden, never wraps. Mail and News supply their own suggestions.
- The v0.5 meta row (`models [ok] · privacy`) is removed; that information is in the model chip title and the telemetry popover.

Agent composer (5.10) is the same component without attach and model chips.

Replaces: `.chat-composer`, `.composer-input-row`, `.composer-input`, `.composer-context-row`, `.composer-context-pills`, `.composer-meta-row`, `.composer-status-label`, `.composer-controls`, `.context-add-btn`, `#chat-model-select`.

### 5.7 Menus and command bar

**Menu `.menu`.** `--panel`, 1px `--line`, `--r-lg`, `--shadow-pop`, padding 4px, min-width 180px. Items `.menu-item`: 30px, padding `0 10px`, `--r-md`, icon 14px + label + optional `.kbd` right. Hover `--hover`. Destructive item in `--danger`. Separator `.sep`. Replaces `.rail-popover-menu`.

**Command bar (⌘K overlay).** Centered 640px, top 14vh, same visual as the home command bar (5.8) plus a results list grouped by `.label` (Open tab, Ask, Mail, Brain, Commands), each result a `.menu-item` with a route icon and a privacy hint in mono `--faint` on the right (`on-device`, `cloud: gemini`). Backdrop: `--canvas` at 40% with blur 4px. Replaces `.cmd-foryou-section` and the overlay markup in `start.ts`.

### 5.8 Home (start screen)

Centered column, max-width 760px, top padding 46px.

1. Date line: mono `--fs-micro` uppercase `--faint` (`WEDNESDAY · 18 NOV`).
2. Greeting: Besley 700 `--fs-2xl`, "Where do you want to start?".
3. **Home command bar `.bigbar`:** 640px, `--panel`, 1px `--line`, `--r-xl`, `--shadow-bar`, padding `14px 14px 8px 16px`. Row 1: `cmd` icon, input `--fs-lg`, `.kbd` ⌘K. Row 2: attach chip, model chip, two inline suggestions, send button right.
4. Two sections **stacked full width** at the command bar's 640px width, For you first, Resume below, gap 18px (decided 2026-11-18; the side-by-side mock is superseded):
   - **For you** (`.label` + `refresh` text action): digest items `.digest` with a 26px `--sunk` source tile (icon by kind: mail, news, star for bookmark, globe for page), title 500 `--fs-base`, subline `--fs-xs` `--muted` (lane · sender or source · age · reason). Optional thumbnail 72x50 `--r-md` right of the text; extra thumbs as a row of 54x38. Hover `--hover` on the whole item, `--r-lg`.
   - **Resume** (`.label` + `all`): `.row`-style items with conversation icon, title, mono meta (tabs, src, age).
5. Profile unlock card (when locked): a `.card` above the columns with PIN `.input.pin`, `Unlock` primary button, `Unlock with Touch ID` button when available, and `Create profile` below a `.sep`.

The agent panel starts folded on Home.

Replaces: `.start-screen`, `.start-container`, `.start-prompt-title`, `.start-input-box`, `.start-input-row`, `.start-input-field`, `.start-controls-row`, `.start-columns`, `.start-col`, `.start-col-header`, `.start-col-foryou`, `.start-col-resume`, `.start-foryou-list`, `.start-digest-*`, `.start-list-item`, `.start-resume-item`, `.start-resume-main`, `#start-profile-unlock-card`.

### 5.9 Chat thread

Messages column max 720px centered in `.main-body`, gap 14px.

- **User message `.msg-you`:** right-aligned, `--sunk` fill, 1px `--line`, radius `12px 12px 4px 12px`, padding `8px 11px`, max 88%.
- **Assistant message `.msg-bot`:** no bubble. Header line in mono `--fs-xs` `--faint` (model · time · sources count). Body `--fs-md` `--lh-read`, selectable. Inline `.cite` chips. Sources list below as numbered `--fs-xs` lines (`1 · dw.com · 8.4`), personal trust shown next to system trust when they differ.
- **Streaming status `.stream`:** inside the assistant message, a `--sunk` box `--r-md`, current step in `--ink` 500 with the pulsing accent dot, previous steps in `--muted` `--fs-xs`, one line each, truncated.
- **Error `.msg-bot.error`:** `.banner.danger` with the error text and a `Retry` button.
- **Findings grid `.findings`:** `.label` "Findings" then a grid `repeat(auto-fill, minmax(140px,1fr))` gap 8px. Each `.finding` is a `.card` with 120px image (`--r-md` top corners), title `--fs-sm`, price mono 600.
- **Page preview cards `.preview-grid`:** grid `minmax(240px,1fr)`, each a `.card` with favicon, title, host mono, 2-line snippet. Hover border `--accent`.
- **Video cards `.video-grid`:** grid `minmax(300px,1fr)`, 16:9 embed `--r-md`, title below.
- **Attachments:** images max 420px tall `--r-md`; PDFs in a 440px embed `--r-md` 1px `--line`; inline email body in a `--sunk` `--r-md` box max 360px scroll.
- **Draft card `.draft`** (mail replies, task cards): `--sunk`, 1px `--line`, `--r-lg`, padding 10px, a `--faint` line "Draft · sends only after you press Send", body, then actions (`Send` primary, `Edit`, `In English`). This is the send gate, never auto-submit.
- **Task card** (M22 agents): `.card` with title, step list, token budget in mono, `Confirm` primary and `Cancel`.
- Inline page links: `--accent` text, underline on hover.

Replaces: `.chat-view`, `.chat-column`, `.chat-messages`, `.msg-block`, `.msg-header`, `.msg-body`, `.msg-streaming-block`, `.streaming-status-*`, `.streaming-step-line`, `.msg-error-block`, `.msg-error-badge`, `.msg-findings-*`, `.msg-finding-*`, `.chat-preview-cards-grid`, `.chat-page-preview-card`, `.chat-video-*`, `.chat-attachment-*`, `.chat-inline-email-body`, `.inline-page-link`, `.caret-blink`.

### 5.10 Agent panel `.agent`

Right side, `--agent-w` 318px open, `--agent-folded-w` 44px folded. Transition on `grid-template-columns` with `--dur` `--ease`.

- **Header `.ag-h`:** 28px `--accent-soft` tile with `spark` icon, title 600 (`On this tab`), subline `--fs-xs` `--muted` (what the agent sees: `Top stories · 3 families read`, `Inbox · message 1 of 12`), fold button `panel` icon right.
- **Tabs (optional):** `Chat`, `Sources (14)` as small `.tabs`. Sources tab lists `.source-row`s (5.11).
- **Thread:** chat thread components (5.9) at `--fs-sm`.
- **Composer:** 5.6 without attach and model chips.
- **Folded strip `.strip`:** `spark` tile button at top, vertical mono label `ON-TAB AGENT` in `--faint`. Clicking anywhere on the strip opens the panel. Unread agent output shows an `--accent` dot on the tile.
- Default state per view: Home folded, Mail and News open, web tabs open. Remember the user's last choice per view.

Replaces: `.right-panel`, `.panel-header`, `.panel-scroll` (agent use).

### 5.11 Lists, cards and sections

**Card `.card`.** `--panel`, 1px `--line`, `--r-lg`, padding 14px, gap 10px. Header row: `.label` or title 600 left, text actions right. In floating layout cards inside `--panel` views use `--sunk` fill instead so they separate. Replaces `.kb-card`, `.knowledge-section`, `.kb-section`, `.news-persp-col`, `.news-reader-overlay` (reader uses a card with `--fs-md` body and 62ch column).

**Section `.section`.** A titled group inside a view: `.label` header with a 1px `--line` underline and optional actions, then content with gap 8px. Replaces `.kb-section-title` pattern.

**Source row `.source-row`.** For sources in context and bookmarks: padding `8px 10px`, `--r-md`, hover `--hover`. Line 1: favicon 14px, title `--fs-sm` (click opens), trust in mono right (`8.4`, personal value after a `·` when different). Line 2: host mono `--fs-xs` `--faint`, flags (`.flag cut`). Remove action `x` on hover. Replaces `.source-row`, `.source-row-top`, `.source-row-title`, `.source-row-meta`.

**Table `.table`.** For KB entities and the sources list in News: `--fs-sm`, header in `.label` style on `--sunk`, rows separated by 1px `--line`, no vertical borders, cell padding `8px 10px`, numbers mono right-aligned, row hover `--hover`. Outer container `--r-lg` with `overflow: hidden`. Replaces `.kb-table`.

**Form row `.form-row`.** Flex wrap gap 8px, inputs flex 1 min 140px, buttons last. Replaces `.kb-form-row`, `.vault-form-row`, `.vault-inline-controls`, `.vault-raw-block`.

**Accordion `.acc`.** Header button with chevron, body toggled by class `open`. Used in the sidebar, settings sections and the Brain view. Replaces `.accordion-header`.

### 5.12 Panels and overlays

**Error log panel.** `.card` docked above the composer or as a sheet from the telemetry popover: header "Sidecar log (n / 50)" with `Clear` and `Close`, rows in mono `--fs-xs` (scope, message, time). Max height 200px, scroll. Replaces `#region-error-log-overlay` and the error ring markup in `status.ts`.

**Profile startup modal.** Centered `.card` 420px with `--shadow-pop` over a blurred `--canvas` backdrop. Same content as the Home unlock card. Replaces the modal markup at `start.ts:759`.

### 5.13 Mail

- **Account filter:** row of `.pill.round` (All mail, then each account by name), sync status mono `--faint` right (`synced 3m ago`), `Sync now` `.btn` when idle.
- **Lane tabs:** 5.5 with counts.
- **Split view:** list 330px | reading pane, separated by 1px `--line`, full bleed inside `.main-body`.
- **Message row `.mail-row`:** padding `10px 14px`, 1px `--line` bottom. Line 1: unread `--accent` 6px dot, sender 600 `--fs-sm` truncated, time mono `--fs-xs` `--faint`. Line 2: subject `--fs-sm`. Line 3: preview `--fs-xs` `--muted`. Read: sender and subject 400 `--muted`. Selected: `--accent-soft`. Replaces `.mail-lane-list`, `.mail-lane-row`, `.mail-unseen`, `.mail-col-from`, `.mail-col-subject`, `.mail-col-time`.
- **Lane cards** (Pings, Orders, Promos): grouped `.card` per sender or order, with tracking `Track` button and status `.dot`. Promos show the code in a mono `.pill`.
- **Reading pane:** subject Besley 700 `--fs-xl`; from line with 30px avatar initials, name 600, recipient `--fs-xs` `--muted`, date mono right. **Extracted action `.extract`:** `--sunk` box `--r-md` with `cal` (or `box` for orders) icon in `--accent`, one bold label + text, primary button right (`Add to calendar`, `Track`). Body `--fs-md` `--lh-read` max 62ch. HTML bodies render in `.email-frame` (sandboxed iframe, `--r-md`, background follows theme: `--panel`). Attachments as `.pill` with `doc` icon, name and size. Actions `Reply`, `Forward`, `Archive` as `.btn`.
- **Add account form:** `.card` with `.form-row`s (email, name, app password; IMAP host and port; SMTP host and port), `Test` and `Add account` primary. Note "Credentials are stored in your encrypted vault" in `--fs-xs` `--muted`.
- **Account list:** `.table` with name, email, last sync, state dot, and `Test`, `Sync`, `Remove` as `.btn-text`.
- **Eval mode:** `.card` with progress mono (`37 / 200`), `Prev` / `Next`, message excerpt in `--sunk`, label `.seg` (1 Email, 2 Ping, 3 Information, 4 Promotion), extraction check `.seg` (Yes, No). Keyboard 1 to 4, y, n.
- **Locked state:** `.banner` "Mail is locked" + inline PIN form (5.1 `.input.pin`, `Unlock`, `Unlock with Touch ID`).

Replaces: `.email-body-iframe`, `.email-tab-header`, the bracket buttons in `mail.ts`.

### 5.14 News

- **Lane tabs:** Chat, Top stories, For you, Perspectives, Topics, Sources.
- **Story card `.story`:** `.card` grid `112px minmax(0,1fr)` gap 16px, `align-items: start`. Thumbnail 112x86 `--r-md` (full color; v0.5 grayscale filter retired). Content column `.story-c` is a flex column with gap 6px and **no element margins** (reset `h5` and `ul` margins; `ul` uses `padding-left: 16px`). Order:
  1. Meta line, mono `--fs-xs` `--faint`: status (`developing · 40m` in `--warn`), topic, then the confidence meter pushed right (`margin-left: auto`).
  2. Headline, Inter 600 `--fs-lg`, `text-wrap: balance`.
  3. Bullets, `--fs-sm` `--muted`, max 3.
  4. Brain match line (optional), `--fs-xs` `--muted`, with `outside usual sources` as a `.flag`.
  5. Footer `.story-foot`: separated by a 1px `--line` top border and 10px padding-top. Left: source family `.pill`s in one non-wrapping row (`flex: 1; min-width: 0; overflow: hidden`), at most 2 shown, the rest as a `+N` pill whose `title` lists them. Right (`flex: none`): `.btn-text` actions, at most 3 visible plus a `more` button. The first action is `Open reader` in `--accent` 500. Second is the best next step for the story (`Perspectives (n)` when there are 2+ families, else `Translate xx→en` for foreign text, else `Ask in chat`). Third is `Save` (to Brain). Everything else (Compare, Ask in chat, Less like this, Hide) lives in the `more` menu.
  The footer never wraps onto two lines. If the column is narrower than 520px, pills collapse to the first one plus `+N`.
- **Confidence meter `.conf`:** mono value + 38x4px bar, fill `--accent` to `--c` percent on `--hover`. Replaces `.news-band-pill`, `.news-band-good`, `.news-band-low` (low confidence: value in `--warn`).
- **Perspectives:** cluster selector `.select` + `Re-analyze` `.btn`; analyzer and privacy line `--fs-xs` `--muted`; "Agreed facts" `.section`; columns grid (count from data) of `.card`s per family with source `.pill`s and stance bullets; "Blind spots and counterfactual" `.section`. Replaces `.news-persp-grid`, `.news-persp-col`.
- **Reader:** `.card` with headline Besley 700 `--fs-xl`, source and time mono, body 62ch `--fs-md` `--lh-read`, audit box `.section` at the bottom (faithfulness, confidence items). Replaces `.news-reader-overlay`, `.news-audit-box`.
- **Topics:** add form (`.form-row`: topic name, keywords, `Track topic` primary), list of `.source-row`s with `Query now` and `Remove`.
- **Sources:** filter `.input` with `search` icon, `.table` of domain, category, system trust, personal `.slider` (cap note "Personal trust counts for at most 30%" in `--fs-xs` `--muted`), effective trust mono. Add feed `.form-row`.

Replaces: `.news-story-card`, `.news-card-media-row`, `.news-card-thumb`, and all bracket actions in `news.ts`.

### 5.15 Brain and Knowledge views

- View header: title Besley 700 `--fs-xl` + subline `--muted`, search `.input` right. Replaces `.knowledge-view`, `.kb-header`.
- Entities: `.table` or `.card` list; entity cards show type `.flag`, name 600, facts as `--fs-sm` lines with `[B1]`-style memory citations rendered as `.cite`.
- Proposals (accept / reject): `.card` with diff lines, `Accept` primary, `Reject` `.btn`.
- Domain trust sliders: as News sources.
- Vault raw JSON: `.textarea` mono. Replaces `.kb-textarea`, `.vault-textarea`.

### 5.16 Compare view

Grid of 2, 3 or 4 live tabs. Gap 1px on `--line` background (square, it is a grid). Each `.compare-tile` has a 30px header with favicon, host mono, close `x`. In floating layout the whole grid sits in a `--r-lg` container with `overflow: hidden`. Replaces `.compare-grid`, `.panes-2`, `.panes-3`, `.panes-4`, `.compare-tile`, `.webview-slot` (webview placeholder text `--faint` centered).

## 6. Icons

`src/design-system/icons.ts`. 24px grid, 1.7 stroke, round caps and joins, no fill, `currentColor`. Render at 16px (`.ico`), 14px in rows (`.ico-sm`), 11px in chips.

Set: `home`, `cmd`, `compose`, `mail`, `news`, `pin`, `chat`, `brain`, `settings`, `pulse`, `chev`, `back`, `fwd`, `reload`, `panel`, `send`, `globe`, `lock`, `spark`, `attach`, `reply`, `cal`, `doc`, `star`, `box`, `archive`, `x`, `plus`, `more`, `search`, `check`, `trash`, `compare`, `external`, `translate`, `eye`, `watch`.

Need a new icon? Draw it on the same grid and stroke, add it to `ICONS`, and list it here. No icon fonts, no emoji, no filled icons.

## 7. Migration map (every v0.5 class)

Every class defined or used in `src/style.css` and `src/*.ts` as of 2026-11-18 (after commit f2efec3). "Keep" means the name stays and only its styles change to tokens.

| v0.5 class | v1 | Section |
|---|---|---|
| `.hidden`, `.truncate`, `.muted` | Keep | 5.1 |
| `.inverse`, `button.active` | `.btn.primary` / `.on` | 5.1 |
| `.caret-blink` | Retire (streaming dot only) | 5.9 |
| `.shell-root`, `.shell-main-row` | `.shell` | 4 |
| `.workspace-column`, `.workspace-body`, `.viewport-primary` | `.main`, `.main-body` | 4 |
| `.left-rail` | `.side` | 5.2 |
| `.rail-header` | `.side .brand` | 5.2 |
| `.rail-controls`, `.rail-btn-full` | `.quick` + `.icon-btn` | 5.2 |
| `.rail-filter-row`, `.rail-filter-input` | Command bar search | 5.7 |
| `.rail-scroll` | `.acc-wrap` | 5.2 |
| `.rail-group`, `.rail-group-label` | `.acc`, `.acc-h` | 5.2 |
| `.rail-row`, `.rail-row-title`, `.rail-row-meta`, `.rail-row-time`, `.rail-row-src-count` | `.row`, `.row .t`, `.row .meta` | 5.2 |
| `.rail-mail-tree`, `.rail-row-sub`, `.rail-sub-branch` | `.row.sub` | 5.2.1 |
| `.rail-running-badge` | Pulsing `.dot` in row | 5.2 |
| `.rail-menu-btn`, `.rail-popover-menu` | `more` `.icon-btn` + `.menu` | 5.2, 5.7 |
| `.rail-rename-input` | `.input` in row | 5.1 |
| `.rail-footer` | `.foot` | 5.2 |
| `.bookmark-btn-wrap`, `.bookmark-tooltip-hint` | Top bar `star` button with `title` | 5.3 |
| `.tab-strip`, `.tab-strip-left`, `.tab-strip-right`, `.tab-item`, `.tab-close-btn` | `.tabs`, `.tab` | 5.5 |
| `.site-tab-toolbar`, `.address-input` | `.top`, `.addr`, `.tile-h`, `.tile-addr` | 5.3, 5.16 |
| `.webview-slot` | Keep | 5.16 |
| `.compare-grid`, `.panes-2/3/4`, `.compare-tile` | Keep (+ `.compare-view`) | 5.16 |
| `.start-screen`, `.start-container`, `.start-prompt-title` | `.home`, greeting | 5.8 |
| `.start-input-box`, `.start-input-row`, `.start-input-field`, `.start-controls-row` | `.bigbar` | 5.8 |
| `.start-columns`, `.start-col`, `.start-col-header`, `.start-col-foryou`, `.start-col-resume` | `.home-cols`, `.label` | 5.8 |
| `.start-foryou-list`, `.start-digest-card`, `.start-digest-card-top`, `.start-digest-title-wrap`, `.start-digest-kind`, `.start-digest-right-meta`, `.start-digest-media`, `.start-digest-thumb`, `.start-digest-body`, `.start-digest-snippet`, `.start-digest-meta`, `.start-digest-extra-thumbs`, `.start-digest-extra-thumb` | `.digest` (+ `.digest-thumb`, `.digest-thumbs`) | 5.8 |
| `.start-list-item`, `.start-resume-item`, `.start-resume-main` | `.row` | 5.8 |
| `.cmd-foryou-section` | Command bar group | 5.7 |
| `.chat-view`, `.chat-column`, `.chat-messages` | `.thread` | 5.9 |
| `.msg-block`, `.msg-header`, `.msg-body` | `.msg-you`, `.msg-bot` | 5.9 |
| `.msg-streaming-block`, `.streaming-status-box`, `.streaming-status-current`, `.streaming-steps-list`, `.streaming-step-line` | `.stream` | 5.9 |
| `.msg-error-block`, `.msg-error-badge` | `.msg-bot.error` + `.banner.danger` | 5.9 |
| `.msg-findings-section`, `.msg-findings-header`, `.msg-findings-grid`, `.msg-finding-card`, `.msg-finding-img`, `.msg-finding-meta`, `.msg-finding-title`, `.msg-finding-price` | `.findings`, `.finding` | 5.9 |
| `.chat-preview-cards-grid`, `.chat-page-preview-card` | `.preview-grid`, `.card` | 5.9 |
| `.chat-video-grid`, `.chat-video-card`, `.chat-video-embed` | `.video-grid` | 5.9 |
| `.chat-attachment-embed`, `.chat-attachment-img`, `.chat-inline-email-body` | Attachments | 5.9 |
| `.inline-page-link` | Keep (accent link) | 5.9 |
| `.citation-link` | `.cite` (reference) or `.btn-text` (action) | 5.1 |
| `.citation-flagged` | `.cite.flagged` | 5.1 |
| `.source-cut-badge` | `.flag` | 5.1 |
| `.chat-composer`, `.composer-input-row`, `.composer-input`, `.composer-context-row`, `.composer-context-pills`, `.composer-meta-row`, `.composer-status-label`, `.composer-controls`, `.context-add-btn` | `.composer`, `.cbox`, `.chip`, `.sugg` | 5.6 |
| `.context-pill` | `.pill` | 5.1 |
| `.right-panel`, `.panel-header`, `.panel-scroll` | `.agent`, `.ag-h`, `.ag-body` | 5.10 |
| `.source-row`, `.source-row-top`, `.source-row-title`, `.source-row-meta` | Keep, restyled | 5.11 |
| `.status-line`, `.status-segment`, `.status-item` | `.telemetry-pop` | 5.4 |
| `.knowledge-view`, `.knowledge-section`, `.kb-header` | View header + `.card` | 5.15 |
| `.kb-section`, `.kb-section-title` | `.section` | 5.11 |
| `.kb-card`, `.kb-card-header` | `.card`, `.label` | 5.11 |
| `.kb-table` | `.table` | 5.11 |
| `.kb-form-row`, `.vault-form-row`, `.vault-inline-controls`, `.vault-raw-block` | `.form-row` | 5.11 |
| `.kb-input`, `.vault-input`, `.vault-pin-input`, `.vault-textarea`, `.kb-textarea` | `.input`, `.input.pin`, `.textarea` | 5.1 |
| `.kb-status-banner`, `.profile-status-banner` | `.banner` | 5.1 |
| `.accordion-header` | `.acc-h` | 5.11 |
| `.mail-lane-list`, `.mail-lane-row`, `.mail-unseen`, `.mail-col-from`, `.mail-col-subject`, `.mail-col-time` | `.mail-list`, `.mail-row` | 5.13 |
| `.email-body-iframe`, `.email-tab-header` | `.email-frame`, reading pane header | 5.13 |
| `.news-story-card`, `.news-card-media-row`, `.news-card-thumb` | `.story` | 5.14 |
| `.news-band-pill`, `.news-band-good`, `.news-band-low` | `.conf` | 5.14 |
| `.news-audit-box`, `.news-reader-overlay` | Reader `.card` + `.section` | 5.14 |
| `.news-persp-grid`, `.news-persp-col` | Perspective grid of `.card` | 5.14 |
| `.news-src-slider`, `.news-src-slider-val` | `.slider` | 5.1 |
| `#start-profile-unlock-card` | Home unlock `.card` | 5.8 |
| `#region-error-log-overlay` | Error log panel | 5.12 |
| `#chat-model-select`, `#start-model-select`, `#overlay-model-select` | Model `.chip` + `.menu` | 5.6 |

All v0.5 class rules and compatibility aliases (`--bg`, `--surface`, `--border`, `--fg`) were retired and `src/style.css` removed in D9; active layout and component styles reside solely in `src/design-system/tokens.css` and `src/design-system/components.css`.

## 8. Migration plan

Do it in this order; each step is one commit that passes `npm run build`.

1. **Tokens in.** Import `src/design-system/tokens.css` first in `index.html`. The compatibility aliases (`--bg`, `--surface`, `--border`, `--fg`) let the current `style.css` run on the new palette immediately. Remove the old `:root` block and the global `border-radius: 0` reset from `style.css`. Set `html, body` font to `var(--font-ui)`.
2. **Primitives.** `src/design-system/components.css` already contains every section 5 class; link it after `tokens.css`. Convert bare `button` styling to `.btn`.
3. **Shell.** Sidebar (5.2), top bar (5.3), telemetry popover (5.4) replacing `status.ts` rendering, agent panel with fold (5.10). Remove `.status-line`.
4. **Composer** (5.6) in chat, mail and news.
5. **Home** (5.8), then **Mail** (5.13), then **News** (5.14), then chat details (5.9), Brain (5.15), compare (5.16).
6. **Cleanup.** Remove the compatibility aliases and every v0.5 class from section 7 that has no remaining reference (`grep -rn "class-name" src/`). Replace remaining inline styles.
7. **Update `.gemini/antigravity.md`.** Replace the "Terminal aesthetic" rule with: "UI follows `docs/design/DESIGN_SYSTEM.md`. Tokens only, Inter / Besley / JetBrains Mono by role, radius by role, both themes, no em dashes, no emoji."

## 9. Checklist for every UI change

- [ ] Only semantic tokens, no hex in TS or component CSS
- [ ] Right font for the job (UI, display, or mono for data)
- [ ] Radius from the role table
- [ ] Light (paper) and dark both checked
- [ ] Floating and flush both checked
- [ ] Focus ring visible, icon buttons have `title` and `aria-label`
- [ ] No em dashes, no emoji, sentence case, actions say what they do
- [ ] Trust, privacy and send-gate information still visible
- [ ] Shortcut still works and is shown in `title` or `.kbd`
- [ ] Section 7 row updated if a class was added, renamed or removed
