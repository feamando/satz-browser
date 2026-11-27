# Version History & Release Snapshots (`dev/versions/`)

Stores milestone implementation notes (`NOTES_v0.3.md`..`NOTES_v0.9.md`), [CHANGELOG.md](CHANGELOG.md), [BINARY_RELEASES.md](BINARY_RELEASES.md), and machine-readable release snapshots under [snapshots/](snapshots/).

## Version Bump & Snapshot Protocol
Run before tagging or cutting any preview release (`fix` | `minor` | `major` via `scripts/release_version.py`):
```powershell
..\sgs\.venv\Scripts\python.exe scripts/release_version.py status --verify-hashes
..\sgs\.venv\Scripts\python.exe scripts/release_version.py bump fix --notes "Short summary"
..\sgs\.venv\Scripts\python.exe scripts/dev_brain.py snapshot
```
Each snapshot (`dev/versions/snapshots/v<ver>_<shortsha>.json`) and [BINARY_RELEASES.md](BINARY_RELEASES.md) record:
- Package/Crate/Tauri version alignment
- Git commit SHA, branch, recent commits
- Shipped Planck chunk filenames & sizes (`sidecar/models/planck/`)
- Existing release executables, NSIS/MSI/DMG installers, sizes, SHA256 hashes, and `.sig` signatures (`src-tauri/target/release/`)
- Runtime dependency manifest SHA256 (`sidecar/requirements-runtime.txt`)
- Automated Dev Brain monitor/eval summary at capture time
