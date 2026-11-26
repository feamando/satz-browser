#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

STAGE_ARGS=("scripts/prepare_sidecar_bundle.py")
for arg in "$@"; do
  STAGE_ARGS+=("$arg")
done

echo "[satz-build] Staging sidecar & relocatable Python runtime..."
python3 "${STAGE_ARGS[@]}"

KEY_PATH="${HOME}/.tauri/satz.key"
if [[ -f "$KEY_PATH" && -z "${TAURI_SIGNING_PRIVATE_KEY:-}" ]]; then
  export TAURI_SIGNING_PRIVATE_KEY
  TAURI_SIGNING_PRIVATE_KEY="$(cat "$KEY_PATH")"
  export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="${TAURI_SIGNING_PRIVATE_KEY_PASSWORD:-}"
fi

echo "[satz-build] Running Tauri release bundle..."
npx --no-install tauri build --config src-tauri/tauri.bundle.conf.json
echo "[satz-build] Done. .app / .dmg outputs are under src-tauri/target/release/bundle/"
echo "[satz-build] For downloaded unsigned .app previews on another Mac, run: xattr -cr /Applications/satz.app"
