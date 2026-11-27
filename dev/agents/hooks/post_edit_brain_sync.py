#!/usr/bin/env python3
"""PostToolUse hook: keep Dev Brain synchronized after dev/ edits & log manifest parity."""

from __future__ import annotations

import sys
from typing import Any

import pre_commit_dev_sync
from hook_common import (
    REPO_ROOT,
    append_behavior_log,
    emit_noop,
    extract_candidate_paths,
    extract_tool_info,
    read_payload,
    to_repo_relative,
)

VERSION_MANIFESTS = {
    "package.json",
    "src-tauri/cargo.toml",
    "src-tauri/tauri.conf.json",
}


def handle_post_tool(payload: dict[str, Any]) -> dict[str, Any]:
    tool_name, _ = extract_tool_info(payload)
    raw_paths = extract_candidate_paths(payload)
    if not raw_paths:
        return {"action": "noop", "reason": "no_paths"}

    rel_paths = [to_repo_relative(p) for p in raw_paths]
    touches_dev = any(
        (rel == "dev" or rel.startswith("dev/"))
        and not rel.startswith("dev/brain/")
        and not rel.endswith("behavior_log.jsonl")
        for rel in rel_paths
    )
    touches_manifests = any(rel.lower() in VERSION_MANIFESTS for rel in rel_paths)

    if touches_manifests:
        try:
            ver = pre_commit_dev_sync.check_version_parity()
            append_behavior_log(
                {
                    "event": "manifest_edit_parity_ok",
                    "tool": tool_name,
                    "version": ver,
                    "paths": rel_paths,
                }
            )
        except AssertionError as exc:
            print(f"[satz-hook:post_edit_brain_sync] Version parity mismatch: {exc}", file=sys.stderr)
            append_behavior_log(
                {
                    "event": "manifest_edit_parity_mismatch",
                    "tool": tool_name,
                    "error": str(exc),
                    "paths": rel_paths,
                }
            )

    if not touches_dev:
        return {"action": "noop", "reason": "outside_dev"}

    from scripts.dev_brain import DevBrain

    brain = DevBrain(REPO_ROOT)
    stats = brain.reindex()
    append_behavior_log(
        {
            "event": "post_edit_brain_sync",
            "tool": tool_name,
            "paths": rel_paths,
            "nodes": stats.get("nodes"),
            "edges": stats.get("edges"),
        }
    )
    return {"action": "reindexed", "nodes": stats.get("nodes"), "edges": stats.get("edges")}


def main() -> int:
    payload: dict[str, Any] = read_payload()
    try:
        handle_post_tool(payload)
    except Exception:
        pass
    emit_noop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
