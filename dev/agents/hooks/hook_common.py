#!/usr/bin/env python3
"""Shared helpers for Satz-Browser lifecycle hooks (Antigravity & Claude Code)."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HOOK_DIR = Path(__file__).resolve().parent
REPO_ROOT = HOOK_DIR.parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
for _sys_dir in (str(SCRIPTS_DIR), str(HOOK_DIR)):
    if _sys_dir not in sys.path:
        sys.path.insert(0, _sys_dir)

BEHAVIOR_LOG = REPO_ROOT / "dev" / "agents" / "behavior" / "behavior_log.jsonl"
ERROR_LOG = REPO_ROOT / "dev" / "agents" / "evals" / "error_log.jsonl"
BRAIN_DB_PATH = REPO_ROOT / "dev" / "brain" / "brain_index.sqlite"

PATH_ARG_KEYS = (
    "Path",
    "TargetFile",
    "path",
    "file_path",
    "target_file",
    "ScriptPath",
    "Cwd",
    "notebook_path",
)


def read_payload() -> dict[str, Any]:
    """Parse JSON hook payload from stdin cleanly, returning {} on invalid/empty input."""
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            return {}
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def is_claude_payload(payload: dict[str, Any]) -> bool:
    """Detect Claude Code snake_case hook payloads vs Antigravity camelCase payloads."""
    if any(k in payload for k in ("hook_event_name", "tool_name", "tool_input", "stop_hook_active")):
        return True
    if "prompt" in payload and "lastUserInput" not in payload and "hookEventName" not in payload:
        return True
    return False


def get_event_name(payload: dict[str, Any], default: str = "") -> str:
    return str(payload.get("hookEventName") or payload.get("hook_event_name") or default)


def get_conversation_id(payload: dict[str, Any]) -> str:
    return str(
        payload.get("conversationId")
        or payload.get("session_id")
        or payload.get("sessionId")
        or "default"
    )


def extract_tool_info(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return normalized (tool_name, tool_args) across Antigravity and Claude Code payloads."""
    tool_call = payload.get("toolCall")
    if isinstance(tool_call, dict):
        name = str(tool_call.get("name") or "")
        args = tool_call.get("args")
        return name, args if isinstance(args, dict) else {}

    name = str(payload.get("tool_name") or payload.get("toolName") or "")
    args = payload.get("tool_input") or payload.get("toolInput") or payload.get("input") or {}
    return name, args if isinstance(args, dict) else {}


def extract_candidate_paths(payload: dict[str, Any]) -> list[str]:
    """Extract all candidate file paths referenced by a hook tool payload."""
    _, args = extract_tool_info(payload)
    paths: list[str] = []
    for key in PATH_ARG_KEYS:
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            paths.append(val.strip())

    for key in ("paths", "Paths"):
        val = args.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item.strip():
                    paths.append(item.strip())

    return paths


def resolve_against_repo(raw_path: str) -> Path | None:
    """Resolve raw_path safely relative to REPO_ROOT if not already absolute."""
    if not raw_path:
        return None
    try:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        return candidate.resolve()
    except Exception:
        return None


def to_repo_relative(raw_path: str) -> str:
    """Return POSIX path relative to REPO_ROOT (or ../... if outside repo)."""
    resolved = resolve_against_repo(raw_path)
    if resolved is None:
        return raw_path.replace("\\", "/")
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        try:
            return os.path.relpath(resolved, REPO_ROOT.resolve()).replace("\\", "/")
        except Exception:
            return resolved.as_posix()


def is_sgs_repo_path(raw_path: str) -> bool:
    """True when raw_path targets sibling ../sgs repository (must stay read-only)."""
    resolved = resolve_against_repo(raw_path)
    sgs_root = (REPO_ROOT.parent / "sgs").resolve()
    if resolved is None:
        normalized = raw_path.replace("\\", "/").lower()
        return "/sgs/" in normalized or normalized.startswith("../sgs")
    try:
        resolved.relative_to(sgs_root)
        return True
    except ValueError:
        return False


def extract_user_prompt(payload: dict[str, Any]) -> str:
    """Extract the user prompt across Antigravity PreInvocation and Claude UserPromptSubmit."""
    for key in ("lastUserInput", "prompt", "user_prompt", "userInput"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def emit_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=True))


def emit_noop() -> None:
    print("{}")


def emit_context(
    text: str,
    *,
    payload: dict[str, Any],
    antigravity_event: str,
    claude_event: str,
) -> None:
    """Emit injected system/additional context using host-native schema."""
    cleaned = text.strip()
    if not cleaned:
        emit_noop()
        return

    if is_claude_payload(payload):
        emit_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": claude_event,
                    "additionalContext": cleaned,
                }
            }
        )
        return

    out: dict[str, Any] = {
        "injectSteps": [{"systemMessage": {"systemMessage": cleaned}}],
    }
    if antigravity_event == "PreInvocation":
        out["terminationBehavior"] = ""
    emit_json(out)


def emit_tool_deny(reason: str, *, payload: dict[str, Any]) -> None:
    """Emit a host-native PreToolUse deny response."""
    if is_claude_payload(payload):
        emit_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
        return

    emit_json({"decision": "deny", "reason": reason})


def emit_tool_pass(*, payload: dict[str, Any]) -> None:
    """Emit a host-native PreToolUse pass-through respecting host confirmation gates."""
    if is_claude_payload(payload):
        emit_noop()
        return

    # Antigravity requires decision on PreToolUse; 'ask' preserves Always Allow / confirmation gates.
    emit_json({"decision": "ask"})


def emit_stop_block(reason: str, *, payload: dict[str, Any]) -> None:
    """Emit a host-native Stop continuation/block response."""
    if is_claude_payload(payload):
        emit_json({"decision": "block", "reason": reason})
        return

    emit_json({"decision": "continue", "reason": reason})


def append_behavior_log(entry: dict[str, Any]) -> None:
    """Append a structured audit event to behavior_log.jsonl without failing caller."""
    try:
        BEHAVIOR_LOG.parent.mkdir(parents=True, exist_ok=True)
        record = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
        with BEHAVIOR_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
    except Exception:
        pass
