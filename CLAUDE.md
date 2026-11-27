# CLAUDE.md - Satz-Browser Engineering & Release Hub

Read [dev/agents/INSTRUCTIONS.md](dev/agents/INSTRUCTIONS.md), [dev/agents/core_dev_flows.md](dev/agents/core_dev_flows.md), and [dev/agents/release_management.md](dev/agents/release_management.md) for canonical agent workflows, release gates, and roles ([dev/agents/roles/roles.yaml](dev/agents/roles/roles.yaml)).

## Core Dev & Release Commands
- Search Dev Brain graph DB: `python scripts/dev_brain.py search "<query>" --neighbors`
- Sync & verify Dev Brain integrity/accuracy: `python scripts/dev_brain.py reindex && python scripts/dev_brain.py monitor && python scripts/dev_brain.py eval`
- Pre-release verification gate: `python dev/agents/hooks/release_gate.py`
- Build Windows standalone preview: `pwsh -File scripts/build_preview.ps1`
- Build macOS standalone preview: `./scripts/build_preview.sh` (unsigned downloaded `.app`: `xattr -cr /Applications/satz.app`)
