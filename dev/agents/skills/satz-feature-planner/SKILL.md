---
name: satz-feature-planner
description: >-
  Use this skill when planning a new initiative, updating dev/plans/ versions, documenting
  milestone notes, or running the full Windows build-and-launch verification loop.
---

# Satz Feature Lifecycle & Verification Skill

Dev Hub: [dev/README.md](../../../README.md) · Plans: [dev/plans/](../../../plans/README.md) · Flows: [core_dev_flows.md](../../core_dev_flows.md)

## Workflow
1. **Research First:** Query `python scripts/dev_brain.py search "<topic>" --neighbors` before designing changes.
2. **Plan Inside `dev/plans/<plan-slug>/`:** Copy `dev/plans/_template/` (`v1.md` + `tasks.md`). For revisions, add `v2.md`, `v3.md`, etc. Never orphan plans outside `dev/plans/`.
3. **Local Windows App Re-Verify (after frontend/Rust/sidecar changes):**
   - Stop any running `satz-browser.exe` instance.
   - Run `npm run build` and `cargo test --manifest-path src-tauri/Cargo.toml`.
   - Build `npx --no-install tauri build --no-bundle` and verify startup + sidecar health.
4. **Closeout:** Record notes in `dev/versions/` (and `dev/analytics/build_telemetry.jsonl` for builds), log root-cause fixes in `dev/agents/evals/error_log.jsonl`, and sync `python scripts/dev_brain.py reindex && monitor`.
