#!/usr/bin/env python3
"""SessionStart hook: inject core Satz-Browser instructions, active plans, and Dev Brain status."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from hook_common import ERROR_LOG, REPO_ROOT, emit_context, emit_noop, read_payload

OPEN_TASK_RE = re.compile(r"^\s*-\s*\[([ /])\]", re.MULTILINE)


def _summarize_active_plans(limit: int = 5) -> list[str]:
    plans_root = REPO_ROOT / "dev" / "plans"
    if not plans_root.exists():
        return []

    summaries: list[str] = []
    for tasks_file in sorted(plans_root.glob("*/tasks.md"), reverse=True):
        if tasks_file.parent.name.startswith("_"):
            continue
        try:
            text = tasks_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        matches = OPEN_TASK_RE.findall(text)
        if not matches:
            continue
        in_progress = sum(1 for m in matches if m == "/")
        pending = sum(1 for m in matches if m == " ")
        plan_name = tasks_file.parent.name
        summaries.append(f"{plan_name} (in_progress={in_progress}, pending={pending})")
        if len(summaries) >= limit:
            break
    return summaries


def _recent_errors(limit: int = 2) -> list[str]:
    if not ERROR_LOG.exists():
        return []
    lines = [ln.strip() for ln in ERROR_LOG.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
    recent: list[str] = []
    for raw in lines[-limit:]:
        try:
            item = json.loads(raw)
        except Exception:
            continue
        err_id = item.get("id") or "err"
        summary = item.get("summary") or item.get("lesson") or ""
        if summary:
            recent.append(f"{err_id}: {str(summary)[:120]}")
    return recent


def _brain_status_line() -> str:
    try:
        from scripts.dev_brain import DevBrain

        report = DevBrain(REPO_ROOT).monitor()
        latest_eval = report.get("latest_eval") or {}
        mrr = latest_eval.get("mrr")
        mrr_txt = f", eval_mrr={mrr:.2f}" if isinstance(mrr, (int, float)) else ""
        return (
            f"DevBrain ok={report.get('ok')} (nodes={report.get('nodes')}, "
            f"edges={report.get('edges')}, stale={report.get('stale_count')}, "
            f"broken_edges={report.get('broken_edge_count')}{mrr_txt})"
        )
    except Exception as exc:
        return f"DevBrain status unavailable ({exc})"


def build_session_bootstrap() -> str:
    lines = [
        "[Satz-Browser Core Agent Instructions & Dev Brain Bootstrap]",
        "Authoritative docs: dev/agents/INSTRUCTIONS.md | dev/agents/core_dev_flows.md | dev/agents/release_management.md",
        "Mandatory guardrails:",
        "- Keep sibling ../sgs strictly read-only and optional at runtime.",
        "- Shipped Planck model (sidecar/models/planck/) must stay <90 MB per shard.",
        "- UI: use src/design-system/tokens.css variables only (zero raw hex in CSS components), zero em/en dashes in UI copy, keep src/i18n/catalog.ts synced (node scripts/i18n_extract.mjs --check).",
        "- Release parity: keep package.json, src-tauri/Cargo.toml, and src-tauri/tauri.conf.json versions synchronized; run python dev/agents/hooks/release_gate.py before tagging.",
        "- Lookup: run python scripts/dev_brain.py search \"<topic>\" --neighbors before non-trivial pipeline/UI/release changes.",
        f"Graph health: {_brain_status_line()}",
    ]

    plans = _summarize_active_plans()
    if plans:
        lines.append("Active plans: " + "; ".join(plans))

    errors = _recent_errors()
    if errors:
        lines.append("Recent error lessons: " + " | ".join(errors))

    return "\n".join(lines)


def main() -> None:
    payload: dict[str, Any] = read_payload()
    try:
        text = build_session_bootstrap()
        emit_context(
            text,
            payload=payload,
            antigravity_event="SessionStart",
            claude_event="SessionStart",
        )
    except Exception:
        emit_noop()


if __name__ == "__main__":
    main()
