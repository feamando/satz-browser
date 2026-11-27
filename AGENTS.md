# Satz-Browser Agent Guidelines

Read [dev/agents/INSTRUCTIONS.md](dev/agents/INSTRUCTIONS.md), [dev/agents/core_dev_flows.md](dev/agents/core_dev_flows.md), and [dev/agents/release_management.md](dev/agents/release_management.md) before modifying builds, releases, UI, or `dev/` artifacts.

- **Dev Management Hub:** `dev/` (`docs/`, `versions/`, `analytics/`, `agents/`, `plans/`, `brain/`)
- **Dev Brain Search / Monitor / Eval:** `python scripts/dev_brain.py search "<query>" --neighbors` | `monitor` | `eval`
- **Release Gate:** `python dev/agents/hooks/release_gate.py`
- **Design System & Localization:** Use `src/design-system/tokens.css` variables only (zero raw hex), zero em/en dashes in UI copy, update `src/i18n/catalog.ts` (`node scripts/i18n_extract.mjs --check`).
- **Windows / macOS Parity:** Keep `../sgs` optional at runtime; shipped Planck (`sidecar/models/planck/`) stays `<90 MB` per shard; `scripts/prepare_sidecar_bundle.py` stages relocatable Python 3.12 CPU bundles.
