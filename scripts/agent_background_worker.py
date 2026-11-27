#!/usr/bin/env python3
"""Background behavior-to-skill analyzer and error-to-eval runner for Satz-Browser."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
HOOK_DIR = REPO_ROOT / "dev" / "agents" / "hooks"
for _p in (str(SCRIPTS_DIR), str(HOOK_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import behavior_eval_store  # noqa: E402
import pre_commit_dev_sync  # noqa: E402
import security_audit  # noqa: E402
from hook_common import append_behavior_log  # noqa: E402

STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "please", "want",
    "have", "need", "make", "when", "what", "how", "should", "would", "could",
    "using", "about", "there", "here", "then", "also", "some", "work", "let", "lets",
}
CORRECTION_RE = re.compile(r"\b(?:always|never|stop doing|remember to|instead of|make sure)\b", re.I)
INJECTION_STRIP_RE = re.compile(
    r"(?:ignore\s+(?:all\s+)?(?:prior|previous)\s+instructions|<\|system\|>|<tool_call>|bypass_confirm|send_gate\s*=\s*false)",
    re.I,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(text: str, max_len: int = 36) -> str:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    filtered = [t for t in tokens if t not in STOP_WORDS and len(t) >= 2]
    slug = "-".join((filtered or tokens or ["workflow"])[:5])[:max_len].strip("-")
    return slug or "workflow"


def _tokenize(text: str) -> set[str]:
    return {
        tok for tok in re.findall(r"[a-z0-9_/-]{3,}", text.lower())
        if tok not in STOP_WORDS
    }


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / max(1, union)


def _sanitize_line(text: str) -> str:
    cleaned = security_audit.redact_text(INJECTION_STRIP_RE.sub("[redacted]", text))
    return " ".join(cleaned.replace("\u2014", "-").replace("\u2013", "-").split())


def _load_events(db_path: Path, *, include_analyzed: bool = False) -> list[dict[str, Any]]:
    if not db_path.is_file():
        return []
    conn = sqlite3.connect(str(db_path), timeout=2.0)
    conn.row_factory = sqlite3.Row
    try:
        where = "" if include_analyzed else "WHERE analyzed = 0"
        rows = conn.execute(f"SELECT * FROM raw_events {where} ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _mark_analyzed(db_path: Path, max_id: int) -> None:
    if not db_path.is_file() or max_id <= 0:
        return
    conn = sqlite3.connect(str(db_path), timeout=2.0)
    try:
        with conn:
            conn.execute("UPDATE raw_events SET analyzed = 1 WHERE id <= ?", (max_id,))
    finally:
        conn.close()


def _cluster_prompts(events: list[dict[str, Any]], *, min_cluster: int = 3) -> list[dict[str, Any]]:
    """Cluster recurring prompt tasks across distinct conversations along with observed touched paths."""
    prompts = [e for e in events if e.get("event_type") == "prompt" and len(str(e.get("prompt_text") or "")) >= 10]
    tools_by_conv: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        if ev.get("event_type") in ("tool_use", "tool_error"):
            tools_by_conv.setdefault(str(ev.get("conv_id") or ""), []).append(ev)

    clusters: list[dict[str, Any]] = []
    for ev in prompts:
        text = _sanitize_line(str(ev.get("prompt_text") or ""))
        toks = _tokenize(text)
        if len(toks) < 2:
            continue
        matched = None
        for cl in clusters:
            if _jaccard(toks, cl["tokens"]) >= 0.34:
                matched = cl
                break
        if matched is None:
            matched = {
                "tokens": set(toks),
                "prompts": [],
                "conv_ids": set(),
                "tools": set(),
                "paths": set(),
            }
            clusters.append(matched)
        else:
            matched["tokens"] |= toks

        matched["prompts"].append(text[:180])
        cid = str(ev.get("conv_id") or "")
        if cid:
            matched["conv_ids"].add(cid)
        for tev in tools_by_conv.get(cid, []):
            if tev.get("tool_name"):
                matched["tools"].add(str(tev["tool_name"]))
            try:
                for rp in json.loads(str(tev.get("rel_paths_json") or "[]")):
                    matched["paths"].add(str(rp))
            except Exception:
                pass

    qualified = [
        cl for cl in clusters
        if len(cl["prompts"]) >= min_cluster
    ]
    return qualified


def _extract_rule_candidates(events: list[dict[str, Any]], out_path: Path) -> int:
    existing: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    if out_path.is_file():
        try:
            loaded = json.loads(out_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                existing = loaded
                seen_hashes = {str(x.get("sig") or "") for x in existing}
        except Exception:
            pass

    added = 0
    for ev in events:
        text = _sanitize_line(str(ev.get("prompt_text") or ""))
        etype = str(ev.get("event_type") or "")
        candidate_rule = ""
        source = ""
        if etype == "prompt" and CORRECTION_RE.search(text):
            candidate_rule = text[:220]
            source = "user_instruction"
        elif etype == "pre_tool_deny" and ev.get("error_text"):
            candidate_rule = _sanitize_line(str(ev["error_text"]))[:220]
            source = "pre_tool_deny"
        if not candidate_rule:
            continue
        sig = hashlib.sha256(candidate_rule.lower().encode("utf-8")).hexdigest()[:12]
        if sig in seen_hashes:
            continue
        seen_hashes.add(sig)
        existing.append(
            {
                "sig": sig,
                "ts": _utc_now(),
                "source": source,
                "rule": candidate_rule,
            }
        )
        added += 1

    if added > 0:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(existing[-100:], indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return added


def _synthesize_skills(
    clusters: list[dict[str, Any]],
    *,
    proposals_dir: Path,
    skills_dir: Path,
    auto_promote: bool = False,
) -> list[str]:
    written: list[str] = []
    target_base = skills_dir if auto_promote else proposals_dir
    for cl in clusters:
        rep_prompt = cl["prompts"][0]
        slug = f"auto-{_slugify(rep_prompt)}"
        skill_dir = target_base / slug
        # Skip if already promoted to active skills or already rejected manually.
        if (skills_dir / slug / "SKILL.md").is_file() and not auto_promote:
            continue
        skill_dir.mkdir(parents=True, exist_ok=True)
        paths_list = sorted(cl["paths"])[:8]
        tools_list = sorted(cl["tools"])[:6]
        prompts_list = cl["prompts"][:5]

        lines = [
            "---",
            f"name: {slug}",
            "description: >-",
            f"  Workflow skill distilled from {len(cl['prompts'])} developer prompt(s) covering: {_sanitize_line(rep_prompt)[:120]}",
            "---",
            "",
            f"# Synthesized Workflow: `{slug}`",
            "",
            f"- **Captured:** {_utc_now()}",
            f"- **Evidence Count:** {len(cl['prompts'])} prompt(s) across {max(1, len(cl['conv_ids']))} session(s)",
            f"- **Status:** {'Active (Auto-Promoted)' if auto_promote else 'Proposal (Pending Review)'}",
            "",
            "## Triggering Developer Requests",
        ]
        for p in prompts_list:
            lines.append(f"- {p}")
        lines.append("")
        if paths_list:
            lines.append("## Frequently Touched Files / Scopes")
            for rp in paths_list:
                lines.append(f"- `{rp}`")
            lines.append("")
        if tools_list:
            lines.append("## Typical Tool Chain")
            lines.append(f"- Tools observed: `{', '.join(tools_list)}`")
            lines.append("")
        lines.extend(
            [
                "## Standard Verification Checklist",
                "1. Search Dev Brain before changes: `python scripts/dev_brain.py search \"<topic>\" --neighbors`",
                "2. Validate relevant unit tests, i18n (`node scripts/i18n_extract.mjs --check`), or release gate.",
                "3. Keep `dev/brain/brain_index.sqlite` synced (`python scripts/dev_brain.py reindex`) if modifying `dev/`.",
            ]
        )
        out_md = skill_dir / "SKILL.md"
        out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(slug)
    return written


def _run_background_evals(
    events: list[dict[str, Any]],
    *,
    repo_root: Path,
    evals_dir: Path,
) -> dict[str, Any]:
    """Generate regression cases from agent/tool errors and execute fast repository invariant evals."""
    auto_yaml = evals_dir / "auto_eval_cases.yaml"
    existing_cases: list[dict[str, Any]] = []
    if auto_yaml.is_file():
        try:
            loaded = yaml.safe_load(auto_yaml.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict) and isinstance(loaded.get("cases"), list):
                existing_cases = list(loaded["cases"])
        except Exception:
            pass

    seen_ids = {str(c.get("id") or "") for c in existing_cases}
    error_events = [e for e in events if not int(e.get("ok") or 0)]
    new_eval_added = 0
    for ev in error_events:
        err_text = _sanitize_line(str(ev.get("error_text") or ""))
        if not err_text:
            continue
        sig = hashlib.sha256(f"{ev.get('event_type')}|{err_text[:150]}".encode("utf-8")).hexdigest()[:8]
        cid = f"auto-err-{sig}"
        if cid in seen_ids:
            continue
        seen_ids.add(cid)

        check_type = "manifest_parity"
        if "em/en dash" in err_text or "hex color" in err_text or "i18n" in err_text:
            check_type = "ui_and_weight_hygiene"
        elif "broken graph link" in err_text:
            check_type = "dev_brain_monitor"

        existing_cases.append(
            {
                "id": cid,
                "captured_at": _utc_now(),
                "source_event": str(ev.get("event_type") or "error"),
                "description": err_text[:180],
                "check_type": check_type,
            }
        )
        new_eval_added += 1

    if new_eval_added > 0 or not auto_yaml.is_file():
        auto_yaml.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "cases": existing_cases[-50:]}
        auto_yaml.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")

    # Execute fast deterministic invariant checks.
    failed_ids: list[str] = []
    checks_run = 0
    try:
        checks_run += 1
        pre_commit_dev_sync.check_version_parity()
    except Exception:
        failed_ids.append("gate-version-parity")

    try:
        checks_run += 1
        pre_commit_dev_sync.check_ui_and_weight_limits()
    except Exception:
        failed_ids.append("gate-planck-shard-and-ui-hygiene")

    try:
        checks_run += 1
        from dev_brain import DevBrain

        mon = DevBrain(repo_root).monitor()
        if int(mon.get("broken_edge_count") or 0) > 0:
            failed_ids.append("dev-brain-broken-links")
    except Exception:
        failed_ids.append("dev-brain-monitor-error")

    result = {
        "ts": _utc_now(),
        "checks_run": checks_run,
        "auto_cases_total": len(existing_cases),
        "new_auto_cases": new_eval_added,
        "passed": len(failed_ids) == 0,
        "failed_ids": failed_ids,
    }
    hist_path = evals_dir / "eval_history.jsonl"
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    with hist_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(result, ensure_ascii=True) + "\n")
    return result


def run_cycle(
    *,
    repo_root: Path | None = None,
    db_path: Path | None = None,
    force: bool = False,
    auto_promote: bool = False,
    min_cluster: int = 3,
) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    raw_db = db_path or behavior_eval_store.get_raw_db_path()
    events = _load_events(raw_db, include_analyzed=force)
    all_prompt_events = _load_events(raw_db, include_analyzed=True)

    behavior_dir = root / "dev" / "agents" / "behavior"
    proposals_dir = behavior_dir / "proposals"
    skills_dir = root / "dev" / "agents" / "skills"
    evals_dir = root / "dev" / "agents" / "evals"

    clusters = _cluster_prompts(all_prompt_events, min_cluster=min_cluster)
    synthesized = _synthesize_skills(
        clusters,
        proposals_dir=proposals_dir,
        skills_dir=skills_dir,
        auto_promote=auto_promote,
    )
    rules_added = _extract_rule_candidates(events, behavior_dir / "rule_candidates.json")
    eval_summary = _run_background_evals(events, repo_root=root, evals_dir=evals_dir)

    max_id = max((int(e.get("id") or 0) for e in events), default=0)
    if max_id > 0:
        _mark_analyzed(raw_db, max_id)

    if synthesized:
        append_behavior_log(
            {
                "event": "skills_synthesized",
                "auto_promote": auto_promote,
                "skills": synthesized,
            }
        )

    if repo_root is None and db_path is None:
        try:
            from dev_brain import DevBrain

            DevBrain(root).reindex()
        except Exception:
            pass

    return {
        "ok": True,
        "events_processed": len(events),
        "clusters_found": len(clusters),
        "skills_written": synthesized,
        "rules_added": rules_added,
        "eval_summary": eval_summary,
    }


def approve_proposal(slug: str, *, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    src = root / "dev" / "agents" / "behavior" / "proposals" / slug
    dst = root / "dev" / "agents" / "skills" / slug
    if not (src / "SKILL.md").is_file():
        raise FileNotFoundError(f"Proposal not found: {src}")
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    text = (dst / "SKILL.md").read_text(encoding="utf-8", errors="ignore")
    text = text.replace("Proposal (Pending Review)", "Active (Approved)")
    (dst / "SKILL.md").write_text(text, encoding="utf-8")

    append_behavior_log({"event": "skill_promoted", "slug": slug, "path": f"dev/agents/skills/{slug}/SKILL.md"})
    try:
        from dev_brain import DevBrain

        DevBrain(root).reindex()
    except Exception:
        pass
    return {"ok": True, "approved": slug, "path": str(dst / "SKILL.md")}


def reject_proposal(slug: str, *, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    src = root / "dev" / "agents" / "behavior" / "proposals" / slug
    if not src.exists():
        raise FileNotFoundError(f"Proposal not found: {src}")
    shutil.rmtree(src)
    append_behavior_log({"event": "skill_rejected", "slug": slug})
    return {"ok": True, "rejected": slug}


def main() -> int:
    parser = argparse.ArgumentParser(description="Satz background behavior-to-skill & error-to-eval worker")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Process unanalyzed events and run background checks")
    p_run.add_argument("--force", action="store_true", help="Reprocess all stored events")
    p_run.add_argument("--auto-promote", action="store_true", help="Promote clustered skills directly into dev/agents/skills/")
    p_run.add_argument("--min-cluster", type=int, default=3)
    p_run.add_argument("--quiet", action="store_true")

    sub.add_parser("list-proposals", help="List candidate skills staged under dev/agents/behavior/proposals/")

    p_app = sub.add_parser("approve", help="Promote a staged skill proposal into dev/agents/skills/ and reindex")
    p_app.add_argument("slug")

    p_rej = sub.add_parser("reject", help="Remove a staged skill proposal")
    p_rej.add_argument("slug")

    sub.add_parser("status", help="Show raw telemetry queue and proposal counts")

    args = parser.parse_args()
    if args.cmd == "run":
        res = run_cycle(force=args.force, auto_promote=args.auto_promote, min_cluster=args.min_cluster)
        if not args.quiet:
            print(json.dumps(res, indent=2))
        return 0
    if args.cmd == "list-proposals":
        prop_dir = REPO_ROOT / "dev" / "agents" / "behavior" / "proposals"
        slugs = [p.parent.name for p in sorted(prop_dir.glob("*/SKILL.md"))] if prop_dir.is_dir() else []
        print(json.dumps({"proposals": slugs}, indent=2))
        return 0
    if args.cmd == "approve":
        print(json.dumps(approve_proposal(args.slug), indent=2))
        return 0
    if args.cmd == "reject":
        print(json.dumps(reject_proposal(args.slug), indent=2))
        return 0
    if args.cmd == "status":
        prop_dir = REPO_ROOT / "dev" / "agents" / "behavior" / "proposals"
        slugs = [p.parent.name for p in sorted(prop_dir.glob("*/SKILL.md"))] if prop_dir.is_dir() else []
        print(
            json.dumps(
                {
                    "raw_db": str(behavior_eval_store.get_raw_db_path()),
                    "unanalyzed_events": behavior_eval_store.count_unanalyzed(),
                    "pending_proposals": slugs,
                },
                indent=2,
            )
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
