# Changelog

All notable milestone releases and pipeline changes for `satz-browser`. Historical milestone logs remain preserved in `NOTES_v0.3.md` through `NOTES_v0.9.md`.

## [0.5.1] - 2026-11-27
### Changed
- Release v0.5.1: first-run onboarding, Planck default launcher, dev hub/brain & hooks, security gates, macOS WebKit fixes, and automated dual-OS CI updater pipeline

## [0.5.0] - 2026-11-26 (v0.5 Parity + v0.6-v0.11 Cumulative Baseline)
### Added
- **Standalone Packaging & Auto-Updater (`v0.10`):** Relocatable Python 3.12 (`python-build-standalone`) + lean CPU PyTorch staging via `scripts/prepare_sidecar_bundle.py`, Tauri resource bundling (`src-tauri/tauri.bundle.conf.json`), `prepare_for_update` sidecar teardown in `src-tauri/src/lib.rs`, Ed25519 updater UI (`src/updater.ts`), and `.github/workflows/release.yml`.
- **Shipped Planck & Local Model Management:** Vendored `sidecar/planck_vendor/` + `<90 MB` sharded weights in `sidecar/models/planck/` (`xreader_planck`, `planck13`, `tokenizer.model`), Hugging Face downloader & local folder/checkpoint linking in `sidecar/satz_local_models.py`, and clean missing-Gemma startup/cloud fallbacks.
- **Dev Pipeline & Dev Brain (`v0.11`):** Unified `dev/` workspace (`docs/`, `versions/`, `analytics/`, `agents/`, `plans/`, `brain/`), cross-harness Antigravity/Claude Code agent rules & hooks, and `scripts/dev_brain.py` graph DB + retrieval evaluation harness.
- **Profile Portability, UI Localization, Settings & News:** Encrypted offline `.satzprofile` export/import/merge, app-wide LLM UI localization (`v0.9`), conversational Settings (`v0.8`), tokenized Design System (`v0.7`), and Satz News (`v0.6`).

### Fixed
- `CrossReader` (`sidecar/planck_vendor/src/planck3/xreader.py`) updated to handle `onednn` / PyTorch `2.15+` CPU quantization engines cleanly without raising `StopIteration`.
