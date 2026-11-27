# Release Management Protocol (`satz-browser`)

Reference from [INSTRUCTIONS.md](INSTRUCTIONS.md) · Runbook: [RELEASE_RUNBOOK.md](../docs/RELEASE_RUNBOOK.md) · Skill: [satz-release-manager](skills/satz-release-manager/SKILL.md)

## 1. Versioning & Manifest Alignment
Every release requires an exact semver match across all three manifests (verified automatically by `dev/agents/hooks/pre_commit_dev_sync.py`):
- `package.json` (`"version"`)
- `src-tauri/Cargo.toml` (`version`)
- `src-tauri/tauri.conf.json` (`"version"`)

Never allow model files larger than `90 MB` under `sidecar/models/planck/` (standard Git, no Git LFS).

## 2. Mandatory Pre-Release Verification Gate
Run before every local preview bundle or release tag:
```powershell
..\sgs\.venv\Scripts\python.exe dev/agents/hooks/release_gate.py
```
`release_gate.py` enforces:
1. Manifest semver parity and UI/model weight hygiene checks
2. `npm run build` and `node scripts/i18n_extract.mjs --check`
3. `cargo test --manifest-path src-tauri/Cargo.toml`
4. Core sidecar regression `unittest` modules (unless `--quick` is explicitly passed for UI-only dry runs)
5. `scripts/dev_brain.py monitor` + `eval` retrieval thresholds

## 3. Standalone Runtime Staging (`scripts/prepare_sidecar_bundle.py`)
- Uses `uv` relocatable Python 3.12 (`python-build-standalone`) and `sidecar/requirements-runtime.txt` into `src-tauri/target/staged-resources/` (`sidecar/` + `python-runtime/`).
- Strips `test_*.py`, `__pycache__/`, `stdlib/test`, `tkinter`, `idlelib`, and removes `EXTERNALLY-MANAGED` during install.
- Windows installs CPU PyTorch by default (`--cuda` optional for local GPU installers); macOS installs default `arm64` MPS-capable wheels.
- Validate isolated runtime before installer compression:
  - Execute `test_local_models` with staged `python-runtime/python.exe -I` (`PYTHONNOUSERSITE=1`) and staged `sidecar/` with zero `../sgs`.

## 4. Signing Keys & Bundled Release Artifacts
- **Updater Signing (`tauri-plugin-updater`):** Public Ed25519 key in `src-tauri/tauri.conf.json` (`plugins.updater.pubkey`). Private key lives strictly outside the repo at `~/.tauri/satz.key` and GitHub secret `TAURI_SIGNING_PRIVATE_KEY`.
- **Tauri Overlay Config:** Always pass `--config src-tauri/tauri.bundle.conf.json` (`createUpdaterArtifacts: true` + `resources`) for distributable previews.
- **Local Previews:**
  - Windows: `pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/build_preview.ps1` -> `*_x64-setup.exe`, `*_x64_en-US.msi`, `.sig`
  - macOS: `./scripts/build_preview.sh` -> `.app`, `.dmg`, `.app.tar.gz`, `.sig`

## 5. CI Multi-OS Release (`v*` Tags) & Install Notes
1. Capture snapshot & changelog entry:
   `python scripts/dev_brain.py snapshot` and update [CHANGELOG.md](../versions/CHANGELOG.md).
2. Commit cleanly, tag `vX.Y.Z`, and push (`git push origin main --tags`).
3. `.github/workflows/release.yml` runs `windows-latest` and `macos-latest` in parallel, caches `python-runtime` by `requirements-runtime.txt` hash, signs updater payloads, and emits a draft GitHub Release with `latest.json`.
4. Preview notes must state:
   - **macOS (unsigned preview):** drag `satz.app` into `/Applications`, then run once: `xattr -cr /Applications/satz.app`
   - **Windows:** click **More info -> Run anyway** if SmartScreen prompts
5. Record build sizes/timings in [build_telemetry.jsonl](../analytics/build_telemetry.jsonl) and run `python scripts/dev_brain.py reindex`.

## 6. Sidecar Shutdown Safety During Self-Update
In `src-tauri/src/lib.rs`, `src/updater.ts` invokes `prepare_for_update` right before `downloadAndInstall()` + `relaunch()`, setting `SIDE_SHUTTING_DOWN` to halt the watchdog and killing the sidecar tree cleanly so Windows installer replacement never hits file locks. User data in `%APPDATA%\com.satz.browser\` / `~/Library/Application Support/com.satz.browser/` stays untouched.
