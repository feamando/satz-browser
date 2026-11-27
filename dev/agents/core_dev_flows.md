# Core Development Flows (`satz-browser`)

Reference from [INSTRUCTIONS.md](INSTRUCTIONS.md) · Hub: [dev/](../README.md) · Platform Parity: [PLATFORMS.md](../docs/PLATFORMS.md)

## 1. Development Loop by Subsystem

### A. Frontend & Design System (`src/`)
- **Design Tokens First:** Only reference CSS variables from `src/design-system/tokens.css` inside `src/design-system/components.css` and TypeScript renderers. Zero raw hex colors.
- **Copy & Localization:** Zero em dashes (`\u2014`) or en dashes (`\u2013`) in UI strings. Add all new user-visible text to `src/i18n/catalog.ts` (`EN_CATALOG` single-line entries) and validate via:
  ```bash
  node scripts/i18n_extract.mjs --check
  npm run build
  ```

### B. Rust Shell & Multi-Webview Engine (`src-tauri/`)
- **WebView Parity:** Windows uses `WebView2` (`webview2-com`), macOS uses `WKWebView` (`objc2-web-kit`, `block2`). Keep child webviews strictly below `.site-tab-toolbar` bounds and keep `SIDE_SHUTTING_DOWN` / `stop_sidecar_child()` clean on exit/update.
- **Bundled vs Dev Runtime:** Never break repo `.venv` / `..\sgs\.venv` priority in `resolve_python_executable_with_resources()` when working inside a git checkout; standalone installs fall back cleanly to `resource_dir()` (`sidecar/` + `python-runtime/`).
- **Checks:**
  ```bash
  cargo test --manifest-path src-tauri/Cargo.toml
  ```

### C. Python Sidecar & Models (`sidecar/`)
- **Optional `../sgs` Boundary:** All runtime paths (`satz_models.py`, `satz_brain.py`, `satz_news.py`, `satz_mail_pipeline.py`) must operate cleanly with zero `../sgs` directory via `sidecar/planck_vendor/` and `sidecar/models/planck/`.
- **PyTorch CPU Compatibility:** `CrossReader` (`sidecar/planck_vendor/src/planck3/xreader.py`) supports `onednn` / safe float32 fallback on PyTorch `2.15+` CPU wheels.
- **Model Safety:** Missing local Gemma must skip preload without recording startup errors and route generative chat via installed custom local LLMs, configured cloud models, or Settings setup prompts.
- **Checks:**
  ```bash
  ..\sgs\.venv\Scripts\python.exe -m unittest sidecar.test_local_models sidecar.test_i18n sidecar.test_m16 sidecar.test_m18 sidecar.test_satz_models sidecar.test_settings_tools sidecar.test_web_harness sidecar.test_dev_brain -v
  ```

### D. Desktop Re-Verify Workflow (Windows)
When modifying frontend or Rust code locally on Windows:
1. Stop running `satz-browser.exe`.
2. Run `npm run build` and `cargo test --manifest-path src-tauri/Cargo.toml`.
3. Rebuild `npx --no-install tauri build --no-bundle` (or `scripts/build_preview.ps1` for full NSIS installer).
4. Launch `src-tauri/target/release/satz-browser.exe` and verify the sidecar process binds cleanly.

### E. Development Management & Dev Brain Workflow (`dev/`)
- **New Features:** Create `dev/plans/<plan-slug>/v1.md` and `tasks.md` from [../plans/_template/v1.md](../plans/_template/v1.md). Revise plans via `v2.md`, `v3.md`, etc.
- **Index & Accuracy Gate:** After modifying files under `dev/`, run:
  ```bash
  python scripts/dev_brain.py reindex
  python scripts/dev_brain.py monitor
  python scripts/dev_brain.py eval --min-mrr 0.80 --min-recall5 0.90
  ```
- **Error Logging:** Record non-trivial root causes and fixes into [evals/error_log.jsonl](evals/error_log.jsonl) via [satz-eval-auditor](skills/satz-eval-auditor/SKILL.md).
