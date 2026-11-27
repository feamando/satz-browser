# Satz Browser Architecture (`v0.5+`)

See also: [PLATFORMS.md](PLATFORMS.md) · [RELEASE_RUNBOOK.md](RELEASE_RUNBOOK.md) · [../agents/INSTRUCTIONS.md](../agents/INSTRUCTIONS.md)

## System Topology

1. **Desktop Shell (`src-tauri/`):** Tauri v2 (`tauri 2.8.2`, Rust `satz_browser_lib`), WebView2 on Windows, WKWebView on macOS, `satz.db` SQLite for conversations/tabs/history/bookmarks, multi-webview `WebviewManagerState`, `satzmail://` custom URI scheme, and `tauri-plugin-updater` / `tauri-plugin-process`.
2. **Frontend (`src/`):** Vanilla TypeScript + Vite (`tsc && vite build`), tokenized design system (`src/design-system/tokens.css`, `components.css`), i18n catalog (`src/i18n/catalog.ts`), settings management (`src/knowledge.ts`), mail/drives/news lanes, and in-app updater bridge (`src/updater.ts`).
3. **Python Sidecar (`sidecar/`):** Local HTTP + SSE server (`satz_models.py`) spawned and supervised by `src-tauri/src/lib.rs`, authenticating via per-session `SATZ_SIDECAR_TOKEN`.
   - **Shipped Planck Runtime (`sidecar/planck_vendor/` + `sidecar/models/planck/`):** Vendored `planck3` code and sub-90 MB sharded hybrid-fp16 weights for `xreader_planck`, `planck13` Brain encoder, and `tokenizer.model`. Zero `../sgs` dependency required at runtime.
   - **Local Model Manager (`sidecar/satz_local_models.py`):** Resumable Hugging Face Hub downloads, vault-scoped optional HF tokens, and native folder/checkpoint linking in **Settings -> Models**.
   - **Satz Brain (`sidecar/satz_brain.py`):** User knowledge graph stored as YAML-frontmatter Markdown notes (`[[wikilinks]]`), `registry.yaml`, compressed pipe-delimited `BRAIN.md`, and Planck13 vector + lexical ranking.
4. **Packaged Distribution (`scripts/prepare_sidecar_bundle.py` & `src-tauri/tauri.bundle.conf.json`):** Stages clean `sidecar/` runtime scripts plus a relocatable `python-build-standalone` 3.12 CPU runtime (`python-runtime`) inside Tauri `bundle.resources`. `src-tauri/src/lib.rs` keeps repo/CUDA `.venv` priority in dev and falls back cleanly to bundled `resource_dir()` in installed builds.
5. **Development Brain (`scripts/dev_brain.py` & `dev/brain/`):** Reuses `SatzBrain` entity/registry/`BRAIN.md` mechanics backed by SQLite (`brain_index.sqlite` FTS5 + graph edges + Planck13 vectors) to index all artifacts across `dev/` and `docs/`.
