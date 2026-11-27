#!/usr/bin/env python3
"""Release Gate validator run prior to tagging or bundling standalone Satz releases."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOKS_DIR = Path(__file__).resolve().parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pre_commit_dev_sync import check_privacy_and_secrets, check_ui_and_weight_limits, check_version_parity


def _run(cmd: list[str], label: str) -> None:
    print(f"[release-gate] {label}: {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), shell=(sys.platform == "win32" and cmd[0] in ("npm", "node", "npx")))
    if proc.returncode != 0:
        raise RuntimeError(f"Release gate step failed ({proc.returncode}): {label}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Satz Release Gate validator")
    parser.add_argument("--quick", action="store_true", help="Skip Rust cargo test & full sidecar suite")
    args = parser.parse_args()

    ver = check_version_parity()
    check_ui_and_weight_limits()
    check_privacy_and_secrets(mode="all")
    print(f"[release-gate] Version & privacy security audit verified: {ver}", flush=True)

    _run(["npm", "run", "build"], "Frontend tsc + Vite build")
    _run(["node", "scripts/i18n_extract.mjs", "--check"], "i18n catalog & AST check")

    if not args.quick:
        _run(["cargo", "test", "--manifest-path", "src-tauri/Cargo.toml"], "Rust cargo test")
        _run(
            [
                sys.executable,
                "-m",
                "unittest",
                "sidecar.test_local_models",
                "sidecar.test_i18n",
                "sidecar.test_m16",
                "sidecar.test_m18",
                "sidecar.test_satz_models",
                "sidecar.test_settings_tools",
                "sidecar.test_web_harness",
            ],
            "Sidecar unittest regression suite",
        )

    from dev_brain import DevBrain

    brain = DevBrain(REPO_ROOT)
    brain.reindex()
    mon = brain.monitor()
    if not mon["ok"]:
        raise RuntimeError(f"Dev Brain monitor failed: {mon}")
    ev = brain.evaluate(min_mrr=0.70, min_recall5=0.85)
    print(
        f"[release-gate] Dev Brain eval: hit@1={ev['hit_at_1']:.3f} recall@5={ev['recall_at_5']:.3f} mrr={ev['mrr']:.3f}",
        flush=True,
    )
    if not ev["passed"]:
        raise RuntimeError(f"Dev Brain eval below release gate threshold: {ev}")

    print("[release-gate] ALL GATES PASSED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
