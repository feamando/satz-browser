# Agent Evals & Error Logging (`dev/agents/evals/`)

Stores development pipeline regression cases, structured engineering error/postmortem logs, and the ground-truth retrieval benchmark for `dev/brain/`.

- [error_log.jsonl](error_log.jsonl) — Timestamped build/runtime/agent failures, root causes, and fix links (appended manually or automatically by `PostToolUse`/`Stop` hooks).
- [agent_eval_cases.yaml](agent_eval_cases.yaml) — Core pipeline invariants verified by `release_gate.py`.
- `auto_eval_cases.yaml` & `eval_history.jsonl` — Automatically synthesized regression assertions from captured agent/tool failures and background evaluation history (`scripts/agent_background_worker.py`).
- [dev_brain_eval_cases.json](dev_brain_eval_cases.json) — Labeled query suite used by `scripts/dev_brain.py eval` to score Recall@3, Recall@5, MRR, and latency.
