---
name: satz-dev-brain
description: >-
  Use this skill to search, inspect graph relationships, re-index, monitor integrity,
  and run accuracy evals against the Satz Development Brain DB in dev/brain/.
---

# Satz Dev Brain Index Skill

Script: [dev_brain.py](../../../../scripts/dev_brain.py) · DB Root: [dev/brain/](../../../brain/)

## Steps
1. Search across all docs, plans, version notes, roles, hooks, skills, analytics, and evals:
   `python scripts/dev_brain.py search "<query>" --neighbors --limit 8`
2. Inspect a specific node and its 1-hop / 2-hop graph connections:
   `python scripts/dev_brain.py node <node-id-or-path> --depth 2`
3. After creating or modifying files inside `dev/` (or migrating docs), refresh the Brain Markdown registry and SQLite graph DB:
   `python scripts/dev_brain.py reindex`
4. Check freshness, broken links, FTS5 parity, and graph connectivity:
   `python scripts/dev_brain.py monitor`
5. Run labeled retrieval accuracy benchmarks:
   `python scripts/dev_brain.py eval --min-mrr 0.70 --min-recall5 0.85`
