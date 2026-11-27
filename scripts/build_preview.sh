#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

NO_UPDATER=0
STAGE_ARGS=("scripts/prepare_sidecar_bundle.py")
for arg in "$@"; do
  if [[ "$arg" == "--no-updater" ]]; then
    NO_UPDATER=1
  else
    STAGE_ARGS+=("$arg")
  fi
done

echo "[satz-build] Staging sidecar & relocatable Python runtime..."
python3 "${STAGE_ARGS[@]}"

KEY_PATH="${HOME}/.tauri/satz.key"
if [[ -f "$KEY_PATH" && -z "${TAURI_SIGNING_PRIVATE_KEY:-}" ]]; then
  export TAURI_SIGNING_PRIVATE_KEY
  TAURI_SIGNING_PRIVATE_KEY="$(cat "$KEY_PATH")"
  export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="${TAURI_SIGNING_PRIVATE_KEY_PASSWORD:-}"
fi

TAURI_ARGS=(--config src-tauri/tauri.bundle.conf.json)
if [[ "$NO_UPDATER" -eq 1 || -z "${TAURI_SIGNING_PRIVATE_KEY:-}" ]]; then
  if [[ "$NO_UPDATER" -eq 0 ]]; then
    echo "[satz-build] No ~/.tauri/satz.key or TAURI_SIGNING_PRIVATE_KEY found; disabling updater artifact signing (--no-updater)."
  fi
  TAURI_ARGS+=(--config src-tauri/tauri.bundle.noupdater.conf.json)
fi

echo "[satz-build] Running Tauri release bundle..."
npx --no-install tauri build "${TAURI_ARGS[@]}"
echo "[satz-build] Done. .app / .dmg outputs are under src-tauri/target/release/bundle/"
echo "[satz-build] For downloaded unsigned .app previews on another Mac, run: xattr -cr /Applications/satz.app"
