# Satz-Browser Workspace Rules & Architecture Memory

- **Owner:** Nikita Gorshkov
- **Primary Write Repo:** `feamando/satz-browser` (Windows & macOS)
- **Canonical Agent & Release Instructions:** [dev/agents/INSTRUCTIONS.md](../dev/agents/INSTRUCTIONS.md) (mirrored via [AGENTS.md](../AGENTS.md) and `.agents/skills.json`)
- **Development Management Hub:** [dev/](../dev/) (`docs/`, `versions/`, `analytics/`, `agents/`, `plans/`, `brain/`)

## Core Invariants
- Every new plan creates a subfolder under `dev/plans/<plan-slug>/` containing `v1.md` (`v2.md`, ...) and `tasks.md`.
- Keep `sidecar/planck_vendor/` and `sidecar/models/planck/` (`<90 MB` shards, no Git LFS) working with zero runtime dependency on `../sgs`.
- Use CSS tokens from `src/design-system/tokens.css`, keep UI text free of em/en dashes, and validate `node scripts/i18n_extract.mjs --check`.
- Commit Dev Brain Markdown entities + `dev/brain/brain_index.sqlite` cleanly using `python scripts/dev_brain.py reindex` (SQLite `journal_mode=DELETE`).
- Verify `npm run build`, `cargo test --manifest-path src-tauri/Cargo.toml`, sidecar `unittest` suites, and `scripts/dev_brain.py eval` before finishing.
