#!/usr/bin/env python3
"""Pre-commit / dev-sync validator:
1. Verifies version parity across package.json, src-tauri/Cargo.toml, tauri.conf.json.
2. Ensures no em/en dashes in src/i18n/catalog.ts UI text and all model chunks < 90 MB.
3. Re-indexes dev/brain/ cleanly with SQLite journal_mode=DELETE (no leftover WAL/SHM).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import security_audit  # noqa: E402


def check_version_parity() -> str:
    pkg = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))["version"].strip()
    tauri_cfg = json.loads((REPO_ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))["version"].strip()
    cargo_raw = (REPO_ROOT / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', cargo_raw)
    cargo_ver = m.group(1).strip() if m else ""
    if not (pkg == tauri_cfg == cargo_ver):
        raise AssertionError(
            f"Version mismatch: package.json={pkg!r}, Cargo.toml={cargo_ver!r}, tauri.conf.json={tauri_cfg!r}"
        )
    return pkg


def check_ui_and_weight_limits() -> None:
    cat_path = REPO_ROOT / "src" / "i18n" / "catalog.ts"
    cat_txt = cat_path.read_text(encoding="utf-8")
    if "\u2014" in cat_txt or "\u2013" in cat_txt:
        raise AssertionError("Found disallowed em/en dash inside src/i18n/catalog.ts")

    planck_dir = REPO_ROOT / "sidecar" / "models" / "planck"
    limit = 90 * 1024 * 1024
    if planck_dir.is_dir():
        for f in planck_dir.rglob("*"):
            if f.is_file() and f.stat().st_size > limit:
                raise AssertionError(f"Model file exceeds 90 MB GitHub limit: {f}")

    if (REPO_ROOT / ".git").exists():
        sh_proc = subprocess.run(
            ["git", "ls-files", "--stage", "--", "scripts/*.sh"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if sh_proc.returncode == 0:
            for line in sh_proc.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 4 and parts[0] != "100755":
                    raise AssertionError(
                        f"Shell script {parts[-1]} lacks executable git mode 100755 (got {parts[0]}). Run: git update-index --chmod=+x {parts[-1]}"
                    )


def check_privacy_and_secrets(*, mode: str = "all") -> None:
    res = security_audit.run_audit(mode=mode, repo_root=REPO_ROOT)
    if not res["ok"]:
        preview = "; ".join(
            f"{f['category']}@{f['path']}:{f['line']}" for f in res["findings"][:5]
        )
        raise AssertionError(
            f"Privacy/security audit failed ({res['finding_count']} finding(s)): {preview}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Satz pre-commit/pre-push validator")
    parser.add_argument("--check-only", action="store_true", help="Validate without modifying brain_index.sqlite")
    args, _ = parser.parse_known_args()

    ver = check_version_parity()
    check_ui_and_weight_limits()
    check_privacy_and_secrets(mode="all")

    from dev_brain import DevBrain

    brain = DevBrain(REPO_ROOT)
    if args.check_only:
        mon = brain.monitor()
        stats = {"nodes": mon.get("nodes", 0), "edges": mon.get("edges", 0)}
    else:
        stats = brain.reindex()
        mon = brain.monitor()
    print(
        f"[pre_commit_dev_sync] version={ver} nodes={stats['nodes']} edges={stats['edges']} "
        f"stale={mon['stale_count']} broken_edges={mon['broken_edge_count']}"
    )
    if mon["broken_edge_count"] > 0:
        print(f"[pre_commit_dev_sync] warning: {mon['broken_edge_count']} broken dev/ links", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
