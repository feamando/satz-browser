# Development Analytics & Telemetry (`dev/analytics/`)

Tracks build sizes, packaging timings, test pass counts, Dev Brain retrieval quality trends, and runtime harness telemetry observations.

## Files
- [build_telemetry.jsonl](build_telemetry.jsonl) — Append-only JSONL records for standalone builds, installer sizes, and suite execution results.
- [dev_brain_eval_history.jsonl](dev_brain_eval_history.jsonl) — Append-only retrieval quality metrics (`hit_at_1`, `recall_at_3`, `recall_at_5`, `mrr`, `avg_latency_ms`) emitted by `scripts/dev_brain.py eval`.
- [harness_telemetry_notes.md](harness_telemetry_notes.md) — Developer synthesis notes connecting runtime `satz_harness_signals` patterns to prompt/model defaults.
