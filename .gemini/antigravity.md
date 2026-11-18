
# Satz-Browser Workspace Rules & Architecture Memory (v0.5)

- **Owner:** Nikita Gorshkov (2026-11-03 · v0.5 Parity, Trust, Agents Plan)
- **Primary Write Repo:** `satz-browser` (`feamando/satz-browser`). Windows: `C:\Users\feama\satz-browser`. macOS: `~/Documents/GitHub/satz-browser`.
- **Read-Only Reference Repo:** `../sgs` (`feamando/sgs`). Do not edit `sgs`; import from it.
- **Active Design Plan:** `docs/PLAN_v0.7_design_system.md` (milestones D1 to D9, one commit each). Spec `docs/design/DESIGN_SYSTEM.md`, gallery `docs/design/components.html`.
- **Previous Plan:** `docs/PLAN_v0.5.md` (follows `docs/PLAN_v0.4.md`, M8 to M15 done). Inputs: `docs/REVIEW_v0.4_macos.md`, `docs/PLATFORMS.md`.

## Rules for v0.5 Execution
- Work milestone by milestone (M16 to M23). M16 (parity) lands first. Each milestone ends with its checks passing on **both** Windows and macOS and one commit.
- Every milestone also passes the manual smoke script (`PLAN_v0.5.md` Section 9) on each platform, with screenshots in `docs/smoke/v0.5/<milestone>/<os>/`. Tests passing alone is not done.
- Record measurements and deviations in `docs/NOTES_v0.5.md`; update `docs/PLATFORMS.md` when a platform row changes.
- Every milestone must pass `npm run build`, `cargo check` and `cargo test --manifest-path src-tauri/Cargo.toml`, and the sidecar tests.
- Reuse `../sgs/src/planck3` entry points (`serve.py`, `policies.py`, `readers.py`, `answer.py`, `web.py`, `store.py`, `digest.py`, `doctor.py`, `chat.py`).
- Local models only (`gemma-4-e4b`, `planck3 (web)`, `hertz (reader)`, `planck (reader)`, local DistilBERT mail classifier). No cloud models, no Gemini, no Bedrock, no API keys.
- Python deps only from `sidecar/requirements.txt`. New Rust crates only for M16 macOS capture (`objc2`, `objc2-foundation`, `objc2-web-kit`, `block2`).
- Never send email or commit any action without a user `[confirm]` click. Never move or delete mail on the server. Pages get no IPC.
- UI follows `docs/design/DESIGN_SYSTEM.md` (v1, 2026-11-18). Read its section 1 before any UI change. Tokens only (`src/design-system/tokens.css`), Inter for UI, Besley for display, JetBrains Mono for data only, radius by role, light (paper) and dark both checked, logo via `src/design-system/brand.ts`, icons via `src/design-system/icons.ts`. No em dashes, no emoji in UI copy. This replaces the v0.5 terminal aesthetic (black and white, monospace, square corners).
- Stay on vanilla TypeScript + Vite with modularized `src/` files.
