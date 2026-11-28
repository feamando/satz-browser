# Tasks: `v0.17-macos-parity-telemetry-ci`

- **Plan:** [v1.md](v1.md)
- **Status:** Complete

## Checklist
- [x] Research repo state after `v0.5.1` (`6bf9d71`), inspect failures, and draft `v1.md`
- [x] Track 1: Fix `sidecar/test_i18n.py` `/var` symlink `.resolve()`, add `-25244` Keychain fallback + `SATZ_MEMORY_KEYRING=1` in `sidecar/satz_passwords.py`, clean `TestSatzSidecar.tearDown()`, add `.venv/` to `.gitignore`, and provision local Python 3.12 `.venv` with `requirements-runtime.txt`
- [x] Track 2: Implement `flush_hosted_sync` + `POST /telemetry/sync` (`sidecar/satz_telemetry.py`, `sidecar/satz_models.py`, `sidecar/test_telemetry.py`), build Settings Telemetry Inspector & Hosted Sync UI (`src/knowledge.ts`, `src/api.ts`, `src/types.ts`, `src/state.ts`, `src/main.ts`, `src/i18n/catalog.ts`, `src/design-system/components.css`), and complete `v0.13` + `v0.10` task trackers
- [x] Track 3: Stage & test isolated `python-runtime -I` with `../sgs` bypassed, run `./scripts/build_preview.sh` on macOS, smoke-check built `.app` / sidecar endpoints, and record telemetry/snapshot in `dev/`
- [x] Dev Hardening: Extend `.github/workflows/ci.yml` + `dev/agents/hooks/release_gate.py` + `dev/agents/release_management.md` + `dev/agents/core_dev_flows.md` + `dev/agents/evals/error_log.jsonl` so Windows builds catch macOS/runtime/keychain regressions early
- [x] Final Verification: Clean git diff, full `release_gate.py` pass on macOS, `dev_brain.py reindex && monitor && eval` pass
