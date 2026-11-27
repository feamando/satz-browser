# Satz Development Brain (`dev/brain/`)

Running knowledge graph and hybrid search index covering everything inside `dev/` (plus `docs/design/` and `docs/evals/`), powered by `sidecar/satz_brain.py` core mechanics (`SatzBrain`, `registry.yaml`, compressed pipe-delimited `BRAIN.md`, and `PlanckEncoder` semantic embeddings) backed by `brain_index.sqlite`.

## Tracked Artifacts
- `registry.yaml` — Canonical `SatzBrain` entity, alias, and relationship registry.
- `BRAIN.md` — Two-tier pipe-delimited developer knowledge index for agent context injection.
- `brain_index.sqlite` — Committed single-file SQLite DB (`journal_mode=DELETE`) storing `nodes`, directed `edges`, `nodes_fts` (BM25 FTS5), `embeddings` (`PlanckEncoder` / hash fallback), and `eval_runs`.

## Usage
```powershell
# Re-index dev/ + sync SatzBrain markdown graph & SQLite DB
..\sgs\.venv\Scripts\python.exe scripts/dev_brain.py reindex

# Search across all development docs, plans, versions, skills, hooks, roles, and errors
..\sgs\.venv\Scripts\python.exe scripts/dev_brain.py search "unsigned macOS xattr" --neighbors

# Inspect node details & 2-hop graph connections
..\sgs\.venv\Scripts\python.exe scripts/dev_brain.py node dev/docs/RELEASE_RUNBOOK.md --depth 2

# Check freshness, broken internal links, FTS5 sync, and graph metrics
..\sgs\.venv\Scripts\python.exe scripts/dev_brain.py monitor

# Evaluate retrieval accuracy (Hit@1, Recall@3, Recall@5, MRR, expected terms)
..\sgs\.venv\Scripts\python.exe scripts/dev_brain.py eval --record --min-mrr 0.70 --min-recall5 0.85
```
