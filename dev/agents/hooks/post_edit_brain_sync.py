#!/usr/bin/env python3
"""PostToolUse hook: keep Dev Brain synchronized after dev/ edits & capture tool/error telemetry."""

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
    get_conversation_id,
    is_claude_payload,
    read_payload,
    to_repo_relative,
)

VERSION_MANIFESTS = {
    "package.json",
    "src-tauri/cargo.toml",
    "src-tauri/tauri.conf.json",
}
WRITE_TOOL_NAMES = {
    "write_file",
    "edit_file",
    "multi_replace_file_content",
    "replace_file_content",
    "write_to_file",
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
}


def handle_post_tool(payload: dict[str, Any]) -> dict[str, Any]:
    tool_name, args = extract_tool_info(payload)
    raw_paths = extract_candidate_paths(payload)
    rel_paths = [to_repo_relative(p) for p in raw_paths]
    err_text = str(payload.get("error") or payload.get("tool_error") or "").strip()

    # Fast local telemetry + error capture across all matched tool calls.
    try:
        import behavior_eval_store

        cmd = str(args.get("CommandLine") or args.get("command") or "").strip()
        cmd_label = f"{tool_name} ({cmd[:60]})" if cmd else (tool_name or "tool")
        behavior_eval_store.record_event(
            harness="claude" if is_claude_payload(payload) else "antigravity",
            conv_id=get_conversation_id(payload),
            event_type="tool_error" if err_text else "tool_use",
            tool_name=tool_name,
            rel_paths=rel_paths,
            ok=not bool(err_text),
            error_text=err_text,
            prompt_text=str(payload.get("lastUserInput") or "")[:300],
            transcript_path=str(payload.get("transcriptPath") or payload.get("transcript_path") or ""),
        )
        if err_text and "denied by pre-tool hook" not in err_text.lower():
            behavior_eval_store.record_error_incident(
                scope=f"tool:{tool_name}" if tool_name else "tool:unknown",
                summary=f"{cmd_label} failed: {err_text[:200]}",
                root_cause="Captured automatically by PostToolUse error telemetry.",
                fix_ref=rel_paths[0] if rel_paths else "",
                severity="medium",
            )
    except Exception:
        pass

    if not raw_paths or (tool_name and tool_name not in WRITE_TOOL_NAMES):
        return {"action": "noop", "reason": "non_write_or_no_paths"}

    touches_dev = any(
        (rel == "dev" or rel.startswith("dev/"))
        and not rel.startswith("dev/brain/")
        and not rel.startswith("dev/agents/behavior/")
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

    from dev_brain import DevBrain

    append_behavior_log(
        {
            "event": "post_edit_brain_sync",
            "tool": tool_name,
            "paths": rel_paths,
        }
    )
    brain = DevBrain(REPO_ROOT)
    stats = brain.reindex()
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
