# Satz-Browser Workspace Rules & Architecture Memory (v0.4)

- **Owner:** Nikita Gorshkov (2026-10-27 · v0.4 Secure, Faster, Mail Plan)
- **Primary Write Repo:** `C:\Users\feama\satz-browser` (`feamando/satz-browser`)
- **Read-Only Reference Repo:** `..\sgs` (`feamando/sgs`). Do not edit `sgs`; import from it. memail is not on this box; its specs are in Appendix A of the v0.4 plan.
- **Active Plan:** `docs/PLAN_v0.4.md` (follows `docs/PLAN_v0.3_working_browser.md`, M1 to M7 done).

## Rules for v0.4 Execution
- Work milestone by milestone (M8 to M15). M8 (security) lands first. Each milestone ends with its checks passing and one commit.
- Record measurements and deviations in `docs/NOTES_v0.4.md`.
- Every milestone must pass `npm run build` and `cargo check --manifest-path src-tauri/Cargo.toml` (plus `cargo test` when touching Rust storage) and the sidecar tests.
- Reuse `..\sgs\src\planck3` entry points (`serve.py`, `policies.py`, `readers.py`, `answer.py`, `web.py`, `store.py`, `digest.py`, `doctor.py`, `chat.py`).
- Local models only (`gemma-4-e4b`, `planck3 (web)`, `hertz (reader)`, `planck (reader)`, local DistilBERT mail classifier). No cloud models, no Gemini, no Bedrock, no API keys.
- New Python deps only from: `cryptography`, `argon2-cffi`, `keyring` (in `sidecar/requirements.txt`). Mail uses the stdlib.
- Never send email without a user `[confirm]` click. Never move or delete mail on the server.
- Terminal aesthetic: black and white (`#000`, `#0d0d0d`, `#1a1a1a`, `#333`, `#777`, `#e8e8e8`), monospace everywhere, square corners (`border-radius: 0`), no em dashes, no emoji in UI copy.
- Stay on vanilla TypeScript + Vite with modularized `src/` files.
