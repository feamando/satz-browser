# Tasks: `v0.10-standalone-packaging`

- **Plan:** [v1.md](v1.md)
- **Status:** Complete (awaiting first GitHub secret + `v*` tag push for macOS CI build)

## Checklist
- [x] Ship Planck runtime & split `<90 MB` sharded weights (`sidecar/planck_vendor/`, `sidecar/models/planck/`)
- [x] Implement HF downloader & local path linker in Settings (`sidecar/satz_local_models.py`, `src/knowledge.ts`)
- [x] Fix missing-Gemma startup preload & `CrossReader` PyTorch `2.15+` `onednn` quantization handling
- [x] Create `scripts/prepare_sidecar_bundle.py` & `sidecar/requirements-runtime.txt`
- [x] Wire `resource_dir()` fallback & `prepare_for_update` in `src-tauri/src/lib.rs`
- [x] Wire `tauri-plugin-updater` + `tauri-plugin-process` + Settings UI (`src/updater.ts`)
- [x] Build & sign Windows NSIS (`402.07 MB`) & MSI (`518.77 MB`) preview installers via `scripts/build_preview.ps1`
- [ ] Set `TAURI_SIGNING_PRIVATE_KEY` in GitHub Secrets & push release tag to build macOS `.dmg`
