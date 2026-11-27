# Development Plans (`dev/plans/`)

Every feature initiative or milestone lives in its own subfolder under `dev/plans/<plan-slug>/` containing:
- **Versioned plans:** `v1.md`, `v2.md`, ... (preserving prior specs when scope evolves)
- **Task tracker:** `tasks.md` (milestones, verification criteria, status checkboxes, and links to release notes in `../../versions/`)

Use [_template/](_template/) when creating a new plan subfolder, then run `scripts/dev_brain.py reindex` so the plan and its tasks become searchable in `dev/brain/`.
