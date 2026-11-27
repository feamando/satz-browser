# Tasks: `v0.11-dev-pipeline-brain`

- **Plan:** [v1.md](v1.md)
- **Status:** Complete

## Checklist
- [x] Update `.gitignore` with `!dev/brain/brain_index.sqlite` exception
- [x] Create `dev/` tree (`docs/`, `versions/`, `analytics/`, `agents/`, `plans/`, `brain/`) & migrate historical docs
- [x] Populate `dev/agents/` instructions, hooks, skills, developer behavior, roles, and evals + root bridges
- [x] Implement `scripts/dev_brain.py` (Satz Brain mechanics + committed SQLite FTS5/graph/Planck13 DB)
- [x] Implement search/retrieval, integrity monitor, and labeled retrieval eval suite (`MRR`, `Recall@3`, `Recall@5`)
- [x] Generate initial `v0.5.0` snapshot, build `brain_index.sqlite`, and pass automated unit & eval tests
