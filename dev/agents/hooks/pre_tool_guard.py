#!/usr/bin/env python3
"""PreToolUse guard hook: enforce hard Satz-Browser invariants across Antigravity & Claude Code."""

from __future__ import annotations

import re
from typing import Any

import pre_commit_dev_sync
from hook_common import (
    REPO_ROOT,
    append_behavior_log,
    emit_noop,
    emit_tool_deny,
    extract_candidate_paths,
    extract_tool_info,
    is_sgs_repo_path,
    read_payload,
    resolve_against_repo,
    to_repo_relative,
)

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
SHELL_TOOL_NAMES = {"run_command", "Bash"}

CSS_PROP_HEX_RE = re.compile(r":[^;{}\n]*#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----")
TAURI_INLINE_KEY_RE = re.compile(r"TAURI_SIGNING_PRIVATE_KEY\s*=\s*['\"]?[A-Za-z0-9+/=]{16,}")
GIT_TAG_CMD_RE = re.compile(r"\bgit\s+tag\b")
GIT_TAG_READ_FLAGS_RE = re.compile(r"\bgit\s+tag\b(?:\s+(?:-l|--list|-v|--verify|-n\d*)\b|$)")
GIT_TAG_VERSION_RE = re.compile(r"\bv?(\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.]+)?)\b")

SENSITIVE_KEY_FILES = (
    ".minisign.key",
    "id_rsa",
    "id_ed25519",
)


def _extract_written_text(args: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("Content", "Replacement", "content", "new_string", "CodeContent", "ReplacementContent", "new_source"):
        val = args.get(key)
        if isinstance(val, str) and val:
            parts.append(val)

    chunks = args.get("ReplacementChunks")
    if isinstance(chunks, list):
        for chunk in chunks:
            if isinstance(chunk, dict):
                rc = chunk.get("ReplacementContent")
                if isinstance(rc, str) and rc:
                    parts.append(rc)
    return "\n".join(parts)


def _check_write_violation(payload: dict[str, Any], args: dict[str, Any]) -> str | None:
    candidate_paths = extract_candidate_paths(payload)
    written_text = _extract_written_text(args)

    for raw_path in candidate_paths:
        if is_sgs_repo_path(raw_path):
            return (
                f"Blocked write targeting sibling ../sgs repo ({raw_path}). "
                "Per dev/agents/INSTRUCTIONS.md, ../sgs must stay strictly read-only."
            )

        rel = to_repo_relative(raw_path).lower()
        base_name = rel.rsplit("/", 1)[-1]
        if base_name in SENSITIVE_KEY_FILES or rel.endswith(".pem") or rel.endswith(".key"):
            return (
                f"Blocked writing private key material inside repository ({rel}). "
                "Store signing keys in ~/.tauri/ or CI Secrets, never inside git."
            )

        if rel == "src/i18n/catalog.ts" or rel.startswith("src/i18n/"):
            if "\u2014" in written_text or "\u2013" in written_text:
                return (
                    f"Blocked em/en dash in UI localization file ({rel}). "
                    "Per AGENTS.md / INSTRUCTIONS.md, replace em/en dashes with '-', ',', or ':'."
                )

        if rel.startswith("src/") and rel.endswith(".css") and rel != "src/design-system/tokens.css":
            # Strip CSS comments before checking property declarations for hardcoded hex literals.
            stripped_css = re.sub(r"/\*.*?\*/", "", written_text, flags=re.DOTALL)
            if CSS_PROP_HEX_RE.search(stripped_css):
                return (
                    f"Blocked hardcoded hex color literal in {rel}. "
                    "Use CSS variables from src/design-system/tokens.css only."
                )

    if written_text:
        if PRIVATE_KEY_RE.search(written_text) or TAURI_INLINE_KEY_RE.search(written_text):
            resolved_first = resolve_against_repo(candidate_paths[0]) if candidate_paths else None
            is_inside_repo = True
            if resolved_first is not None:
                try:
                    resolved_first.relative_to(REPO_ROOT.resolve())
                except ValueError:
                    is_inside_repo = False
            if is_inside_repo:
                return (
                    "Blocked writing inline private key or TAURI_SIGNING_PRIVATE_KEY secret into workspace file. "
                    "Keep secrets in GitHub Actions Secrets or external keystore paths."
                )

    return None


def _check_shell_violation(args: dict[str, Any]) -> str | None:
    cmd = str(args.get("CommandLine") or args.get("command") or "").strip()
    if not cmd:
        return None

    if GIT_TAG_CMD_RE.search(cmd) and not GIT_TAG_READ_FLAGS_RE.match(cmd):
        try:
            manifest_version = pre_commit_dev_sync.check_version_parity()
        except AssertionError as exc:
            return (
                f"Blocked git tag creation: release manifest parity failed ({exc}). "
                "Synchronize package.json, src-tauri/Cargo.toml, and src-tauri/tauri.conf.json first."
            )
        except Exception as exc:
            return f"Blocked git tag creation: could not verify release manifest parity ({exc})."

        # Check explicit tag version argument (excluding flag values like git tag -m "...").
        tokens = cmd.split()
        for tok in tokens:
            if tok.startswith("v") and GIT_TAG_VERSION_RE.fullmatch(tok):
                tag_ver = tok[1:]
                if tag_ver != manifest_version:
                    return (
                        f"Blocked git tag {tok}: manifests declare version {manifest_version}. "
                        "Update manifests or tag the matching version."
                    )

    return None


def evaluate_tool_call(payload: dict[str, Any]) -> str | None:
    tool_name, args = extract_tool_info(payload)
    if not tool_name:
        return None

    if tool_name in WRITE_TOOL_NAMES or extract_candidate_paths(payload):
        # Shell tools might pass Cwd; only run write checks when tool isn't exclusively a shell tool
        if tool_name not in SHELL_TOOL_NAMES:
            reason = _check_write_violation(payload, args)
            if reason:
                return reason

    if tool_name in SHELL_TOOL_NAMES or "CommandLine" in args or "command" in args:
        return _check_shell_violation(args)

    return None


def main() -> None:
    payload: dict[str, Any] = read_payload()
    try:
        reason = evaluate_tool_call(payload)
        if reason:
            tool_name, _ = extract_tool_info(payload)
            append_behavior_log({"event": "pre_tool_deny", "tool": tool_name, "reason": reason})
            emit_tool_deny(reason, payload=payload)
            return
    except Exception:
        pass
    emit_noop()


if __name__ == "__main__":
    main()
