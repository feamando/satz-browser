# Tasks: `v0.13-browser-telemetry`

- **Plan:** [v2.md](v2.md)
- **Status:** Complete

## Checklist
- [x] Implement `sidecar/satz_telemetry.py` creating `<app_data_dir>/dev/` with SQLite store, PII scrubbing, and hosted-ready export cursors
- [x] Wire runtime telemetry + `/telemetry/*` GET/POST endpoints and `/evals/capture` + `/evals/run` hooks in `sidecar/satz_models.py`
- [x] Add automated verification suite in `sidecar/test_telemetry.py`
- [x] Surface local telemetry inspector & opt-in hosted sync toggle inside Settings (`src/knowledge.ts`)
- [x] Implement opt-in HTTPS batch uploader for hosted Satz analytics endpoint (`flush_hosted_sync` + `POST /telemetry/sync`)
