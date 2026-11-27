# Harness Telemetry & Developer Observations

Tracks recurring signals across desktop runtime usage and build telemetry to guide agent instructions, model fallbacks, and harness design:

1. **Silent fallback visibility:** Always log per-slug fallback reasons and avoid deprecated `gemini-2.5-*` fallback defaults (`gemini-3.8-flash` / `cloud_models_<pid>` preferred).
2. **Missing local weights on non-GPU hosts (macOS):** Never fail startup preload when `gemma-4-e4b` is absent; automatically lean on shipped `planck (reader)` / `planck13` and route generative chat via downloaded local LLMs or configured Cloud APIs.
3. **PyTorch CPU quantization engine drift:** Newer PyTorch CPU wheels (`2.15+`) expose `['onednn']` rather than `['fbgemm', 'x86']`; `CrossReader` must accept `'onednn'` or fall back safely.
4. **Windows packaging footprint vs build time:** WiX `.msi` adds ~4 min over NSIS LZMA when packaging ~1.18 GB uncompressed `python-runtime` + `sidecar`; NSIS `.exe` compresses to `402.07 MB`.
