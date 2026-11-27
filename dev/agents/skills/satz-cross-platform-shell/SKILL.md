---
name: satz-cross-platform-shell
description: >-
  Use this skill when modifying src-tauri/ Rust code, WebView2 (Windows) or WKWebView
  (macOS) bounds/capture, OS keychain/Credential Manager bridges, or sidecar process management.
---

# Satz Cross-Platform Tauri Shell Skill

Platform Matrix: [PLATFORMS.md](../../../docs/PLATFORMS.md) · Rust Entry: [lib.rs](../../../../src-tauri/src/lib.rs) · Webviews: [webview_manager.rs](../../../../src-tauri/src/webview_manager.rs)

## Platform Invariants
1. **Multi-Webview Bounds:** Always clamp child webviews below `.site-tab-toolbar` height (`+ window_titlebar_inset` on macOS) across single-tab, 2-up, and 4-up Compare modes.
2. **Sidecar Shutdown & Auto-Update Safety:** Preserve `SIDE_SHUTTING_DOWN` and `stop_sidecar_child()` (`prepare_for_update` IPC) so NSIS installers never fail on Windows `.exe` locks during self-update.
3. **Python Runtime Discovery Parity:** Keep local repo `.venv` / `..\sgs\.venv` priority ahead of bundled `resource_dir()/python-runtime` in `resolve_python_executable_with_resources()` so CUDA stays active in dev while standalone installers run zero-config.
4. **Windows & macOS Parity:** Maintain matching behavior across WebView2 (`ExecuteScript`, `BCryptGenRandom`, `CREATE_NO_WINDOW`) and WKWebView (`evaluateJavaScript_completionHandler`, `/dev/urandom`, `Cmd+Shift+L`).

## Verification
```powershell
cargo test --manifest-path src-tauri/Cargo.toml
```
