# Satz Platforms: Windows vs macOS

Nikita Gorshkov · 2026-11-03 · Living doc · SGS / Satz · Windows 11 (RTX 4090 box) + macOS (M3 Pro, 18 GB)

**TL;DR.** The two platforms run the same code. Windows is the reference box: every model checkpoint is there, Gemma runs on CUDA, and page capture uses a WebView2-only path. On macOS the shell, storage, vault, Mail and Brain all run. The AI path is degraded in four places: (1) Gemma loads on CPU, so the first token takes about 73 s; (2) **live tab capture is not implemented outside Windows**, so chat falls back to an unauthenticated server-side fetch and can't read logged-in pages; (3) the reader and encoder checkpoints aren't on the Mac; (4) the default settings assume Windows paths, so the sidecar won't start without a hand-written `settings.json`. Windows facts below come from `docs/NOTES_v0.4.md` and were not re-measured for this doc. macOS facts were measured on 2026-11-03 at `4963e38` (see `docs/REVIEW_v0.4_macos.md`).

## 1. Matrix

| Area | Windows 11 (4090) | macOS (M3 Pro) | Code | v0.5 |
| :--- | :--- | :--- | :--- | :--- |
| Web engine | WebView2 (Edge 131 UA via `default_browser_user_agent()`) | WKWebView (Safari 18.2 UA via `default_browser_user_agent()`) | `webview_manager.rs:29-38` | M16 [done] |
| Build and tests | `npm run build`, `cargo test` 12/12, `pytest` 20/20 | `npm run build` ok, `cargo test` 12/12, `pytest` 20/20 | n/a | M16-M18 [done] |
| Sidecar spawn defaults | `..\sgs\.venv\Scripts\python.exe`, `..\sgs` | `../sgs/.venv/bin/python` (fallback `python3` -> `python`), `../sgs` | `lib.rs:46-71`, `lib.rs:449-495` | M16 [done] |
| App data | `%APPDATA%\com.satz.browser` | `~/Library/Application Support/com.satz.browser` | `satz_models.py:77-83` | n/a |
| Session token RNG | `BCryptGenRandom` | `/dev/urandom` | `lib.rs:379-405` | n/a |
| Vault device key | Windows Credential Manager (`keyring`) | macOS Keychain (`keyring`) + Touch ID unlock (`unlock_with_keychain`, `/profile/unlock_keychain`) | `satz_passwords.py:565-610` | M17 [done] |
| Gemma 4 E4B device | CUDA (`bfloat16`, `device_map="auto"`), status bar shows `gemma [warm · cuda]` | MPS (`float16`, `.to("mps")`) or CPU (`float32`), status bar shows `gemma [warm · mps]`; 5 s SSE heartbeat + 30 s stall watchdog | `satz_models.py:555-765`, `api.ts:1036-1140` | M16 [done] |
| Gemma weights | `sgs/models/gemma-4-e4b-it` | Same path. Downloaded 2026-11-03 (15 GB, gitignored) | `satz_models.py:567-569` | n/a |
| Planck 3 web answers | Reader checkpoint present, band 9.0/10; `/doctor` reports `ready` | `/doctor` reports `ready` or `missing` with one-line fix instruction | `satz_models.py:595-680` | M16 [done] |
| Hertz / Planck readers | int8 CPU readers present; `/doctor` reports `ready` | `/doctor` reports `ready` or `missing` with one-line fix instruction | `satz_models.py:595-680` | M16 [done] |
| Brain encoder (Planck 1.3) | `/doctor` & `/knowledge` report `brain ranking: semantic (planck13)` or `brain ranking: lexical (planck13 missing)` + fix path | `/doctor` & `/knowledge` report `brain ranking: semantic (planck13)` or `brain ranking: lexical (planck13 missing)` + fix path | `satz_brain.py:137-152`, `satz_models.py:595-685`, `knowledge.ts:100-112` | M16 [done], M18 [done], M20 |
| Live tab DOM capture | WebView2 `ExecuteScript` with completion callback, SPA wait, findings | WKWebView `evaluateJavaScript_completionHandler` via `objc2-web-kit` + `block2`; timeout records `capture_mode="timeout"` without unauthenticated `web.fetch` | `webview_manager.rs:892-955`, `satz_models.py:845-875` | M16 [done] |
| Shortcuts inside pages | WebView2 `AcceleratorKeyPressed` on every child webview, incl. `Ctrl+Shift+L` | App menu accelerators incl. `CmdOrCtrl+Shift+L` (`fill_login`) | `webview_manager.rs:460-520`, `lib.rs:535-560` | M16 [done] |
| Login autofill | Exact-host fill via `webview.eval` | Same code path + `Cmd+Shift+L` menu accelerator + visible toolbar `[fill login]` | `webview_manager.rs:710-835` | M16 [done] |
| Site toolbar | Clamped `child_y >= toolbar_bottom` across single-tab, 2-up, 4-up, resize | Clamped `child_y >= toolbar_bottom + titlebar_inset` (`window_titlebar_inset`), never overlaps `.site-tab-toolbar` | `tabs.ts:166-215`, `webview_manager.rs:44-84` | M16 [done] |
| `satzmail://` scheme | Works | Works (email body rendered) | `lib.rs:720-760` | n/a |
| Mail sync (IMAP) | Works (fixtures) | Works against a local IMAP server, 12/12 messages | `satz_mail.py` | n/a |
| Hidden console for sidecar | `CREATE_NO_WINDOW` | n/a | `lib.rs:483-488` | n/a |
| Default desktop fix | `ensure_default_desktop_on_windows` | n/a | `lib.rs:533` | n/a |
| Text input autocorrect | `spellcheck="false" autocorrect="off" autocapitalize="off"` on all URL, start, rail filter, chat, mail search, and PIN inputs | `spellcheck="false" autocorrect="off" autocapitalize="off"` on all URL, start, rail filter, chat, mail search, and PIN inputs | `start.ts`, `rail.ts`, `chat.ts`, `mail.ts`, `knowledge.ts`, `main.ts` | M17 [done] |
| UI copy | OS-aware path placeholders (`C:\Users\...\.env` on Windows) | OS-aware path placeholders (`~/Downloads/.env` on macOS) | `knowledge.ts:220` | M17 [done] |

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
| 2026-11-09 | M16: WKWebView `evaluateJavaScript_completionHandler` live DOM capture, `compute_child_webview_bounds` + `window_titlebar_inset` toolbar fix, realistic browser UA on WebView2/WKWebView, MPS/CUDA/CPU Gemma device selection + 5 s SSE heartbeat + 30 s watchdog, per-OS sidecar defaults, `/doctor` endpoint, and `Cmd+Shift+L` macOS accelerator. |
| 2026-11-09 | M17: Honest source pills (`dom`/`fetch`/`empty [recapture]`), 0-char source exclusion from citations, canonical URL source deduplication, plain-language errors + `[debug]` drawer, ordered `Esc`/click-away dismissal, inline Mail unlock + macOS Touch ID (`unlock_with_keychain`), `about:blank` new tabs, unseeded bookmarks, and `spellcheck="false" autocorrect="off" autocapitalize="off"` across inputs. |
| 2026-11-09 | M18: Profile-scoped `profiles/<id>/planck_store.sqlite` + `.v04.bak` migration (`:memory:` when locked), no-profile Brain write guard, mail pipeline `profile_id` binding, clean bookmark entities, digest URL/domain deduplication, cascading `delete_passage` and `mail:<id>` `/forget`, hidden `$` attributes in `BRAIN.md`, webmail `(provider, email)` upsert, and encoder mode visibility (`brain ranking: semantic (planck13)` vs `lexical (planck13 missing)`). |
