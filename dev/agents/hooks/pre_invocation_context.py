#!/usr/bin/env python3
"""PreInvocation / UserPromptSubmit hook: inject read-only Dev Brain context relevant to the prompt."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from hook_common import (
    REPO_ROOT,
    emit_context,
    emit_noop,
    extract_user_prompt,
    get_conversation_id,
    read_payload,
)

MAX_CACHE_ENTRIES = 32


def _cache_file() -> Path:
    override = os.environ.get("SATZ_HOOK_CACHE_PATH", "").strip()
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "satz_dev_brain_preinv_cache.json"


def _already_injected(conv_id: str, prompt_hash: str) -> bool:
    cache_path = _cache_file()
    try:
        if cache_path.exists():
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get(conv_id) == prompt_hash:
                return True
    except Exception:
        pass
    return False


def _record_injected(conv_id: str, prompt_hash: str) -> None:
    cache_path = _cache_file()
    try:
        data: dict[str, str] = {}
        if cache_path.exists():
            loaded = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = {str(k): str(v) for k, v in loaded.items()}
        data.pop(conv_id, None)
        data[conv_id] = prompt_hash
        if len(data) > MAX_CACHE_ENTRIES:
            keys = list(data.keys())[-MAX_CACHE_ENTRIES:]
            data = {k: data[k] for k in keys}
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
    except Exception:
        pass


def build_prompt_context(prompt: str) -> str:
    from scripts.dev_brain import DevBrain

    brain = DevBrain(REPO_ROOT)
    health = brain.monitor()
    results = brain.search(
        prompt,
        limit=3,
        include_neighbors=True,
        log_query=False,
    )
    lines: list[str] = []

    stale_count = int(health.get("stale_count") or 0)
    if stale_count > 0:
        lines.append(
            f"[DevBrain Notice] {stale_count} stale file(s) detected in dev/. "
            "Run `python scripts/dev_brain.py reindex` after finishing dev/ edits."
        )

    if isinstance(results, list) and results:
        lines.append("[DevBrain Relevant Context]")
        for item in results:
            path_str = item.get("path") or item.get("id") or ""
            kind = item.get("kind") or "doc"
            title = item.get("title") or path_str
            score = item.get("score")
            neighbors = item.get("neighbors") or []
            nbr_names = ", ".join(
                str(n.get("neighbor_id") or n.get("target") or "")
                for n in neighbors[:2]
                if n.get("neighbor_id") or n.get("target")
            )
            nbr_suffix = f" -> related: {nbr_names}" if nbr_names else ""
            lines.append(f"- [{kind}] {path_str} ({title}, score={score}){nbr_suffix}")

    return "\n".join(lines)


def main() -> None:
    payload: dict[str, Any] = read_payload()
    try:
        invocation_num = payload.get("invocationNum")
        if isinstance(invocation_num, int) and invocation_num > 1:
            emit_noop()
            return

        prompt = extract_user_prompt(payload)
        if len(prompt) < 4:
            emit_noop()
            return

        conv_id = get_conversation_id(payload)
        prompt_hash = hashlib.sha256(prompt.encode("utf-8", errors="ignore")).hexdigest()
        disable_cache = bool(payload.get("disableCache"))
        if not disable_cache and _already_injected(conv_id, prompt_hash):
            emit_noop()
            return

        context_text = build_prompt_context(prompt)
        if not context_text.strip():
            emit_noop()
            return

        if not disable_cache:
            _record_injected(conv_id, prompt_hash)

        emit_context(
            context_text,
            payload=payload,
            antigravity_event="PreInvocation",
            claude_event="UserPromptSubmit",
        )
    except Exception:
        emit_noop()


if __name__ == "__main__":
    main()
