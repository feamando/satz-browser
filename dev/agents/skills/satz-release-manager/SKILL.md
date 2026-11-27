---
name: satz-release-manager
description: >-
  Use this skill whenever preparing, verifying, tagging, building, or debugging
  standalone Windows and macOS releases, PyTorch CPU bundling, updater signatures,
  or GitHub Actions release workflows for satz-browser.
---

# Satz Release Manager Skill

Canonical runbook: [RELEASE_RUNBOOK.md](../../../docs/RELEASE_RUNBOOK.md) · Workflow: [.github/workflows/release.yml](../../../../.github/workflows/release.yml)

## Steps
1. Verify plan & task completion under `dev/plans/` and synchronize semver across `package.json`, `src-tauri/Cargo.toml`, and `src-tauri/tauri.conf.json`.
2. Run pre-release gate:
   `python dev/agents/hooks/release_gate.py`
3. Capture release snapshot into `dev/versions/snapshots/` and append release notes to `dev/versions/CHANGELOG.md`:
   `python scripts/dev_brain.py snapshot`
4. Stage relocatable Python 3.12 CPU runtime + clean sidecar (`scripts/prepare_sidecar_bundle.py`) and run isolated `test_local_models` under staged `python-runtime`.
5. Build locally (`scripts/build_preview.ps1` on Windows / `scripts/build_preview.sh` on macOS) or push version tag `vX.Y.Z` to trigger `.github/workflows/release.yml`.
6. Record installer sizes and test counts inside `dev/analytics/build_telemetry.jsonl` and reindex `dev/brain/`.

## Verification Notes
- On unsigned macOS `.app` previews downloaded from CI, always include `xattr -cr /Applications/satz.app`.
- Ensure Ed25519 private signing key remains strictly outside git (`~/.tauri/satz.key` and GitHub Secret `TAURI_SIGNING_PRIVATE_KEY`).
