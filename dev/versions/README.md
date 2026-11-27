# Version History & Release Snapshots (`dev/versions/`)

Stores milestone implementation notes (`NOTES_v0.3.md`..`NOTES_v0.9.md`), [CHANGELOG.md](CHANGELOG.md), and machine-readable release snapshots under [snapshots/](snapshots/).

## Snapshot Protocol
Run before tagging or cutting any preview release:
```powershell
..\sgs\.venv\Scripts\python.exe scripts/dev_brain.py snapshot
```
Each snapshot (`dev/versions/snapshots/v<ver>_<shortsha>.json`) records:
- Package/Crate/Tauri version alignment
- Git commit SHA, branch, recent commits
- Shipped Planck chunk filenames & sizes (`sidecar/models/planck/`)
- Runtime dependency manifest SHA256 (`sidecar/requirements-runtime.txt`)
- Automated Dev Brain monitor/eval summary at capture time
