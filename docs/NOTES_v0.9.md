# Satz v0.9 Notes: App-Wide UI Localization with User-Model Translation

Plan: `docs/PLAN_v0.9_localization.md` · Spec: `docs/design/DESIGN_SYSTEM.md` (v1.2) · Platform: Windows (`1440x900`)

## Scope & Confirmed Decisions (2026-11-24)
- **App-wide scope across profiles:** Custom language packs live in `<app_data_dir>/i18n/config.json` and `<app_data_dir>/i18n/<lang>.json` (mirrored to `localStorage` under `satz.ui.locale`, `satz.ui.dir`, and `satz.ui.i18n.<lang>`) and appear inside the top **App-wide preferences** card (`Theme`, `Layout`, `Interface language`) in Manual Settings, independent of profile switches or vault locks.
- **Silent background sync for untranslated keys:** When active language `!= "en"`, missing or stale (`source_hash` changed) UI keys translate automatically in the background using the user's selected default chat model (`roles.chat`).
- **Model-agnostic execution:** Routes through `SatzSidecarRuntime._complete_role_prompt(...)`, supporting local `gemma-4-e4b` and configured Cloud models (`gemini`, `anthropic`, `openai`, `mistral`) with live SSE progress and cancellation.

## Milestone Log

### L1 · Core Catalog, `t()` Runtime & AST Extractor
- **Status:** Complete
- **Files:** `src/i18n/catalog.ts`, `src/i18n/index.ts`, `scripts/i18n_extract.mjs`
- **Notes:** Extracted canonical English strings into `EN_CATALOG` (`1145` keys) with optional `one` plurals and `hint` context; implemented `t()`, `tCount()`, `tDynamic()`, `switchActiveLocale()`, `setActiveLocaleBundle()`, `mergeActiveLocaleEntries()`, `exportCatalogManifest()`, `applyUiLocalePreferences()`, and `Intl` relative-time/date formatting; added TS AST checker `scripts/i18n_extract.mjs --check` (`1491` call sites, `7` unused keys referenced dynamically via server keys/manifest, `0` errors).

### L2 · Frontend & Card String Extraction
- **Status:** Complete
- **Files:** `src/rail.ts`, `src/tabs.ts`, `src/status.ts`, `src/keys.ts`, `src/start.ts`, `src/sources.ts`, `src/knowledge.ts`, `src/mail.ts`, `src/news.ts`, `src/chat.ts`, `src/main.ts`, `src/api.ts`, `src/state.ts`, `src/types.ts`
- **Notes:** Migrated UI chrome, tabs, settings, mail, news, chat, status, and command/shortcut views onto `t()` / `tCount()` / `tDynamic()` with `escapeHtml(...)` wrappers around interpolated translations and eliminated em/en dashes from UI copy.

### L3 · Sidecar Translation Manager & Endpoints (`satz_i18n.py`)
- **Status:** Complete
- **Files:** `sidecar/satz_i18n.py`, `sidecar/satz_models.py`, `sidecar/satz_google_auth.py`, `sidecar/test_i18n.py`
- **Notes:** Implemented `SatzI18nManager` (`parse_ts_catalog_file`, `normalize_lang_spec` with RTL detection, `resolve_translation_model` with non-generative guard, 25-key priority batching, `{placeholder}` verification + 1-shot retry + corrupted-key fallback, `custom: true` protection, `source_hash` diffing, synchronous/SSE/background thread translation + cancellation + override + pack JSON export/import); exposed `/i18n/status`, `/i18n/bundle`, `/i18n/translate`, `/i18n/cancel`, `/i18n/override`, `/i18n/export`, and `/i18n/import`; localized OAuth callback HTML `<html lang dir>`.

### L4 · App-Wide Settings UI, Background Auto-Sync & Settings Chat
- **Status:** Complete
- **Files:** `src/knowledge.ts`, `src/chat.ts`, `src/main.ts`, `src/api.ts`, `src/state.ts`, `src/types.ts`, `sidecar/satz_tools/settings_i18n.py`, `sidecar/satz_tools/__init__.py`, `sidecar/satz_tools/fallback.py`, `sidecar/test_settings_tools.py`
- **Notes:** Added app-wide **Interface language** controls (`#kb-app-language-slot`) to `renderKnowledgeView`, live `.meter` progress indicator, focus-preserving partial re-renders for the collapsed **Customize strings** key override editor, background `syncAppI18nState()` sync on startup and profile switch/unlock, 4 declarative Settings Chat tools (`settings_get_language_status`, `settings_switch_language`, `settings_prepare_language_translation`, `settings_set_ui_translation_override`), fallback card detection, and inline `locale_translate_card` UI in Settings Chat.

### L5 · Verification, Long-String & RTL Polish
- **Status:** Complete
- **Files:** `src/design-system/components.css`, `docs/design/DESIGN_SYSTEM.md`, `docs/NOTES_v0.9.md`
- **Notes:** Added `.kb-app-lang-*` layout styles (flex wrapping for longer localized labels, bounded table scroll container for override editor) and `[dir="rtl"]` alignment/border/margin mirroring rules to `src/design-system/components.css`; documented section `5.18` classes in `docs/design/DESIGN_SYSTEM.md` §7. Zero hex literals or em/en dashes remain in component CSS/TS UI code.

## Verification Results
- `npm run build` (`tsc && vite build`): passed (`✓ built in 935ms`)
- `node scripts/i18n_extract.mjs --check`: `Catalog keys: 1145, call sites: 1491, unused: 7, errors: 0`
- `..\sgs\.venv\Scripts\python.exe -m pytest sidecar/test_i18n.py sidecar/test_settings_tools.py -v`: `13 passed in 7.81s`
- `..\sgs\.venv\Scripts\python.exe -m pytest sidecar/ -v`: `101 passed in 557.33s (0:09:17)`
- `cargo test --manifest-path src-tauri\Cargo.toml`: `14 passed; 0 failed` (`satz_browser_lib`)
