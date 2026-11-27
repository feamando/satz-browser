#!/usr/bin/env python3
"""Stop hook: auto-sync stale Dev Brain files and block stop on broken links or UI/version regressions."""

from __future__ import annotations

import subprocess
from typing import Any

import pre_commit_dev_sync
from hook_common import (
    REPO_ROOT,
    append_behavior_log,
    emit_noop,
    emit_stop_block,
    is_claude_payload,
    read_payload,
)


def _git_dirty_paths(pathspecs: list[str]) -> list[str]:
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain", "--", *pathspecs],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode != 0:
            return []
        return [line[3:].strip() for line in res.stdout.splitlines() if line.strip()]
    except Exception:
        return []


def evaluate_stop(payload: dict[str, Any]) -> str | None:
    # Infinite-loop prevention: never block again once continuation is active.
    if bool(payload.get("continuationActive") or payload.get("stop_hook_active")):
        return None

    # In Antigravity, only inspect natural completions (NO_TOOL_CALL), not cancels/errors.
    if not is_claude_payload(payload):
        term_reason = payload.get("terminationReason")
        if term_reason is not None and term_reason != "NO_TOOL_CALL":
            return None

    issues: list[str] = []

    try:
        from scripts.dev_brain import DevBrain

        brain = DevBrain(REPO_ROOT)
        health = brain.monitor()
        if int(health.get("stale_count") or 0) > 0:
            brain.reindex()
            health = brain.monitor()

        broken_count = int(health.get("broken_edge_count") or 0)
        if broken_count > 0:
            broken_links = health.get("broken_links") or []
            preview = ", ".join(
                f"{b.get('source')} -> {b.get('target')}" for b in broken_links[:4]
            )
            issues.append(
                f"Dev Brain detected {broken_count} broken graph link(s) in dev/ ({preview}). Fix broken references before finishing."
            )
    except Exception:
        # Fail-open if DB / Python deps aren't built in this environment.
        pass

    # If src/ files changed in git, ensure i18n catalog check passes.
    if _git_dirty_paths(["src"]):
        try:
            i18n_res = subprocess.run(
                ["node", "scripts/i18n_extract.mjs", "--check"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if i18n_res.returncode != 0:
                detail = (i18n_res.stdout or i18n_res.stderr or "").strip().splitlines()
                msg = detail[-1] if detail else "i18n catalog out of sync"
                issues.append(f"i18n check failed (`node scripts/i18n_extract.mjs --check`): {msg}")
        except Exception:
            pass

    # If any release version manifest changed in git, enforce 3-manifest version parity.
    if _git_dirty_paths(["package.json", "src-tauri/Cargo.toml", "src-tauri/tauri.conf.json"]):
        try:
            pre_commit_dev_sync.check_version_parity()
        except AssertionError as exc:
            issues.append(
                f"Release manifest version mismatch ({exc}). Sync package.json, src-tauri/Cargo.toml, and src-tauri/tauri.conf.json."
            )

    if issues:
        return " | ".join(issues)
    return None


def main() -> None:
    payload: dict[str, Any] = read_payload()
    try:
        block_reason = evaluate_stop(payload)
        if block_reason:
            append_behavior_log({"event": "stop_gate_block", "reason": block_reason})
            emit_stop_block(block_reason, payload=payload)
            return
    except Exception:
        pass
    emit_noop()


if __name__ == "__main__":
    main()
