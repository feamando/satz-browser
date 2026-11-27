# Satz Browser Development Hub (`dev/`)

Central engineering workspace for managing Satz Browser architecture, documentation, releases, version snapshots, analytics, agent instructions/skills/hooks/roles/evals, versioned plans, and the **Dev Brain Graph DB**.

## Directory Map

| Folder | Purpose | Key Entrypoints |
| :--- | :--- | :--- |
| [docs/](docs/) | Technical architecture, platform notes, release runbook, research | [ARCHITECTURE.md](docs/ARCHITECTURE.md), [RELEASE_RUNBOOK.md](docs/RELEASE_RUNBOOK.md), [PLATFORMS.md](docs/PLATFORMS.md) |
| [versions/](versions/) | Release history (`NOTES_v*.md`), changelog, point-in-time build snapshots | [CHANGELOG.md](versions/CHANGELOG.md), [snapshots/](versions/snapshots/) |
| [analytics/](analytics/) | Build size/timing telemetry, Dev Brain eval time-series, harness analysis | [build_telemetry.jsonl](analytics/build_telemetry.jsonl), [dev_brain_eval_history.jsonl](analytics/dev_brain_eval_history.jsonl) |
| [agents/](agents/) | Core instructions for Antigravity & Claude Code (especially release management) | [INSTRUCTIONS.md](agents/INSTRUCTIONS.md), [hooks/](agents/hooks/), [skills/](agents/skills/), [behavior/](agents/behavior/), [roles/](agents/roles/), [evals/](agents/evals/) |
| [plans/](plans/) | Versioned implementation plans (`v1.md`, `v2.md`, ...) & `tasks.md` per plan | [v0.10-standalone-packaging/](plans/v0.10-standalone-packaging/), [v0.11-dev-pipeline-brain/](plans/v0.11-dev-pipeline-brain/) |
| [brain/](brain/) | Committed Satz Dev Brain graph index (`BRAIN.md`, `registry.yaml`, `brain_index.sqlite`) | [README.md](brain/README.md), [BRAIN.md](brain/BRAIN.md) |

> **Runtime Artifacts Kept at Root [docs/](../docs/):** App runtime eval fixtures (`docs/evals/`), generated design gallery (`docs/design/`), README screenshots (`docs/screenshots/`), and smoke captures (`docs/smoke/`) remain under `../docs/` to keep existing scripts, README embeds, and test suites intact. All of them are still indexed by `dev/brain/`.

## Quick Commands

```powershell
# Rebuild Dev Brain graph index + SQLite DB (uses Planck13 semantic embeddings when present)
..\sgs\.venv\Scripts\python.exe scripts/dev_brain.py reindex

# Hybrid search (FTS5 + Planck13 semantic + 1-hop graph neighbors)
..\sgs\.venv\Scripts\python.exe scripts/dev_brain.py search "release xattr updater" --neighbors

# Monitor graph freshness, orphan links, FTS5 sync, and latency
..\sgs\.venv\Scripts\python.exe scripts/dev_brain.py monitor

# Run labeled retrieval evaluation (Recall@3, Recall@5, MRR, latency)
..\sgs\.venv\Scripts\python.exe scripts/dev_brain.py eval --min-mrr 0.70 --min-recall5 0.85

# Record a release/version snapshot
..\sgs\.venv\Scripts\python.exe scripts/dev_brain.py snapshot
```
