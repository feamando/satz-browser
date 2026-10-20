# Satz-Browser Workspace Rules & Architecture Memory (v0.3)

- **Owner:** Nikita Gorshkov (2026-10-20 · v0.3 Working Browser Plan)
- **Primary Write Repo:** `C:\Users\feama\satz-browser` (`feamando/satz-browser`)
- **Read-Only Reference Repos:** `..\sgs` (`feamando/sgs`) and `..\memail` (`feamando/memail`). Do not edit `sgs`; import from it.
- **Active Plan:** `docs/PLAN_v0.3_working_browser.md` (supersedes the Phase 0 lock).

## Rules for v0.3 Execution
- Work milestone by milestone (M1 to M7). Each milestone ends with its checks passing and one commit.
- Every milestone must pass `npm run build` and `cargo check --manifest-path src-tauri/Cargo.toml` (plus `cargo test` when touching Rust storage).
- Reuse `..\sgs\src\planck3` entry points (`serve.py`, `policies.py`, `readers.py`, `answer.py`, `web.py`, `store.py`, `digest.py`, `doctor.py`, `chat.py`).
- Local models only (`gemma-4-e4b`, `planck3 (web)`, `hertz (reader)`, `planck (reader)`). No cloud models, no Gemini, no Bedrock, no API keys.
- Terminal aesthetic: black and white (`#000`, `#0d0d0d`, `#1a1a1a`, `#333`, `#777`, `#e8e8e8`), monospace everywhere, square corners (`border-radius: 0`), no em dashes, no emoji in UI copy.
- Stay on vanilla TypeScript + Vite with modularized `src/` files.
