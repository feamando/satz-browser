# Satz Platforms: Windows vs macOS

Nikita Gorshkov · 2026-11-03 · Living doc · SGS / Satz · Windows 11 (RTX 4090 box) + macOS (M3 Pro, 18 GB)

**TL;DR.** The two platforms run the same code. Windows is the reference box: every model checkpoint is there, Gemma runs on CUDA, and page capture uses a WebView2-only path. On macOS the shell, storage, vault, Mail and Brain all run. The AI path is degraded in four places: (1) Gemma loads on CPU, so the first token takes about 73 s; (2) **live tab capture is not implemented outside Windows**, so chat falls back to an unauthenticated server-side fetch and can't read logged-in pages; (3) the reader and encoder checkpoints aren't on the Mac; (4) the default settings assume Windows paths, so the sidecar won't start without a hand-written `settings.json`. Windows facts below come from `docs/NOTES_v0.4.md` and were not re-measured for this doc. macOS facts were measured on 2026-11-03 at `4963e38` (see `docs/REVIEW_v0.4_macos.md`).

## 1. Matrix

| Area | Windows 11 (4090) | macOS (M3 Pro) | Code | v0.5 |
| :--- | :--- | :--- | :--- | :--- |
| Web engine | WebView2 (Chromium UA) | WKWebView, bare WebKit UA. zalando.de serves "browser not supported" | no `user_agent` set in `src-tauri` | M16 |
| Build and tests | `npm run build`, `cargo test` 9/9, `pytest` 12/12 (per NOTES_v0.4) | `npm run build` ok, `cargo test` 9/9, `pytest` 13/13 (venv with sgs deps) | n/a | n/a |
| Sidecar spawn defaults | `..\sgs\.venv\Scripts\python.exe`, `..\sgs` | Same Windows defaults. Falls back to `python`, which does not exist on macOS (only `python3`). Sidecar does not start until `settings.json` is edited | `lib.rs:47-58`, `lib.rs:446-451` | M16 |
| App data | `%APPDATA%\com.satz.browser` | `~/Library/Application Support/com.satz.browser` | `satz_models.py:65-71` | n/a |
| Session token RNG | `BCryptGenRandom` | `/dev/urandom` | `lib.rs:369-395` | n/a |
| Vault device key | Windows Credential Manager (`keyring`) | macOS Keychain (`keyring`), works | `satz_passwords.py` | M17: Touch ID unlock |
| Gemma 4 E4B device | CUDA, `device_map="auto"`, warm first token 1.73 s | CPU (MPS available but unused). First token 73 s, ~11 s per streamed chunk. In-app chat dies with `TypeError: Load failed` | `satz_models.py:634-635` | M16 |
| Gemma weights | `sgs/models/gemma-4-e4b-it` | Same path. Downloaded 2026-11-03 (15 GB, gitignored) | `satz_models.py:542-544` | n/a |
| Planck 3 web answers | Reader checkpoint present, band 9.0/10 | `missing reader checkpoint` (folders hold `train_log.json` only) | `satz_models.py:546-566` | M16 doctor |
| Hertz / Planck readers | int8 CPU readers present | `missing` | same | M16 doctor |
| Brain encoder (Planck 1.3) | `checkpoints/planck13/best.pt` + tokenizer (assumed present) | Missing. Falls back to `HashEncoder`, so Brain ranking is lexical | `satz_brain.py:135-160` | M16 doctor, M20 |
| Live tab DOM capture | WebView2 `ExecuteScript` with completion callback, SPA wait, findings | **Not implemented.** Posts an empty ingest, and the sidecar falls back to an unauthenticated Python fetch. dw.com: `0 / 0 chars`. Logged-in pages (webmail, dashboards) can't be read | `webview_manager.rs:789-843`, `satz_models.py:752` | M16 (P0) |
| Shortcuts inside pages | WebView2 `AcceleratorKeyPressed` on every child webview, incl. `Ctrl+Shift+L` | App menu accelerators only; no `Mod+Shift+L` in the menu set | `webview_manager.rs:400-461`, `lib.rs:493-513` | M16 |
| Login autofill | Exact-host fill via `webview.eval` | Same code path (cross-platform). Untested because the toolbar is hidden | `webview_manager.rs:654-778` | M17 retest |
| Site toolbar | Works (v0.3 notes: focus and compare panes good) | Covered by the page view; ~6 px visible. No address bar, back, reload, `[codes]`, `[fill login]` | `tabs.ts:166-200`, `webview_manager.rs:267` | M16 (P0) |
| `satzmail://` scheme | Works | Works (email body rendered) | `lib.rs:720-760` | n/a |
| Mail sync (IMAP) | Works (fixtures) | Works against a local IMAP server, 12/12 messages | `satz_mail.py` | n/a |
| Hidden console for sidecar | `CREATE_NO_WINDOW` | n/a | `lib.rs:483-488` | n/a |
| Default desktop fix | `ensure_default_desktop_on_windows` | n/a | `lib.rs:533` | n/a |
| Text input autocorrect | No OS autocorrect in WebView2 inputs | macOS autocorrect fires on URL, start and search inputs ("zalando" → "Calando") | only 1 `spellcheck` attr in `src/` | M17 |
| UI copy | `C:\Users\...` placeholders | Same Windows placeholders shown on Mac | `knowledge.ts` | M17 |

## 2. What "works on Windows" hides

- **Chat over your logged-in tabs is a Windows feature today.** It is the core v0.3 promise ("tabs are sources, including authenticated accounts"), and on macOS it silently degrades to a public fetch. The UI still shows a source pill and a citation number when the capture is empty.
- **Speed numbers are CUDA numbers.** M9's `1,731.5 ms` first token is real on the 4090. A laptop without CUDA sees about 40x slower.
- **Brain ranking quality depends on a checkpoint the code treats as optional.** Without `planck13/best.pt`, `make_encoder("hash")` runs and nothing tells the user.

## 3. How to run on macOS today (until M16 lands)

1. `curl https://sh.rustup.rs -sSf | sh` then `npm install` and `npx tauri build --debug --no-bundle`.
2. Create a venv with the sidecar and sgs deps: `cryptography argon2-cffi keyring requests numpy scipy scikit-learn torch transformers sentencepiece trafilatura ddgs huggingface_hub pyarrow`.
3. Write `~/Library/Application Support/com.satz.browser/settings.json` with absolute `sgs_root`, `python` (the venv's `bin/python`) and `repo_root`, plus `"preload_gemma": false` to keep the first launch responsive.
4. `hf download google/gemma-4-E4B-it --local-dir ../sgs/models/gemma-4-e4b-it` (15 GB).
5. Copy `reader.pt` for `xreader_hertz_rc` / `xreader_planck_rc` and `planck13/best.pt` + `data/wikipedia/tokenizer.model` from the Windows box if you need Planck web answers, readers and Brain ranking.

## 4. Change log

| Date | Change |
| :--- | :--- |
| 2026-11-03 | First version, from the macOS field test at `4963e38`. |
