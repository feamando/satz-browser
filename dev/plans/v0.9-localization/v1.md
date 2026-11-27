# Satz v0.9 Plan: App-Wide UI Localization with User-Model Translation

Status: Ready for Execution (`L1`–`L5`)  
Spec alignment: `docs/design/DESIGN_SYSTEM.md` (v1.2), `docs/PLAN_v0.8_settings_chat.md`

---

## 1. Goals & Approved Design Decisions

1. **Core Typed Key Table (`src/i18n/catalog.ts`):**
   - Extract all user-displayed UI strings across `src/*.ts` (labels, headers, buttons, placeholders, tooltips/`title`, `aria-label`, banners, command routes, relative time/date labels, and error states) into one canonical English catalog (`EN_CATALOG`) with derived TypeScript `UiKey` union checking.
2. **App-Wide Scope Across Profiles:**
   - Selected interface language and translated bundles are stored **app-wide** (`<app_data_dir>/i18n/<lang>.json` + `<app_data_dir>/i18n/config.json`) and cached in `localStorage` (`satz.ui.locale`, `satz.ui.i18n.<lang>`).
   - Switching or locking profiles never resets the interface language or forces re-translation.
3. **Display in Manual Settings & Settings Chat:**
   - Top of Manual Settings displays an explicit **App-wide preferences** card (`App-wide · all profiles` badge) grouping **Theme**, **Layout**, and **Interface language** above the profile/runtime sections (`1.`–`6.` accordions).
   - **Interface language** provides: saved-pack dropdown (`English (built-in)` + user packs), compact **"Translate new language..."** input + action button, model & privacy readout, silent background sync indicator, and an optional collapsed-by-default **Customize strings** key editor table (`Key | English | Translation | Reset`).
   - Settings Chat exposes declarative tools (`sidecar/satz_tools/settings_i18n.py`) + inline `locale_translate_card`.
4. **Silent Background Translation of Missing / Stale Keys:**
   - Whenever active locale `!= "en"` on startup, profile unlock, or catalog hash update, missing or changed-English keys (`source_hash` mismatch) are queued and translated automatically in the background using the user's selected default chat model (`roles.chat`).
5. **Model-Agnostic Translation via Default Model (`roles.chat`):**
   - Routes all batches through `SatzSidecarRuntime._complete_role_prompt(...)`, supporting local `gemma-4-e4b` as well as configured Cloud providers (`gemini`, `anthropic`, `openai`, `mistral`). Web/reader-only chat selections (`planck3 (web)`, `hertz (reader)`, `planck (reader)`) fall back to `gemma-4-e4b` just like chat.

---

## 2. Architecture & Storage Format

### 2.1 Frontend Key Schema (`src/i18n/catalog.ts`, `src/i18n/index.ts`)
- Namespaces:
  - `common.*` — shared actions (`Save`, `Cancel`, `Delete`, `Close`, `Reset`, `Retry`, `Confirm`)
  - `rail.*` — sidebar quick buttons, accordions, bookmarks, profile menu, footer buttons
  - `top.*` — top bar navigation tooltips, address placeholders, compare/watch/autofill/mode switches
  - `start.*`, `cmd.*` — Home greetings, date formatting, unlock card, empty feed hints, command bar actions
  - `chat.*` — composer hints, chips, attachments, model privacy notes, citation/audit badges, task cards, inline settings suggestions
  - `mail.*` — inbox/pings/orders/promos lanes, account controls, reader/compose actions
  - `news.*` — Top stories, For you, Perspectives, Topics, Sources, trust cap labels
  - `brain.*` — Brain search, entity cards, proposals, skills/red-team audit badges
  - `settings.*`, `settings_cards.*` — App-wide Appearance & Language, models, profiles/vault, providers, Google OAuth, mail accounts, inline card UI
  - `profile.*`, `status.*`, `time.*`, `err.*` — lock modal, telemetry popover, `Intl.RelativeTimeFormat`, normalized error banners
- Placeholder safety:
  - `t(key, vars?)` and `tCount(key, count, vars?)` substitute `{var}` tokens after validating the translated string retains every placeholder defined in `EN_CATALOG[key]`. Corrupted translations fall back to English for that key.
  - All DOM bindings continue escaping `t(...)` via `escapeHtml(...)` (catalog entries contain plain text only).
- Locale-aware formatting:
  - `formatRelativeTime` -> `Intl.RelativeTimeFormat(activeLang, ...)`
  - `formatHomeDateLine` -> `Intl.DateTimeFormat(activeLang, ...)`
  - `document.documentElement.lang = activeLang`; `document.documentElement.dir = activeDir` (`ltr` or `rtl`).

### 2.2 Sidecar App-Wide Store (`<app_data_dir>/i18n/`)
- Directory: `self.legacy_store_path.parent / "i18n"` (outside `profiles/<id>/`).
- `config.json`:
  ```json
  {
    "active_lang": "en",
    "updated_at": 1795524000
  }
  ```
- `<lang>.json` (per language normalized tag, e.g. `de.json`, `ja.json`, `pt-br.json`):
  ```json
  {
    "lang": "de",
    "label": "Deutsch",
    "dir": "ltr",
    "model": "gemma-4-e4b",
    "entries": {
      "rail.new": {
        "text": "Neu",
        "source_hash": "9f86d081884c",
        "model": "gemma-4-e4b",
        "custom": false,
        "fallback": false,
        "updated_at": 1795524000
      }
    }
  }
  ```
- Incremental hashing:
  - `source_hash = sha256(f"{text}|{hint or ''}|{int(bool(plural))}")[:12]`.
  - Background sync compares `EN_CATALOG` hashes against `<lang>.json`. Entries with `custom: true` are never overwritten by background or LLM re-translation unless reset.

### 2.3 LLM Batch Translation Engine (`sidecar/satz_i18n.py`)
- Uses `runtime.get_model_management_config()["roles"]["chat"]` (unless overridden).
- Chunks untranslated/stale keys into priority batches of **25–30 entries** (`rail.*`, `top.*`, `start.*`, `profile.*`, `settings.*` first; `mail.*`, `news.*`, `brain.*`, `chat.*`, `status.*`, `err.*` after).
- Each prompt requests strict JSON `{ "<key>": "<translated string>" }` with explicit constraints:
  - Preserve every `{placeholder}` verbatim.
  - Follow Satz UI conventions (`DESIGN_SYSTEM.md`): no em/en dashes (`-` or `·` instead), no emojis, sentence case, respect slot length hints.
  - Keep technical literals intact (`vault.enc`, `IMAP/SMTP`, `XOAUTH2`, `{mod}+K`, `[1]`).
- Validates JSON output, strips accidental markdown fences, normalizes dashes/emojis, verifies placeholder sets, retries invalid keys once in a smaller mini-batch, and persists valid translations after every batch so progress survives cancellation/restarts.
- Concurrency: serial under `gemma_infer_lock` for local `gemma-4-e4b`; bounded `ThreadPoolExecutor(max_workers=3)` for Cloud models.
- Never sends user PII, emails, bookmarks, or vault secrets (static `EN_CATALOG` entries only).

### 2.4 Sidecar HTTP & Settings Tool Contracts
- `GET /i18n/status?lang=<lang>`: active locale, list of saved language packs + coverage stats (`translated`, `missing`, `stale`, `custom`), resolved `default_model`, `privacy` (`local` vs `cloud`), and live background job progress.
- `GET /i18n/bundle?lang=<lang>`: returns full entry map `{ key: { text, source_hash, custom, fallback, model } }` + `lang`, `label`, `dir`.
- `POST /i18n/translate` (SSE stream + background-capable): accepts `{ target_lang, target_label?, catalog, model_id?, only_missing?: bool, background?: bool }`. Streams batch progress (`phase: "progress"`, `done_keys`, `total_keys`, `applied_delta`) and final summary. Supports `POST /i18n/cancel`.
- `POST /i18n/override`: set `active_lang`, upsert a single-key `custom: true` override, reset custom keys, or delete a pack.
- `GET /i18n/export` / `POST /i18n/import`: portable JSON backup/edit of custom packs.
- Settings tools (`sidecar/satz_tools/settings_i18n.py`, `origin == "settings"` only):
  - `settings_get_language_status`
  - `settings_switch_language`
  - `settings_prepare_language_translation` (emits `locale_translate_card`)
  - `settings_set_ui_translation_override`

---

## 3. Execution Milestones (`L1`–`L5`)

### L1 · Core Catalog, `t()` Runtime & AST Extractor
- Create `src/i18n/catalog.ts` and `src/i18n/index.ts`.
- Move `formatRelativeTime` / home date formatting to `Intl` wrappers.
- Create `scripts/i18n_extract.mjs` (TypeScript compiler API AST + template attribute scanner) to inventory unextracted UI strings and verify key/placeholder consistency (`--check`).
- **Gate:** `npm run build` passes cleanly; extractor audit runs cleanly.

### L2 · Frontend & Card String Extraction
- Migrate UI strings systematically by surface:
  1. Chrome & navigation: `src/rail.ts`, `src/tabs.ts`, `src/status.ts`, `src/keys.ts`
  2. Home & Command Bar: `src/start.ts`, `src/sources.ts`
  3. Settings & Brain: `src/knowledge.ts`
  4. Mail & News: `src/mail.ts`, `src/news.ts`
  5. Chat, Dialogs & Notifications: `src/chat.ts`, `src/main.ts`, `src/api.ts`, `src/state.ts`
- Support optional `title_key` / `subtitle_key` / `resolution_note_key` hydration on Settings UI cards in `sidecar/satz_tools/` + `src/chat.ts`.
- **Gate:** `npm run build` passes; `node scripts/i18n_extract.mjs --check` passes with 0 missing/orphan keys and 0 placeholder mismatches.

### L3 · Sidecar Translation Manager & Endpoints (`satz_i18n.py`)
- Implement `SatzI18nManager` in `sidecar/satz_i18n.py`, wire into `SatzSidecarRuntime` (`self.legacy_store_path.parent / "i18n"`), expose HTTP routes in `sidecar/satz_models.py`, and support SSE progress + background execution.
- Add `sidecar/test_i18n.py` covering local Gemma + Cloud `_complete_role_prompt` batching, malformed JSON retry, placeholder guard fallback, incremental `source_hash` diffing, `custom: true` preservation, app-wide persistence across profile switches, and cancel/resume.
- **Gate:** `pytest sidecar/test_i18n.py -v` passes.

### L4 · App-Wide Settings UI, Background Auto-Sync & Settings Chat
- Update top `Appearance` card in `src/knowledge.ts` to **App-wide preferences** (`Theme`, `Layout`, `Interface language` selector, `Translate new language...`, model/privacy note, live background sync indicator, collapsible **Customize strings** key editor, JSON import/export).
- Add silent startup/unlock background check in `src/main.ts`: if active language `!= "en"` and `catalog` has untranslated/stale keys (and selected default model is ready), trigger background `only_missing: true` translation and refresh UI cleanly as batches land.
- Cache active bundle in `localStorage` for instant zero-flash startup and sync `document.documentElement.lang` / `dir`.
- Add `sidecar/satz_tools/settings_i18n.py` and `locale_translate_card` renderer in `src/chat.ts`.
- **Gate:** `npm run build`, `cargo test`, and `pytest sidecar/test_settings_tools.py sidecar/test_i18n.py` pass.

### L5 · Verification, Long-String & RTL Polish
- Verify RTL CSS rules (`dir="rtl"`) and truncation resilience (e.g., long German labels in `.rail`, `.tab`, `.chip`, `.pill`, `.btn`).
- Full verification run: `npm run build`, `node scripts/i18n_extract.mjs --check`, CSS hygiene check (`0` hex literals, no non-computed inline `style=`), `cargo test`, and `pytest`.
- Update `docs/NOTES_v0.9.md` and `docs/design/DESIGN_SYSTEM.md` if any UI classes are added.
