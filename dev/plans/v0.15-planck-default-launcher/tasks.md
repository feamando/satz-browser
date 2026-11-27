# Tasks: `v0.15-planck-default-launcher`

- **Plan:** [v1.md](v1.md)
- **Status:** Complete

## Checklist
- [x] Research launcher, preload, Settings fallback, News pipeline, and frontend defaults
- [x] Author plan `v1.md` and task checklist `tasks.md`
- [x] Set Rust `preload_gemma: false` default (`src-tauri/src/lib.rs`)
- [x] Gate sidecar preload on explicit `model_role_chat` config & default roles to Planck (`sidecar/satz_models.py`, `sidecar/satz_local_models.py`, `sidecar/satz_mail.py`)
- [x] Expand deterministic Settings fallback (`sidecar/satz_tools/fallback.py`) and clean Planck/template News handling (`sidecar/satz_news.py`)
- [x] Update frontend default model selection, Settings role options, and chat routing (`src/state.ts`, `src/main.ts`, `src/knowledge.ts`, `src/api.ts`)
- [x] Update & run Rust (`17 passed`), TS/i18n (`build` + `i18n_extract`), and Python sidecar (`102 passed`) unit tests, then re-index Dev Brain
