# Development Analytics & Telemetry (`dev/analytics/`)

Tracks build sizes, packaging timings, test pass counts, Dev Brain retrieval quality trends, and runtime harness telemetry observations.

## Files
- [build_telemetry.jsonl](build_telemetry.jsonl) — Append-only JSONL records for standalone builds, installer sizes, and suite execution results.
- [dev_brain_eval_history.jsonl](dev_brain_eval_history.jsonl) — Append-only retrieval quality metrics (`hit_at_1`, `recall_at_3`, `recall_at_5`, `mrr`, `avg_latency_ms`) emitted by `scripts/dev_brain.py eval`.
- [harness_telemetry_notes.md](harness_telemetry_notes.md) — Developer synthesis notes connecting runtime signals patterns to prompt/model defaults.

## Per-Instance Browser Telemetry (`<app_data_dir>/dev/`)
Every installed Satz Browser instance initializes its own local `dev/` directory via `sidecar/satz_telemetry.py` (`SatzTelemetryManager`):
- `analytics/telemetry.sqlite` & `events.jsonl`: PII-scrubbed runtime, harness, shell, updater, and eval events (`hosted_sync_enabled: false` by default).
- `instance.json`: install UUID, app semver, platform, and future opt-in hosted endpoint metadata (`/telemetry/summary`, `/telemetry/export`, `/telemetry/ack`).
- Spec: [v0.13-browser-telemetry](../plans/v0.13-browser-telemetry/v1.md).
