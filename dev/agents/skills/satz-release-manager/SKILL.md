---
name: satz-release-manager
description: >-
  Use this skill whenever preparing, bumping major/minor/fix versions, tracking shipped
  model revisions, verifying, tagging, building, signing, or publishing Windows and macOS
  releases and updater updates for satz-browser.
---

# Satz Release & Version Manager Skill

Runbook: [RELEASE_RUNBOOK.md](../../../docs/RELEASE_RUNBOOK.md) · Protocol: [release_management.md](../../release_management.md) · Version CLI: [release_version.py](../../../../scripts/release_version.py) · Workflow: [.github/workflows/release.yml](../../../../.github/workflows/release.yml)

## Semver & Model Versioning Policy
- **`fix` (`patch`, e.g. `0.5.0 -> 0.5.1`):** Bug fixes, UI/i18n/hook fixes, and backward-compatible sidecar patches without schema or shipped-model weight changes.
- **`minor` (e.g. `0.5.0 -> 0.6.0`):** New browser/agent capabilities OR any **shipped Planck model weight/tokenizer update** (always re-verify `<90 MB` shard sizes and `sha256` checksums in `sidecar/models/planck/*/manifest.json`).
- **`major` (e.g. `0.x.y -> 1.0.0`):** Breaking storage, vault, or profile migrations.
- **Manifest Triplet:** `package.json`, `src-tauri/Cargo.toml`, and `src-tauri/tauri.conf.json` must ALWAYS share the exact same semver (`pre_commit_dev_sync.py` + `PreToolUse` `git tag` guard enforce this).

## Step-by-Step Release Workflow
1. **Inspect current state:**
   ```powershell
   ..\sgs\.venv\Scripts\python.exe scripts/release_version.py status
   ```
2. **Bump version cleanly (`fix` | `minor` | `major` | explicit `X.Y.Z`):**
   ```powershell
   ..\sgs\.venv\Scripts\python.exe scripts/release_version.py bump fix --notes "Short release summary"
   ```
   *(If updating shipped Planck weights, pass `--model-version <tag>` to stamp and hash-verify `sidecar/models/planck/*/manifest.json` simultaneously.)*
3. **Run mandatory release gate:**
   ```powershell
   ..\sgs\.venv\Scripts\python.exe dev/agents/hooks/release_gate.py
   ```
4. **Stage & build executables / signed updater packages:**
   - **Windows (`*_x64-setup.exe`, `*_x64_en-US.msi`, `.sig`):**
     `pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/build_preview.ps1`
   - **macOS (`.app`, `.dmg`, `.app.tar.gz`, `.sig`):**
     `./scripts/build_preview.sh` *(downloaded unsigned previews require `xattr -cr /Applications/satz.app` once)*
5. **Snapshot binaries + publish CI release (`latest.json` updater feed):**
   - Capture binary SHA256s/sizes & manifest snapshot: `..\sgs\.venv\Scripts\python.exe scripts/dev_brain.py snapshot`
   - Commit clean changes, tag & push: `git tag -a vX.Y.Z -m "Release vX.Y.Z" && git push origin main --tags`
   - `.github/workflows/release.yml` builds Windows + macOS in parallel, signs updater bundles via `TAURI_SIGNING_PRIVATE_KEY` (`~/.tauri/satz.key` locally, GitHub Secret in CI), and publishes `latest.json` for installed previews while keeping AppData (`satz.db`, Vault, Mail, Brain, downloaded HF LLMs) intact.
6. **Record telemetry & reindex Brain:**
   Append build sizes/durations to `dev/analytics/build_telemetry.jsonl` and run `python scripts/dev_brain.py reindex`.

## Field Notes (Windows & macOS Standalone Previews)
- Keep all `sidecar/requirements-runtime.txt` packages (including `httpx`) installed in local `../sgs/.venv` across Windows and macOS.
- To verify the embedded `python-runtime` inside a built `.app`/`.exe` on a dev machine, remove any leftover `"python"` and `"repo_root"` keys from AppData/Application Support `settings.json`, otherwise the app falls back to your local repo checkout + `../sgs/.venv`.
- Secondary build hosts lacking `~/.tauri/satz.key` automatically build `.app`/`.dmg`/installers via `scripts/build_preview.sh` / `.ps1` (`src-tauri/tauri.bundle.noupdater.conf.json` / `--no-updater`) without updater signature errors; signed updater bundles come from the key host or CI (`TAURI_SIGNING_PRIVATE_KEY`).
