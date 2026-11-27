# Tasks: `v0.14-first-run-onboarding`

- **Plan:** [v1.md](v1.md)
- **Status:** Complete

## Checklist
- [x] Research existing profile, model setup, rail, and Planck fallback flows
- [x] Draft plan `v1.md` and task tracker `tasks.md`
- [x] Ensure `conv-mail` initializes on fresh DB (`src-tauri/src/db.rs`, `src/main.ts`) and guard `run_answer` `sgs_root` (`sidecar/satz_models.py`)
- [x] Add onboarding & tour state + Planck fallback selection (`src/state.ts`, `src/tabs.ts`)
- [x] Build `src/onboarding.ts` (Step 1 Create/Upload/Demo, Step 2 Cloud API Key / Local Gemma HF Download, 5-step left-rail click-through tooltip tour)
- [x] Wire onboarding, Demo mode, inline `.satzprofile` upload parity, and tour replay across `src/main.ts`, `src/start.ts`, `src/rail.ts`, `src/knowledge.ts`, `src/mail.ts`, `src/news.ts`, `src/drives.ts`
- [x] Add tokenized styles (`src/design-system/components.css`) and i18n keys (`src/i18n/catalog.ts`)
- [x] Run automated checks (`i18n_extract.mjs --check`, `npm run build`, `cargo test`, Python `unittest` suite)
- [x] Re-index Dev Brain (`dev_brain.py reindex`, `monitor`, `eval`)
