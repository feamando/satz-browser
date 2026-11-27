# Release Runbook (Windows & macOS Standalone Previews)

Links: [[../agents/INSTRUCTIONS.md]] · [[../plans/v0.10-standalone-packaging/v1.md]] · [PLATFORMS.md](PLATFORMS.md)

## 1. Prerequisites
- **Versions synchronized across all three manifests:**
  - `package.json` (`"version"`)
  - `src-tauri/Cargo.toml` (`version`)
  - `src-tauri/tauri.conf.json` (`"version"`)
- **Ed25519 Updater Signing Key:**
  - Public key lives in `src-tauri/tauri.conf.json` (`plugins.updater.pubkey`).
  - Private key lives locally at `~/.tauri/satz.key` (Windows: `%USERPROFILE%\.tauri\satz.key`) and in GitHub repo secret `TAURI_SIGNING_PRIVATE_KEY` (never commit private keys).
- **Pre-release gate:** Run `dev/agents/hooks/release_gate.py` before tagging.

## 2. Local Standalone Build Commands

### Windows (`x86_64`)
```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/build_preview.ps1
```
Options: `-SidecarOnly` (skip reinstalling `python-runtime`), `-Cuda` (bundle CUDA instead of lean CPU PyTorch), `-ForcePython` (rebuild cached runtime).
Outputs under `src-tauri/target/release/bundle/`: NSIS `*_x64-setup.exe`, WiX `*_x64_en-US.msi`, and `.sig` files (pass `-NoUpdater`, or omit `~/.tauri/satz.key`, to build local installers without updater `.sig` artifacts).

### macOS (`aarch64` Apple Silicon / Intel)
```bash
./scripts/build_preview.sh
```
Outputs under `src-tauri/target/release/bundle/`: `.app`, `.dmg`, and signed updater artifacts.
- **Note on updater signing (`satz.key`):** Both `build_preview.sh` and `build_preview.ps1` automatically apply `src-tauri/tauri.bundle.noupdater.conf.json` (pass `--no-updater` / `-NoUpdater` explicitly too) when `~/.tauri/satz.key` and `TAURI_SIGNING_PRIVATE_KEY` are absent, so `.app` / `.dmg` builds complete cleanly on secondary Macs without updater signing errors. Copy `~/.tauri/satz.key` out-of-band or rely on GitHub Actions (`TAURI_SIGNING_PRIVATE_KEY` secret) for signed updater releases.
- **Note on verifying true bundled runtime on dev Macs:** Remove any leftover `"python"` and `"repo_root"` keys from `~/Library/Application Support/com.satz.browser/settings.json` when testing `satz.app`; otherwise `resolve_python_executable_with_resources()` executes your local checkout + `../sgs/.venv` instead of the embedded `Contents/Resources/python-runtime`.
For **downloaded unsigned macOS previews**, preview users drag `satz.app` to `/Applications` and strip Gatekeeper quarantine once:
```bash
xattr -cr /Applications/satz.app
```

## 3. Automated GitHub Actions Release (`v*`)
1. Record snapshot & update release notes in `dev/versions/` (`scripts/dev_brain.py snapshot`).
2. Bump version across all 3 manifests and commit cleanly (`pre_commit_dev_sync.py` checks sync).
3. Tag & push:
   ```bash
   git tag v0.5.1
   git push origin main --tags
   ```
4. `.github/workflows/release.yml` builds Windows and macOS bundles in parallel, generates `latest.json` + `.sig` signatures, and creates a draft release on `feamando/satz-browser`.
5. Review draft notes (including macOS `xattr -cr` note) and publish release; existing preview installs upgrade cleanly in **Settings -> Appearance & Language -> App updates**.
6. Append release metrics (`installer size`, `test counts`, `commit SHA`) to `dev/analytics/build_telemetry.jsonl` and re-index `dev/brain/`.
