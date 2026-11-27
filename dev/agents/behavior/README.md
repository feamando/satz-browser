# Developer Behavior Analysis (`dev/agents/behavior/`)

Captures Nikita Gorshkov's verified engineering preferences, recurring friction patterns, and tool/workflow adjustments so Antigravity and Claude Code adapt cleanly across sessions.

- [developer_patterns.yaml](developer_patterns.yaml) — Persistent engineering rules learned from real sessions.
- [behavior_log.jsonl](behavior_log.jsonl) — Structured distilled event stream appended by agent hooks and skill promotions.
- `raw_events.sqlite` *(gitignored)* — Fast local SQLite queue populated by `dev/agents/hooks/behavior_eval_store.py` (`PreInvocation`, `PostToolUse`, `PreToolUse`, `Stop`) without dirtying `git status`.
- [scripts/agent_background_worker.py](../../../scripts/agent_background_worker.py) — Detached background analyzer triggered on `Stop` to cluster repeated tasks into draft skills (`proposals/<slug>/SKILL.md`), extract `rule_candidates.json`, and generate/run `auto_eval_cases.yaml`. Approve staged proposals with `python scripts/agent_background_worker.py approve <slug>`.
