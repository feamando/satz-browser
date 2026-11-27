# Tasks: `v0.16-autoupdater-release-automation`

- **Plan:** [v1.md](v1.md)
- **Status:** Complete

## Checklist
- [x] Audit full updater & GitHub release chain (`tauri.conf.json`, `src/updater.ts`, `.github/workflows/release.yml`, `scripts/release_version.py`, `scripts/git_sync.py`)
- [x] Author plan `v1.md` and task checklist `tasks.md`
- [x] Add `src/updater.ts` sequential `download()` -> `prepare_for_update` -> `install()` -> `relaunch()` fix
- [x] Extend `scripts/release_version.py` (`package-lock.json` sync, `ci-preflight`, `verify-updater-manifest`) and `scripts/git_sync.py` (`--bump`)
- [x] Upgrade `.github/workflows/release.yml` (3-stage preflight/matrix/verify-publish) and add `.github/workflows/ci.yml`
- [x] Update `dev/docs/RELEASE_RUNBOOK.md`, `dev/agents/release_management.md`, and `dev/agents/skills/satz-release-manager/SKILL.md`
- [x] Add unit tests in `sidecar/test_dev_brain.py` and run full verification (`npm run build`, `i18n_extract`, `cargo test`, `unittest`, `security_audit`, `dev_brain monitor`)
