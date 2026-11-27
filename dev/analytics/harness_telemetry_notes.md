# Harness Telemetry & Developer Observations

Tracks recurring signals across desktop runtime usage and build telemetry to guide agent instructions, model fallbacks, and harness design:

1. **Silent fallback visibility:** Always log per-slug fallback reasons and avoid deprecated `gemini-2.5-*` fallback defaults (`gemini-3.8-flash` / `cloud_models_<pid>` preferred).
2. **Missing local weights on non-GPU hosts (macOS):** Never fail startup preload when `gemma-4-e4b` is absent; automatically lean on shipped `planck (reader)` / `planck13` and route generative chat via downloaded local LLMs or configured Cloud APIs.
3. **PyTorch CPU quantization engine drift:** Newer PyTorch CPU wheels (`2.15+`) expose `['onednn']` rather than `['fbgemm', 'x86']`; `CrossReader` must accept `'onednn'` or fall back safely.
4. **Windows packaging footprint vs build time:** WiX `.msi` adds ~4 min over NSIS LZMA when packaging ~1.18 GB uncompressed `python-runtime` + `sidecar`; NSIS `.exe` compresses to `402.07 MB`.
5. **macOS Apple Silicon preview build & `settings.json` override trap (`2026-11-27`):** `scripts/build_preview.sh` built `satz_0.5.0_aarch64.dmg` (`521 MB`), and Gemma now loads cleanly on Apple GPU (`mps`) rather than 73s CPU. However, stale `"python"` and `"repo_root"` keys in `~/Library/Application Support/com.satz.browser/settings.json` silently override bundled `python-runtime` + `sidecar/` (exposing a missing `httpx` inside old `../sgs/.venv`), and secondary build hosts lacking `~/.tauri/satz.key` fail at updater `.sig` signing after generating `.app` and `.dmg`. Also keep two local macOS compile fixes in `src-tauri/src/webview_manager.rs` synced before cutting CI tags.
