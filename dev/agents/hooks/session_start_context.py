#!/usr/bin/env python3
"""SessionStart hook: inject core Satz-Browser instructions, live skills roster, plans, and Dev Brain status."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

from hook_common import ERROR_LOG, REPO_ROOT, emit_context, emit_noop, read_payload

OPEN_TASK_RE = re.compile(r"^\s*-\s*\[([ /])\]", re.MULTILINE)


def _discover_repo_skills() -> list[tuple[str, str]]:
    skills_root = REPO_ROOT / "dev" / "agents" / "skills"
    if not skills_root.is_dir():
        return []
    discovered: list[tuple[str, str]] = []
    for skill_md in sorted(skills_root.glob("*/SKILL.md")):
        try:
            text = skill_md.read_text(encoding="utf-8", errors="ignore")
            parts = text.split("---", 2)
            if len(parts) < 3:
                continue
            meta = yaml.safe_load(parts[1]) or {}
            name = str(meta.get("name") or skill_md.parent.name).strip()
            desc = " ".join(str(meta.get("description") or "").split())[:130]
            if name:
                discovered.append((name, desc))
        except Exception:
            continue
    return discovered


def _pending_skill_proposals(limit: int = 4) -> list[str]:
    prop_root = REPO_ROOT / "dev" / "agents" / "behavior" / "proposals"
    if not prop_root.is_dir():
        return []
    items = [p.parent.name for p in sorted(prop_root.glob("*/SKILL.md"))]
    return items[:limit]


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
        summaries.append(f"{tasks_file.parent.name} (in_progress={in_progress}, pending={pending})")
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
            recent.append(f"{err_id}: {str(summary)[:110]}")
    return recent


def _latest_auto_eval_alert() -> str | None:
    hist = REPO_ROOT / "dev" / "agents" / "evals" / "eval_history.jsonl"
    if not hist.is_file():
        return None
    lines = [ln.strip() for ln in hist.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
    if not lines:
        return None
    try:
        last = json.loads(lines[-1])
        if last.get("passed") is False:
            failed = last.get("failed_ids") or []
            return f"Background eval ALERT: {len(failed)} check(s) failed ({', '.join(str(x) for x in failed[:4])})"
    except Exception:
        pass
    return None


def _brain_status_line() -> str:
    try:
        from dev_brain import DevBrain

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
        "Authoritative docs: dev/agents/INSTRUCTIONS.md | dev/agents/core_dev_flows.md | dev/agents/release_management.md | dev/docs/SYSTEM_OVERVIEW.md",
        "Mandatory guardrails:",
        "- Keep sibling ../sgs strictly read-only and optional at runtime.",
        "- Shipped Planck model (sidecar/models/planck/) must stay <90 MB per shard.",
        "- UI: use src/design-system/tokens.css variables only (zero raw hex in CSS components), zero em/en dashes in UI copy, keep src/i18n/catalog.ts synced (node scripts/i18n_extract.mjs --check).",
        "- Release parity: keep package.json, src-tauri/Cargo.toml, and src-tauri/tauri.conf.json versions synchronized; run python dev/agents/hooks/release_gate.py before tagging.",
        "- Pre-push privacy & key scrubbing: never commit/push private keys, API tokens, real personal emails, or OS usernames (run python scripts/security_audit.py scan).",
        "- Lookup: run python scripts/dev_brain.py search \"<topic>\" --neighbors before non-trivial pipeline/UI/release changes.",
        f"Graph health: {_brain_status_line()}",
    ]

    if (REPO_ROOT / ".git").exists() and not (REPO_ROOT / ".git" / "hooks" / "pre-push").is_file():
        lines.append("Security Alert: Git pre-push hook missing; run `python scripts/security_audit.py install-git-hooks`.")

    try:
        res_lr = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res_lr.returncode == 0:
            parts = res_lr.stdout.strip().split()
            if len(parts) == 2 and int(parts[1]) > 0:
                lines.append(
                    f"Git Sync Notice: local branch is {parts[1]} commit(s) behind upstream; run `python scripts/git_sync.py pull` to rebase cleanly."
                )
    except Exception:
        pass

    skills = _discover_repo_skills()
    if skills:
        lines.append("Available repo skills (read dev/agents/skills/<name>/SKILL.md when task matches):")
        for name, desc in skills:
            lines.append(f"  - {name}: {desc}")

    proposals = _pending_skill_proposals()
    if proposals:
        lines.append(
            "Pending auto-synthesized skill proposals (review via `python scripts/agent_background_worker.py approve <slug>`): "
            + ", ".join(proposals)
        )

    plans = _summarize_active_plans()
    if plans:
        lines.append("Active plans: " + "; ".join(plans))

    errors = _recent_errors()
    if errors:
        lines.append("Recent error lessons: " + " | ".join(errors))

    eval_alert = _latest_auto_eval_alert()
    if eval_alert:
        lines.append(eval_alert)

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
