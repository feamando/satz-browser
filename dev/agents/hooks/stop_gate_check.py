#!/usr/bin/env python3
"""Stop hook: capture stop/error telemetry, spawn background analyzer, auto-sync Dev Brain, and check integrity."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pre_commit_dev_sync
from hook_common import (
    REPO_ROOT,
    append_behavior_log,
    emit_noop,
    emit_stop_block,
    get_conversation_id,
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


def _capture_turn_telemetry(payload: dict[str, Any]) -> None:
    try:
        import behavior_eval_store
    except Exception:
        return

    term_reason = str(payload.get("terminationReason") or "")
    stop_error = str(payload.get("error") or "").strip()
    transcript_path = str(payload.get("transcriptPath") or payload.get("transcript_path") or "").strip()
    transcript_err = ""

    if transcript_path:
        try:
            tp = Path(transcript_path)
            if tp.is_file():
                lines = tp.read_text(encoding="utf-8", errors="ignore").splitlines()[-25:]
                for raw in reversed(lines):
                    if not raw.strip():
                        continue
                    step = json.loads(raw)
                    if str(step.get("status") or "").upper() == "ERROR":
                        transcript_err = str(step.get("content") or step.get("type") or "step ERROR")[:300]
                        break
        except Exception:
            pass

    combined_err = stop_error or transcript_err or (term_reason if term_reason in ("ERROR", "MAX_INVOCATIONS", "MAX_FORCED_INVOCATIONS") else "")
    has_err = bool(combined_err)
    try:
        behavior_eval_store.record_event(
            harness="claude" if is_claude_payload(payload) else "antigravity",
            conv_id=get_conversation_id(payload),
            event_type="stop_error" if has_err else "stop",
            prompt_text=str(payload.get("lastUserInput") or "")[:400],
            ok=not has_err,
            error_text=combined_err,
            termination_reason=term_reason,
            transcript_path=transcript_path,
        )
        if combined_err and term_reason != "USER_CANCELED":
            behavior_eval_store.record_error_incident(
                scope=f"agent:{term_reason or 'stop'}",
                summary=f"Agent turn ended with error ({term_reason or 'ERROR'}): {combined_err[:220]}",
                root_cause="Captured automatically by Stop telemetry hook.",
                fix_ref="dev/agents/evals/error_log.jsonl",
                severity="high" if term_reason == "ERROR" else "medium",
            )
        if behavior_eval_store.should_spawn_worker(has_errors=has_err):
            behavior_eval_store.spawn_background_worker()
    except Exception:
        pass


def evaluate_stop(payload: dict[str, Any]) -> str | None:
    _capture_turn_telemetry(payload)

    # Infinite-loop prevention: never block again once continuation is active.
    if bool(payload.get("continuationActive") or payload.get("stop_hook_active")):
        return None

    # In Antigravity, only block natural completions (NO_TOOL_CALL), not cancels/errors.
    if not is_claude_payload(payload):
        term_reason = payload.get("terminationReason")
        if term_reason is not None and term_reason != "NO_TOOL_CALL":
            return None

    issues: list[str] = []

    try:
        from dev_brain import DevBrain

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
        pass

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
