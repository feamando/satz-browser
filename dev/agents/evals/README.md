# Agent Evals & Error Logging (`dev/agents/evals/`)

Stores development pipeline regression cases, structured engineering error/postmortem logs, and the ground-truth retrieval benchmark for `dev/brain/`.

- [error_log.jsonl](error_log.jsonl) — Timestamped build/runtime failures, root causes, and fix links.
- [agent_eval_cases.yaml](agent_eval_cases.yaml) — Pipeline invariants verified by `release_gate.py`.
- [dev_brain_eval_cases.json](dev_brain_eval_cases.json) — Labeled query suite used by `scripts/dev_brain.py eval` to score Recall@3, Recall@5, MRR, and latency.
