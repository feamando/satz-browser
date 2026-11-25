"""
Behavior-Driven Automatic Skill & Agent Builder + Site Affordance Domain Recipes.

All skills are strictly declarative DAGs composed from typed, audited Satz primitives
(`VERIFIED_SKILL_PRIMITIVES`), persisted as Markdown + YAML entities in `Skills/*.md`
via `SatzBrain`, and any external mutation step MUST pass a `send_gate` with a single-use
`confirm_token`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


READ_PRIMITIVES: frozenset[str] = frozenset(
    {
        "search_mail",
        "read_message",
        "search_brain",
        "news_digest",
        "open_tab",
        "capture_tab",
        "web_search",
        "run_comparer",
        "list_codes",
    }
)

MUTATING_PRIMITIVES: frozenset[str] = frozenset(
    {
        "actor_click_control",
        "add_watch",
        "draft_mail",
        "brain_store",
        "mail_unsubscribe",
        "hide_sender",
    }
)

VERIFIED_SKILL_PRIMITIVES: frozenset[str] = READ_PRIMITIVES | MUTATING_PRIMITIVES

_SELECTOR_UNSAFE_RE = re.compile(r"[\x00-\x1f<>`]|javascript:", re.IGNORECASE)
_INJECTION_PROMPT_RE = re.compile(
    r"(?:ignore\s+previous\s+instructions|<\|?system\|?>|</?\s*brain_store\b|bypass\s+gate|skip\s+confirm)",
    re.IGNORECASE,
)


def _utc_iso(ts: float | None = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts if ts is not None else time.time()))


def _clean_domain(domain_or_url: str) -> str:
    raw = (domain_or_url or "").strip().lower()
    if "://" in raw:
        try:
            raw = urlparse(raw).hostname or ""
        except Exception:
            raw = ""
    raw = raw.split(":")[0].removeprefix("www.").strip()
    return raw[:120]


def _sanitize_selector(selector: str) -> str:
    s = re.sub(r"\s+", " ", (selector or "").strip())
    if not s or len(s) > 220 or _SELECTOR_UNSAFE_RE.search(s):
        return ""
    return s


def ensure_skills_tables_on_conn(db_conn: sqlite3.Connection) -> None:
    db_conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS satz_behavior_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL DEFAULT 'default',
            event_type TEXT NOT NULL,
            domain TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            query TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            ts REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_satz_behavior_ts ON satz_behavior_events(profile_id, ts DESC);
        CREATE INDEX IF NOT EXISTS idx_satz_behavior_type ON satz_behavior_events(profile_id, event_type, ts DESC);

        CREATE TABLE IF NOT EXISTS satz_domain_recipes (
            domain TEXT NOT NULL,
            control_key TEXT NOT NULL,
            selector TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            action_kind TEXT NOT NULL DEFAULT 'click',
            sample_url TEXT NOT NULL DEFAULT '',
            success_count INTEGER NOT NULL DEFAULT 1,
            last_success_at REAL NOT NULL,
            PRIMARY KEY (domain, control_key)
        );
        CREATE INDEX IF NOT EXISTS idx_satz_recipes_dom ON satz_domain_recipes(domain, success_count DESC);

        CREATE TABLE IF NOT EXISTS satz_skill_proposals (
            proposal_id TEXT PRIMARY KEY,
            pattern_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'pending',
            skill_json TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 0.75,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        """
    )
    db_conn.commit()


def validate_skill_step_graph(
    step_graph: list[dict[str, Any]],
    explicit_gate_steps: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Validates a declarative Skill step graph against `VERIFIED_SKILL_PRIMITIVES`.
    Ensures acyclic `depends_on` edges, sanitizes step parameters, and enforces
    `send_gate` confirmation barriers on EVERY mutating primitive.
    """
    if not isinstance(step_graph, list) or not step_graph:
        raise ValueError("Skill step_graph must be a non-empty list of declarative steps.")

    gate_set: set[str] = {str(x).strip() for x in (explicit_gate_steps or []) if str(x).strip()}
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for idx, raw_step in enumerate(step_graph, 1):
        if not isinstance(raw_step, dict):
            raise ValueError(f"Skill step #{idx} must be an object.")
        primitive = str(raw_step.get("primitive") or "").strip()
        if primitive not in VERIFIED_SKILL_PRIMITIVES:
            raise ValueError(f"Disallowed or unverified skill primitive: '{primitive}'.")

        sid = str(raw_step.get("id") or f"step_{idx}").strip() or f"step_{idx}"
        if sid in seen_ids:
            raise ValueError(f"Duplicate skill step id: '{sid}'.")
        seen_ids.add(sid)

        raw_args = raw_step.get("args") if isinstance(raw_step.get("args"), dict) else {}
        clean_args: dict[str, Any] = {}
        for k, v in raw_args.items():
            key_s = str(k).strip()[:64]
            if not key_s:
                continue
            if isinstance(v, (str, int, float, bool)):
                val = v[:500] if isinstance(v, str) else v
                if key_s == "selector" and isinstance(val, str):
                    val = _sanitize_selector(val)
                if isinstance(val, str) and _INJECTION_PROMPT_RE.search(val):
                    raise ValueError(f"Unsafe instruction marker in step '{sid}' args.")
                clean_args[key_s] = val
            elif isinstance(v, list):
                clean_args[key_s] = [str(item)[:300] for item in v[:12]]

        deps = [str(d).strip() for d in (raw_step.get("depends_on") or []) if str(d).strip()]
        is_mut = primitive in MUTATING_PRIMITIVES
        requires_gate = bool(is_mut or raw_step.get("send_gate", False))
        if is_mut or requires_gate:
            gate_set.add(sid)

        desc = str(raw_step.get("summary") or f"{primitive}").strip()[:200]
        if _INJECTION_PROMPT_RE.search(desc):
            desc = primitive

        normalized.append(
            {
                "id": sid,
                "primitive": primitive,
                "mutating": is_mut,
                "send_gate": requires_gate,
                "args": clean_args,
                "depends_on": deps,
                "summary": desc,
            }
        )

    # Check depends_on validity + cycle freedom via topological pass
    id_map = {st["id"]: st for st in normalized}
    for st in normalized:
        for dep in st["depends_on"]:
            if dep not in id_map:
                raise ValueError(f"Step '{st['id']}' depends on unknown step '{dep}'.")
            if dep == st["id"]:
                raise ValueError(f"Self-dependency on step '{st['id']}'.")

    ordered = _toposort_steps(normalized)
    ordered_gates = [st["id"] for st in ordered if st["id"] in gate_set or st["send_gate"]]
    return ordered, ordered_gates


def _toposort_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    remaining = {st["id"]: st for st in steps}
    done: set[str] = set()
    ordered: list[dict[str, Any]] = []
    while remaining:
        progressed = False
        for sid in list(remaining.keys()):
            st = remaining[sid]
            if all(dep in done for dep in st.get("depends_on") or []):
                ordered.append(st)
                done.add(sid)
                remaining.pop(sid)
                progressed = True
        if not progressed:
            raise ValueError("Cycle detected in skill step_graph.")
    return ordered


class DomainRecipeStore:
    """Caches proven CSS/text affordance recipes per hostname across Actor & UI runs."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def record_success(
        self,
        *,
        domain: str = "",
        control_key: str,
        selector: str,
        label: str = "",
        action_kind: str = "click",
        sample_url: str = "",
    ) -> dict[str, Any]:
        dom = _clean_domain(domain or sample_url)
        ck = re.sub(r"[^a-z0-9_:-]+", "_", (control_key or "").strip().lower())[:64] or "control"
        sel = _sanitize_selector(selector)
        lbl = re.sub(r"\s+", " ", (label or "").strip())[:120]
        kind = (action_kind or "click").strip().lower()[:32]
        if not dom or not sel:
            return {"ok": False, "error": "domain and valid CSS selector required"}

        from satz_evals import validate_actor_rule_redteam

        rt_res = validate_actor_rule_redteam(
            domain=dom,
            control_key=ck,
            selector=sel,
            label=lbl,
            action_kind=kind,
        )
        if not rt_res.get("passed"):
            return {
                "ok": False,
                "error": "; ".join(f["reason"] for f in (rt_res.get("failures") or [])) or rt_res.get("summary", "Blocked by red-team gate"),
                "redteam": rt_res,
            }

        now = time.time()
        with self.runtime.store_lock:
            ensure_skills_tables_on_conn(self.runtime.store.db)
            self.runtime.store.db.execute(
                """
                INSERT INTO satz_domain_recipes
                  (domain, control_key, selector, label, action_kind, sample_url, success_count, last_success_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(domain, control_key) DO UPDATE SET
                  selector = excluded.selector,
                  label = CASE WHEN length(excluded.label) > 0 THEN excluded.label ELSE satz_domain_recipes.label END,
                  action_kind = excluded.action_kind,
                  sample_url = CASE WHEN length(excluded.sample_url) > 0 THEN excluded.sample_url ELSE satz_domain_recipes.sample_url END,
                  success_count = satz_domain_recipes.success_count + 1,
                  last_success_at = excluded.last_success_at
                """,
                (dom, ck, sel, lbl, kind, (sample_url or "")[:400], now),
            )
            self.runtime.store.db.commit()
            row = self.runtime.store.db.execute(
                "SELECT * FROM satz_domain_recipes WHERE domain = ? AND control_key = ?",
                (dom, ck),
            ).fetchone()
        return {"ok": True, "recipe": dict(row) if row else None, "redteam": rt_res}

    def list_recipes(self, domain: str = "", control_key: str = "", limit: int = 50) -> list[dict[str, Any]]:
        dom = _clean_domain(domain)
        ck = (control_key or "").strip().lower()
        with self.runtime.store_lock:
            ensure_skills_tables_on_conn(self.runtime.store.db)
            clauses: list[str] = []
            params: list[Any] = []
            if dom:
                clauses.append("domain = ?")
                params.append(dom)
            if ck:
                clauses.append("control_key = ?")
                params.append(ck)
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(max(1, min(int(limit or 50), 200)))
            rows = self.runtime.store.db.execute(
                f"""
                SELECT domain, control_key, selector, label, action_kind, sample_url, success_count, last_success_at
                FROM satz_domain_recipes
                {where}
                ORDER BY success_count DESC, last_success_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_best_recipe(self, domain_or_url: str, control_key: str = "") -> dict[str, Any] | None:
        dom = _clean_domain(domain_or_url)
        if not dom:
            return None
        items = self.list_recipes(domain=dom, control_key=control_key, limit=1)
        return items[0] if items else None

    def format_prompt_hints(self, urls_or_domains: list[str], max_recipes: int = 6) -> str:
        doms = [_clean_domain(u) for u in (urls_or_domains or []) if _clean_domain(u)]
        seen_doms = list(dict.fromkeys(doms))[:6]
        recipes: list[dict[str, Any]] = []
        for d in seen_doms:
            for rec in self.list_recipes(domain=d, limit=2):
                recipes.append(rec)
                if len(recipes) >= max_recipes:
                    break
            if len(recipes) >= max_recipes:
                break
        if not recipes:
            return ""
        lines = ["CACHED SITE AFFORDANCE RECIPES (proven CSS/control selectors):"]
        for r in recipes:
            lbl = f" label='{r['label']}'" if r.get("label") else ""
            lines.append(
                f"- {r['domain']} [{r['control_key']} -> {r['action_kind']}]: selector `{r['selector']}`{lbl} (verified x{r['success_count']})"
            )
        return "\n".join(lines)


class BehaviorMiner:
    """
    Logs lightweight user/agent behavior traces into SQLite (`satz_behavior_events`)
    and mines repeatable multi-step routines into gateable `Skills/*.md` proposals.
    """

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self._last_mine_ts: float = 0.0

    def log_event(
        self,
        event_type: str,
        *,
        domain: str = "",
        url: str = "",
        query: str = "",
        metadata: dict[str, Any] | None = None,
        ts: float | None = None,
    ) -> None:
        pm = getattr(self.runtime, "passwords", None)
        if pm is None or not pm.unlocked:
            return
        if getattr(self.runtime, "pause_learning", False):
            return
        ev_type = re.sub(r"[^a-z0-9_:-]+", "_", (event_type or "").strip().lower())[:48]
        if not ev_type:
            return
        pid = str(pm.active_profile_id or "default")
        dom = _clean_domain(domain or url)
        ev_ts = float(ts if ts is not None else time.time())
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)[:2000]
        try:
            with self.runtime.store_lock:
                ensure_skills_tables_on_conn(self.runtime.store.db)
                self.runtime.store.db.execute(
                    """
                    INSERT INTO satz_behavior_events (profile_id, event_type, domain, url, query, metadata_json, ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (pid, ev_type, dom, (url or "")[:400], (query or "")[:400], meta_json, ev_ts),
                )
                self.runtime.store.db.commit()
        except Exception:
            pass

    def list_proposals(self, include_resolved: bool = False) -> list[dict[str, Any]]:
        pm = getattr(self.runtime, "passwords", None)
        if pm is None or not pm.unlocked:
            return []
        with self.runtime.store_lock:
            ensure_skills_tables_on_conn(self.runtime.store.db)
            sql = "SELECT proposal_id, pattern_key, status, skill_json, reason, confidence, created_at, updated_at FROM satz_skill_proposals"
            if not include_resolved:
                sql += " WHERE status = 'pending'"
            sql += " ORDER BY updated_at DESC LIMIT 40"
            rows = self.runtime.store.db.execute(sql).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            try:
                sk = json.loads(r["skill_json"])
            except Exception:
                sk = {}
            out.append(
                {
                    "proposal_id": r["proposal_id"],
                    "pattern_key": r["pattern_key"],
                    "status": r["status"],
                    "skill": sk,
                    "reason": r["reason"],
                    "confidence": float(r["confidence"] or 0.75),
                    "created_at": float(r["created_at"] or 0.0),
                    "updated_at": float(r["updated_at"] or 0.0),
                }
            )
        return out

    def _upsert_proposal(self, pattern_key: str, skill: dict[str, Any], reason: str, confidence: float) -> dict[str, Any] | None:
        ordered_steps, gate_steps = validate_skill_step_graph(
            skill.get("step_graph") or [],
            skill.get("send_gate_steps"),
        )
        skill = {
            "name": str(skill["name"]),
            "trigger_examples": list(skill.get("trigger_examples") or []),
            "required_context": list(skill.get("required_context") or []),
            "step_graph": ordered_steps,
            "send_gate_steps": gate_steps,
            "domain_recipes": list(skill.get("domain_recipes") or []),
            "last_success_at": str(skill.get("last_success_at") or ""),
            "summary": str(skill.get("summary") or reason),
        }
        from satz_evals import run_skill_redteam_gate

        rt_res = run_skill_redteam_gate(skill, runtime=self.runtime)
        skill["redteam"] = rt_res
        if not rt_res.get("passed"):
            return None
        now = time.time()
        with self.runtime.store_lock:
            ensure_skills_tables_on_conn(self.runtime.store.db)
            existing = self.runtime.store.db.execute(
                "SELECT proposal_id, status FROM satz_skill_proposals WHERE pattern_key = ?",
                (pattern_key,),
            ).fetchone()
            if existing and existing["status"] in ("rejected", "accepted"):
                return None
            if existing:
                pid = str(existing["proposal_id"])
                self.runtime.store.db.execute(
                    """
                    UPDATE satz_skill_proposals
                    SET skill_json = ?, reason = ?, confidence = ?, updated_at = ?
                    WHERE proposal_id = ?
                    """,
                    (json.dumps(skill, ensure_ascii=False), reason, confidence, now, pid),
                )
            else:
                pid = f"skillprop-{secrets.token_hex(5)}"
                self.runtime.store.db.execute(
                    """
                    INSERT INTO satz_skill_proposals
                      (proposal_id, pattern_key, status, skill_json, reason, confidence, created_at, updated_at)
                    VALUES (?, ?, 'pending', ?, ?, ?, ?, ?)
                    """,
                    (pid, pattern_key, json.dumps(skill, ensure_ascii=False), reason, confidence, now, now),
                )
            self.runtime.store.db.commit()
        return {
            "proposal_id": pid,
            "pattern_key": pattern_key,
            "status": "pending",
            "skill": skill,
            "reason": reason,
            "confidence": confidence,
        }

    def accept_proposal(self, proposal_id: str) -> dict[str, Any]:
        pm = getattr(self.runtime, "passwords", None)
        if pm is None or not pm.unlocked or getattr(self.runtime.brain, "locked", True):
            raise PermissionError("Unlock a profile before saving Skills to your Brain.")
        with self.runtime.store_lock:
            ensure_skills_tables_on_conn(self.runtime.store.db)
            row = self.runtime.store.db.execute(
                "SELECT proposal_id, skill_json, status FROM satz_skill_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if not row:
                raise KeyError(f"Skill proposal '{proposal_id}' not found.")
            skill = json.loads(row["skill_json"])

        from satz_evals import run_skill_redteam_gate

        rt_res = run_skill_redteam_gate(skill, runtime=self.runtime)
        if not rt_res.get("passed"):
            fail_msg = "; ".join(f["reason"] for f in (rt_res.get("failures") or [])) or rt_res.get("summary", "Red-team gate failed")
            raise ValueError(f"Blocked by prompt-injection red-team gate: {fail_msg}")

        with self.runtime.store_lock:
            self.runtime.store.db.execute(
                "UPDATE satz_skill_proposals SET status = 'accepted', updated_at = ? WHERE proposal_id = ?",
                (time.time(), proposal_id),
            )
            self.runtime.store.db.commit()

        ent = save_skill_to_brain(self.runtime, skill, actor="skill/proposal_accept", _redteam_report=rt_res)
        return {"ok": True, "proposal_id": proposal_id, "skill": ent, "redteam": rt_res}

    def reject_proposal(self, proposal_id: str) -> dict[str, Any]:
        with self.runtime.store_lock:
            ensure_skills_tables_on_conn(self.runtime.store.db)
            self.runtime.store.db.execute(
                "UPDATE satz_skill_proposals SET status = 'rejected', updated_at = ? WHERE proposal_id = ?",
                (time.time(), proposal_id),
            )
            self.runtime.store.db.commit()
        return {"ok": True, "proposal_id": proposal_id, "status": "rejected"}

    def mine_proposals(self, *, min_interval_secs: float = 0.0) -> list[dict[str, Any]]:
        """
        Mines recent behavioral traces across mail, tabs, news, compare, codes,
        and actor actions into declarative Skill proposals.
        """
        pm = getattr(self.runtime, "passwords", None)
        if pm is None or not pm.unlocked:
            return []
        now = time.time()
        if min_interval_secs > 0.0 and (now - self._last_mine_ts) < min_interval_secs:
            return []
        self._last_mine_ts = now

        pid = str(pm.active_profile_id or "default")
        with self.runtime.store_lock:
            ensure_skills_tables_on_conn(self.runtime.store.db)
            rows = self.runtime.store.db.execute(
                """
                SELECT event_type, domain, url, query, metadata_json, ts
                FROM satz_behavior_events
                WHERE profile_id = ? AND ts >= ?
                ORDER BY ts ASC
                LIMIT 1000
                """,
                (pid, now - 45 * 86400.0),
            ).fetchall()

        events: list[dict[str, Any]] = []
        for r in rows:
            try:
                meta = json.loads(r["metadata_json"] or "{}")
            except Exception:
                meta = {}
            events.append(
                {
                    "event_type": str(r["event_type"] or ""),
                    "domain": str(r["domain"] or ""),
                    "url": str(r["url"] or ""),
                    "query": str(r["query"] or ""),
                    "meta": meta if isinstance(meta, dict) else {},
                    "ts": float(r["ts"] or 0.0),
                }
            )

        if not events:
            return []

        created: list[dict[str, Any]] = []

        # Pattern 1: Recurring Triage Routine (invoices / mail + news + packages/brain)
        # Cluster events into 4-hour sessions; count sessions or prompts exhibiting triage signals
        monday_triage_sessions: set[str] = set()
        triage_sessions_all: set[str] = set()
        triage_signals_seen: set[str] = set()
        for ev in events:
            q_low = (ev["query"] or "").lower()
            et = ev["event_type"]
            sess_key = time.strftime("%Y-%m-%d", time.gmtime(ev["ts"])) + f"-{int((ev['ts'] % 86400) // 14400)}"
            is_invoice_mail = (et in ("mail_search", "chat_prompt") and any(k in q_low for k in ("invoice", "rechnung", "unpaid", "bill", "payment")))
            is_news_sig = (et in ("news_briefing", "chat_prompt") and any(k in q_low for k in ("news", "energy", "energie", "briefing", "headline", "stories")))
            is_package_sig = (et in ("mail_search", "chat_prompt") and any(k in q_low for k in ("package", "delivery", "parcel", "paket", "tracking", "ship")))
            if is_invoice_mail or is_news_sig or is_package_sig:
                triage_sessions_all.add(sess_key)
                if is_invoice_mail:
                    triage_signals_seen.add("invoices")
                if is_news_sig:
                    triage_signals_seen.add("news")
                if is_package_sig:
                    triage_signals_seen.add("deliveries")
                try:
                    dt = datetime.fromtimestamp(ev["ts"])
                    if dt.weekday() == 0:
                        monday_triage_sessions.add(sess_key)
                except Exception:
                    pass

        if len(triage_signals_seen) >= 2 and (len(monday_triage_sessions) >= 2 or len(triage_sessions_all) >= 2):
            is_monday = len(monday_triage_sessions) >= 2
            skill_name = "Monday Briefing" if is_monday else "Recurring Triage Briefing"
            trigs = (
                ["monday briefing", "start my week", "unpaid invoices news deliveries"]
                if is_monday
                else ["morning briefing", "triage invoices news deliveries"]
            )
            prop = self._upsert_proposal(
                "pattern:recurring_triage_briefing",
                {
                    "name": skill_name,
                    "trigger_examples": trigs,
                    "required_context": ["mail_accounts", "brain", "news_feeds"],
                    "summary": "Combines unpaid invoice search, top news digest, and delivery tracking from Brain & Mail.",
                    "step_graph": [
                        {
                            "id": "invoices",
                            "primitive": "search_mail",
                            "args": {"query": "unpaid invoice bill due", "limit": 8},
                            "summary": "Find unpaid invoices and bills in Mail",
                        },
                        {
                            "id": "news",
                            "primitive": "news_digest",
                            "args": {"query": "energy headlines today", "limit": 8},
                            "summary": "Fetch top synced news briefing",
                        },
                        {
                            "id": "deliveries",
                            "primitive": "search_brain",
                            "args": {"query": "package delivery tracking order", "limit": 6},
                            "summary": "Check active deliveries and orders in Brain",
                        },
                    ],
                    "send_gate_steps": [],
                    "domain_recipes": [],
                },
                reason=f"Detected {len(triage_sessions_all)} recurring sessions checking {', '.join(sorted(triage_signals_seen))}.",
                confidence=0.88 if is_monday else 0.78,
            )
            if prop:
                created.append(prop)

        # Pattern 2: Cross-Tab Shopping Habit (open >= 2-3 tabs + codes check + compare_run)
        compare_hits = [ev for ev in events if ev["event_type"] == "compare_run"]
        codes_hits = [ev for ev in events if ev["event_type"] == "codes_check"]
        tab_hits = [ev for ev in events if ev["event_type"] in ("tab_open", "tab_capture")]
        shopping_sessions = 0
        shop_domains: list[str] = []
        for cmp_ev in compare_hits:
            t_cmp = cmp_ev["ts"]
            nearby_tabs = [t for t in tab_hits if 0 <= (t_cmp - t["ts"]) <= 1800]
            nearby_codes = [c for c in codes_hits if abs(t_cmp - c["ts"]) <= 1800]
            if len(nearby_tabs) >= 2 and len(nearby_codes) >= 1:
                shopping_sessions += 1
                for nt in nearby_tabs:
                    if nt["domain"] and nt["domain"] not in shop_domains:
                        shop_domains.append(nt["domain"])
        if shopping_sessions >= 2:
            recipes = self.runtime.recipes.list_recipes(limit=10)
            matched_recs = [
                {"domain": r["domain"], "control_key": r["control_key"], "selector": r["selector"], "label": r["label"]}
                for r in recipes
                if r["domain"] in shop_domains
            ]
            prop = self._upsert_proposal(
                "pattern:cross_tab_deal_compare",
                {
                    "name": "Deal Check + Compare",
                    "trigger_examples": ["check codes and compare", "deal check compare tabs", "compare open products"],
                    "required_context": ["open_tabs", "mail_promos"],
                    "summary": "Checks extracted promo codes for open shopping tabs and runs Compare View synthesis.",
                    "step_graph": [
                        {
                            "id": "codes",
                            "primitive": "list_codes",
                            "args": {"domain": ""},
                            "summary": "Check matching promo codes from Mail",
                        },
                        {
                            "id": "capture",
                            "primitive": "capture_tab",
                            "args": {},
                            "depends_on": ["codes"],
                            "summary": "Capture current open tabs",
                        },
                        {
                            "id": "compare",
                            "primitive": "run_comparer",
                            "args": {"goal": "Compare price, specs, shipping, and active promo codes"},
                            "depends_on": ["capture"],
                            "summary": "Run structured side-by-side comparison",
                        },
                    ],
                    "send_gate_steps": [],
                    "domain_recipes": matched_recs,
                },
                reason=f"Observed {shopping_sessions} cross-tab shopping flows checking promo codes and running Compare.",
                confidence=0.86,
            )
            if prop:
                created.append(prop)

        # Pattern 3: Domain Unsubscribe / Archiving (>= 2 unsubscribe or hide_sender actions for sender/domain pattern)
        sender_counts: dict[str, int] = {}
        for ev in events:
            if ev["event_type"] not in ("mail_unsubscribe", "mail_hide_sender", "browser_unsubscribe"):
                continue
            sender = str(ev["meta"].get("sender") or ev["query"] or ev["domain"] or "").strip().lower()
            dom_key = sender.split("@", 1)[1] if "@" in sender else _clean_domain(sender)
            pat_key = sender or dom_key
            if not pat_key:
                continue
            sender_counts[pat_key] = sender_counts.get(pat_key, 0) + 1
            if dom_key and dom_key != pat_key:
                sender_counts[dom_key] = sender_counts.get(dom_key, 0) + 1

        for sender_pat, cnt in sorted(sender_counts.items(), key=lambda kv: kv[1], reverse=True):
            if cnt < 2:
                continue
            recipes = self.runtime.recipes.list_recipes(domain=sender_pat, limit=2)
            prop = self._upsert_proposal(
                f"pattern:auto_triage:{sender_pat}",
                {
                    "name": f"Auto-triage Promos ({sender_pat})",
                    "trigger_examples": [f"clean up {sender_pat}", f"unsubscribe and archive {sender_pat}"],
                    "required_context": ["mail_accounts", "confirm_token"],
                    "summary": f"Finds promos from {sender_pat} and prepares gated unsubscribe + sender archiving.",
                    "step_graph": [
                        {
                            "id": "find_promos",
                            "primitive": "search_mail",
                            "args": {"query": sender_pat, "limit": 5},
                            "summary": f"Locate emails from {sender_pat}",
                        },
                        {
                            "id": "unsubscribe",
                            "primitive": "mail_unsubscribe",
                            "args": {"sender": sender_pat, "query": sender_pat},
                            "depends_on": ["find_promos"],
                            "send_gate": True,
                            "summary": f"Unsubscribe from {sender_pat} (send_gate)",
                        },
                        {
                            "id": "archive_sender",
                            "primitive": "hide_sender",
                            "args": {"sender": sender_pat},
                            "depends_on": ["unsubscribe"],
                            "send_gate": True,
                            "summary": f"Archive promos from {sender_pat} (send_gate)",
                        },
                    ],
                    "send_gate_steps": ["unsubscribe", "archive_sender"],
                    "domain_recipes": recipes,
                },
                reason=f"Triggered unsubscribe/archiving on '{sender_pat}' {cnt} times.",
                confidence=0.84,
            )
            if prop:
                created.append(prop)

        self.mine_provider_suggestions(min_interval_secs=0.0)
        return created

    def mine_provider_suggestions(self, *, min_interval_secs: float = 0.0) -> list[dict[str, Any]]:
        """Detects recurring vertical domain affinity in behavior logs and creates non-intrusive provider suggestions."""
        pm = getattr(self.runtime, "passwords", None)
        prov_mgr = getattr(self.runtime, "providers", None)
        if pm is None or not pm.unlocked or prov_mgr is None or getattr(self.runtime, "pause_learning", False):
            return []
        now = time.time()
        last_ps = float(getattr(self, "_last_prov_mine_ts", 0.0) or 0.0)
        if min_interval_secs > 0.0 and (now - last_ps) < min_interval_secs:
            return []
        self._last_prov_mine_ts = now

        from satz_providers import CATEGORY_INTENT_KEYWORDS, find_preset_match

        pid = str(pm.active_profile_id or "default")
        with self.runtime.store_lock:
            ensure_skills_tables_on_conn(self.runtime.store.db)
            rows = self.runtime.store.db.execute(
                """
                SELECT domain, query
                FROM satz_behavior_events
                WHERE profile_id = ? AND ts >= ? AND LENGTH(TRIM(domain)) > 0
                ORDER BY ts DESC
                LIMIT 600
                """,
                (pid, now - 45 * 86400.0),
            ).fetchall()

        domain_counts: dict[str, int] = {}
        domain_queries: dict[str, list[str]] = {}
        for r in rows:
            d = _clean_domain(str(r["domain"] or ""))
            if not d:
                continue
            domain_counts[d] = domain_counts.get(d, 0) + 1
            q = str(r["query"] or "").strip().lower()
            if q:
                domain_queries.setdefault(d, []).append(q)

        suggested: list[dict[str, Any]] = []
        for dom, cnt in sorted(domain_counts.items(), key=lambda item: -item[1]):
            if cnt < 3:
                continue
            preset = find_preset_match(dom)
            cid = str((preset or {}).get("suggested_category_id") or "")
            if not cid:
                hay = " ".join(domain_queries.get(dom, []))
                best_sc = 0
                for cand_cid, kws in CATEGORY_INTENT_KEYWORDS.items():
                    sc = sum(1 for kw in kws if kw in hay)
                    if sc > best_sc:
                        best_sc = sc
                        cid = cand_cid
            if not cid:
                continue
            sug = prov_mgr.upsert_suggestion(
                category_id=cid,
                domain=dom,
                display_name=str((preset or {}).get("display_name") or ""),
                reason=f"Visited/used {dom} {cnt} times in recent sessions.",
                evidence_count=cnt,
            )
            if sug:
                suggested.append(sug)
            if len(suggested) >= 4:
                break
        return suggested


def save_skill_to_brain(
    runtime: Any,
    skill: dict[str, Any],
    *,
    actor: str = "skill/builder",
    _redteam_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validates, red-team checks, and persists a procedural Skill as `Skills/*.md` inside SatzBrain."""
    if getattr(runtime, "brain", None) is None or runtime.brain.locked:
        raise PermissionError("Unlock a profile to save Skills to your Brain.")

    name = str(skill.get("name") or "").strip() or "Saved Workflow Skill"
    ordered_steps, gate_steps = validate_skill_step_graph(
        skill.get("step_graph") or [],
        skill.get("send_gate_steps"),
    )
    triggers = [str(t).strip() for t in (skill.get("trigger_examples") or [name.lower()]) if str(t).strip()][:8]
    req_ctx = [str(c).strip() for c in (skill.get("required_context") or []) if str(c).strip()][:8]
    dom_recipes = [r for r in (skill.get("domain_recipes") or []) if isinstance(r, dict)][:12]
    last_ok = str(skill.get("last_success_at") or "").strip()
    summary = str(skill.get("summary") or f"Declarative skill ({len(ordered_steps)} step(s))").strip()

    rt_res = _redteam_report
    if rt_res is None:
        from satz_evals import run_skill_redteam_gate

        rt_res = run_skill_redteam_gate(
            {
                "name": name,
                "summary": summary,
                "trigger_examples": triggers,
                "required_context": req_ctx,
                "step_graph": ordered_steps,
                "send_gate_steps": gate_steps,
                "domain_recipes": dom_recipes,
            },
            runtime=runtime,
        )
    if not rt_res.get("passed"):
        fail_msg = "; ".join(f["reason"] for f in (rt_res.get("failures") or [])) or rt_res.get("summary", "Red-team gate failed")
        raise ValueError(f"Blocked by prompt-injection red-team gate: {fail_msg}")

    content_lines = [
        f"Summary: {summary}",
        "",
        "## Declarative Step Graph",
    ]
    for st in ordered_steps:
        gate_note = " [send_gate]" if st.get("send_gate") else ""
        deps_note = f" (after {', '.join(st['depends_on'])})" if st.get("depends_on") else ""
        content_lines.append(
            f"- `{st['id']}` · **{st['primitive']}**{gate_note}{deps_note}: {st['summary']} `args={json.dumps(st['args'], ensure_ascii=False)}`"
        )

    attrs: dict[str, Any] = {
        "name": name,
        "trigger_examples": triggers,
        "required_context": req_ctx,
        "step_graph": ordered_steps,
        "send_gate_steps": gate_steps,
        "domain_recipes": dom_recipes,
        "last_success_at": last_ok,
        "redteam_passed": bool(rt_res.get("passed")),
        "redteam_checked_at": str(rt_res.get("checked_at") or _utc_iso()),
        "redteam_cases_run": int(rt_res.get("cases_run") or 0),
        "redteam_summary": str(rt_res.get("summary") or ""),
    }
    return runtime.brain.upsert_entity(
        entity_type="skill",
        name=name,
        summary=summary,
        attributes=attrs,
        content="\n".join(content_lines),
        aliases=triggers,
        tier=1,
        actor=actor,
    )


def build_skill_from_task_or_turn(
    runtime: Any,
    *,
    conversation_id: str = "default",
    task_id: str = "",
    name: str = "",
    user_prompt: str = "",
    assistant_text: str = "",
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Crystallizes an explicit completed AgentTaskCard or multi-step turn into a Brain Skill."""
    steps: list[dict[str, Any]] = []
    req_ctx: list[str] = []
    triggers: list[str] = []
    doms: list[str] = []

    task_obj = None
    if task_id:
        with runtime.tasks_lock:
            task_obj = runtime.tasks.get(task_id)

    if task_obj is not None:
        goal = str(task_obj.get("goal") or user_prompt or "Saved Task Workflow").strip()
        if goal:
            triggers.append(goal[:120])
        agent = str(task_obj.get("agent") or "").lower()
        t_steps = list(task_obj.get("steps") or [])

        idx = 1
        for ts in t_steps:
            kind = str(ts.get("kind") or "")
            ap = ts.get("action_payload") if isinstance(ts.get("action_payload"), dict) else {}
            atype = str(ap.get("action_type") or "").lower()
            if kind == "send_gate" and atype in ("mail_unsubscribe", "browser_unsubscribe"):
                sender = str(ap.get("sender") or ap.get("sender_name") or "").strip()
                steps.append(
                    {
                        "id": f"step_{idx}",
                        "primitive": "mail_unsubscribe",
                        "args": {"sender": sender, "query": sender, "message_id": str(ap.get("message_id") or "")},
                        "send_gate": True,
                        "summary": str(ts.get("action_summary") or f"Unsubscribe {sender}"),
                    }
                )
                idx += 1
            elif kind == "send_gate" and atype == "mail_hide_sender":
                sender = str(ap.get("sender") or "").strip()
                steps.append(
                    {
                        "id": f"step_{idx}",
                        "primitive": "hide_sender",
                        "args": {"sender": sender},
                        "send_gate": True,
                        "summary": f"Archive emails from {sender}",
                    }
                )
                idx += 1
            elif kind == "send_gate" and atype == "compare_tabs":
                steps.append(
                    {
                        "id": f"step_{idx}",
                        "primitive": "run_comparer",
                        "args": {"goal": str(ap.get("goal") or goal)},
                        "summary": f"Compare tabs: {goal[:60]}",
                    }
                )
                idx += 1
            elif kind == "send_gate" and atype == "add_watch":
                steps.append(
                    {
                        "id": f"step_{idx}",
                        "primitive": "add_watch",
                        "args": {"query_or_url": str(ap.get("query_or_url") or "")},
                        "send_gate": True,
                        "summary": "Create background Watch",
                    }
                )
                idx += 1
            elif kind == "send_gate" and atype == "actor_click_control":
                u = str(ap.get("url") or "")
                dom = _clean_domain(u)
                if dom:
                    doms.append(dom)
                steps.append(
                    {
                        "id": f"step_{idx}",
                        "primitive": "actor_click_control",
                        "args": {
                            "url": u,
                            "selector": str(ap.get("selector") or ""),
                            "label": str(ap.get("label") or ""),
                        },
                        "send_gate": True,
                        "summary": str(ts.get("action_summary") or "Click site control"),
                    }
                )
                idx += 1

        if not steps and "compar" in (agent + " " + goal).lower():
            steps.append(
                {
                    "id": "step_1",
                    "primitive": "run_comparer",
                    "args": {"goal": goal},
                    "summary": "Run side-by-side comparison",
                }
            )
        if not name:
            name = goal[:60]

    # Multi-step chat turn extraction fallback / augmentation
    if not steps:
        q_clean = (user_prompt or "").strip()
        if q_clean:
            triggers.append(q_clean[:120])
        src_list = list(sources or [])
        mail_srcs = [s for s in src_list if str(s.get("id") or "").startswith("mail:") or "satzmail://" in str(s.get("url") or "")]
        web_srcs = [s for s in src_list if str(s.get("url") or "").startswith(("http://", "https://"))]
        for ws in web_srcs:
            d = _clean_domain(str(ws.get("url") or ""))
            if d and d not in doms:
                doms.append(d)

        q_low = q_clean.lower()
        if mail_srcs or any(k in q_low for k in ("mail", "email", "inbox", "invoice", "order", "promo")):
            req_ctx.append("mail_accounts")
            steps.append(
                {
                    "id": f"step_{len(steps) + 1}",
                    "primitive": "search_mail",
                    "args": {"query": q_clean[:100] or "inbox", "limit": 6},
                    "summary": "Search relevant mail",
                }
            )
        if any(k in q_low for k in ("news", "headline", "briefing", "energy")):
            req_ctx.append("news_feeds")
            steps.append(
                {
                    "id": f"step_{len(steps) + 1}",
                    "primitive": "news_digest",
                    "args": {"query": q_clean[:100], "limit": 6},
                    "summary": "Check synced news digest",
                }
            )
        if web_srcs or "web" in q_low or "search" in q_low:
            req_ctx.append("open_tabs")
            steps.append(
                {
                    "id": f"step_{len(steps) + 1}",
                    "primitive": "web_search",
                    "args": {"query": q_clean[:100], "max_results": 4},
                    "summary": "Search web for fresh context",
                }
            )
        if any(k in q_low for k in ("compare", "vs", "difference")):
            steps.append(
                {
                    "id": f"step_{len(steps) + 1}",
                    "primitive": "run_comparer",
                    "args": {"goal": q_clean[:120] or "Compare sources"},
                    "depends_on": [steps[-1]["id"]] if steps else [],
                    "summary": "Compare collected sources",
                }
            )
        if not steps:
            req_ctx.append("brain")
            steps.append(
                {
                    "id": "step_1",
                    "primitive": "search_brain",
                    "args": {"query": q_clean[:100] or name or "notes", "limit": 6},
                    "summary": "Search Satz Brain knowledge graph",
                }
            )
        if not name:
            name = (q_clean or "Custom Workflow Skill")[:60]

    # Attach any cached domain recipes for domains involved
    dom_recipes: list[dict[str, Any]] = []
    if hasattr(runtime, "recipes"):
        for d in doms[:4]:
            dom_recipes.extend(runtime.recipes.list_recipes(domain=d, limit=2))

    # Chain linear dependencies if none set
    for i in range(1, len(steps)):
        if not steps[i].get("depends_on"):
            steps[i]["depends_on"] = [steps[i - 1]["id"]]

    return save_skill_to_brain(
        runtime,
        {
            "name": name,
            "trigger_examples": list(dict.fromkeys(triggers or [name.lower()])),
            "required_context": list(dict.fromkeys(req_ctx)),
            "step_graph": steps,
            "domain_recipes": dom_recipes,
            "last_success_at": _utc_iso(),
            "summary": f"Saved workflow skill from {'task' if task_obj else 'conversation turn'}: {name}",
        },
        actor="user/save_as_skill",
    )


class SkillRunner:
    """
    Executes declarative Brain Skills via `AgentTaskCard`s.
    Automatically runs read-only primitives and ALWAYS pauses on `MUTATING_PRIMITIVES`
    with a single-use `send_gate` `confirm_token`.
    """

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self._active_runs: dict[str, dict[str, Any]] = {}

    def _load_skill_by_slug(self, slug_or_name: str) -> dict[str, Any]:
        if getattr(self.runtime, "brain", None) is None or self.runtime.brain.locked:
            raise PermissionError("Unlock a profile to run Skills from your Brain.")
        target = (slug_or_name or "").strip().lower()
        for ent in self.runtime.brain.list_entities():
            if str(ent.get("type") or "").lower() != "skill":
                continue
            if str(ent.get("slug") or "").lower() == target or str(ent.get("name") or "").lower() == target:
                brain_dir = getattr(self.runtime.brain, "brain_dir", None)
                rel_path = ent.get("path")
                if brain_dir and rel_path and hasattr(self.runtime.brain, "_parse_entity_file"):
                    from pathlib import Path

                    fm, _ = self.runtime.brain._parse_entity_file(Path(brain_dir) / str(rel_path))
                    if isinstance(fm, dict) and fm:
                        merged_attrs = dict(ent.get("attributes") or {})
                        if isinstance(fm.get("attributes"), dict):
                            merged_attrs.update(fm["attributes"])
                        for k in ("trigger_examples", "required_context", "step_graph", "send_gate_steps", "domain_recipes"):
                            if k in fm:
                                merged_attrs[k] = fm[k]
                        ent = {
                            **ent,
                            "name": str(fm.get("name") or ent.get("name") or ""),
                            "summary": str(fm.get("summary") or ent.get("summary") or ""),
                            "attributes": merged_attrs,
                        }
                return ent
        raise KeyError(f"Skill '{slug_or_name}' not found.")

    def _run_read_primitive(self, primitive: str, args: dict[str, Any], cid: str) -> dict[str, Any]:
        if primitive == "search_mail":
            if getattr(self.runtime, "mail", None) is None or not self.runtime.passwords.unlocked:
                return {"ok": False, "rows": [], "error": "Mail unavailable or profile locked."}
            res = self.runtime.mail.search_messages(str(args.get("query") or ""), limit=int(args.get("limit") or 6))
            rows = res.get("rows") or []
            return {"ok": True, "count": len(rows), "summary": f"{len(rows)} mail hit(s)", "rows": rows[:6]}

        if primitive == "read_message":
            if getattr(self.runtime, "mail", None) is None or not self.runtime.passwords.unlocked:
                return {"ok": False, "error": "Mail unavailable."}
            det = self.runtime.mail.get_message_detail(str(args.get("message_id") or ""))
            msg = det.get("message") or {}
            return {"ok": bool(msg), "subject": msg.get("subject") or "", "summary": str(msg.get("snippet") or "")[:200]}

        if primitive == "search_brain":
            res = self.runtime.search_brain(str(args.get("query") or ""), limit=int(args.get("limit") or 6))
            ents = res.get("entities") or []
            return {"ok": True, "count": len(ents), "summary": f"{len(ents)} Brain entity hit(s)", "entities": ents[:6]}

        if primitive == "news_digest":
            if getattr(self.runtime, "news", None) is None:
                return {"ok": False, "error": "News engine unavailable."}
            st = self.runtime.news.get_stories(lane="stories")
            stories = list(st.get("stories") or [])
            q_toks = [t.lower() for t in re.findall(r"[a-z0-9äöüß]{3,}", str(args.get("query") or ""))]
            if q_toks:
                filtered = [
                    s for s in stories
                    if any(tok in f"{s.get('headline','')} {s.get('summary','')}".lower() for tok in q_toks)
                ]
                if filtered:
                    stories = filtered
            lim = int(args.get("limit") or 6)
            return {"ok": True, "count": len(stories[:lim]), "summary": f"{len(stories[:lim])} news stories", "stories": stories[:lim]}

        if primitive == "list_codes":
            if getattr(self.runtime, "mail", None) is None or not self.runtime.passwords.unlocked:
                return {"ok": True, "codes": [], "summary": "0 promo codes (mail locked)"}
            codes = self.runtime.mail.get_active_codes_for_domain(str(args.get("domain") or ""))
            return {"ok": True, "count": len(codes), "summary": f"{len(codes)} active promo code(s)", "codes": codes[:10]}

        if primitive == "capture_tab":
            with self.runtime.store_lock:
                rows = self.runtime.store.db.execute(
                    "SELECT source_id, url, title FROM satz_sources WHERE conversation_id = ? ORDER BY updated_at DESC LIMIT 6",
                    (cid,),
                ).fetchall()
            tabs = [dict(r) for r in rows]
            return {"ok": True, "count": len(tabs), "summary": f"Captured {len(tabs)} source(s)", "sources": tabs}

        if primitive == "open_tab":
            u = str(args.get("url") or "").strip()
            return {"ok": bool(u), "open_url": u, "summary": f"Open tab: {u}" if u else "No URL"}

        if primitive == "web_search":
            from satz_web_harness import WebSearchSessionHarness

            q = str(args.get("query") or "").strip()
            h = WebSearchSessionHarness(
                self.runtime,
                combined_sources=[],
                hydrated_sources=[],
                used_source_ids=[],
                cited_web_sources=[],
                source_stats_list=[],
                conversation_id=cid,
            )
            res = h.execute_web_search(q, max_results=int(args.get("max_results") or 4))
            return {"ok": bool(res.get("ok")), "count": len(res.get("results") or []), "summary": f"{len(res.get('results') or [])} web hit(s)", "results": res.get("results") or []}

        if primitive == "run_comparer":
            res = self.runtime.run_comparer(cid, goal=str(args.get("goal") or "compare these"))
            return {"ok": bool(res.get("ok")), "summary": "Comparison table generated", "markdown": res.get("markdown") or ""}

        return {"ok": False, "error": f"Unknown read primitive: {primitive}"}

    def _run_mutating_primitive(self, primitive: str, args: dict[str, Any], cid: str, task_id: str, step_id: str) -> dict[str, Any]:
        if primitive == "hide_sender":
            res = self.runtime.mail.hide_sender_messages(str(args.get("sender") or ""))
            return {"ok": bool(res.get("ok")), "summary": f"Archived {res.get('hidden_count', 0)} email(s)", **res}

        if primitive == "mail_unsubscribe":
            prep = self.runtime.prepare_mail_unsubscribe_task(
                conversation_id=cid,
                target_query=str(args.get("sender") or args.get("query") or ""),
                message_id=str(args.get("message_id") or ""),
            )
            if not prep.get("ok"):
                return {"ok": False, "summary": prep.get("error") or "No matching unsubscribe email found", **prep}
            ap = next((s.get("action_payload") or {} for s in (prep.get("task") or {}).get("steps") or [] if s.get("kind") == "send_gate"), {})
            mid = str(ap.get("message_id") or "")
            url = str(ap.get("url") or "")
            if mid:
                ex = self.runtime.execute_mail_unsubscribe_task(
                    message_id=mid,
                    url=url,
                    method_type=str(ap.get("preferred_method") or ""),
                    task_id=task_id,
                    step_id=step_id,
                )
                return {"ok": bool(ex.get("ok")), "summary": f"Unsubscribe executed via {ex.get('method') or 'browser'}", **ex}
            return {"ok": True, "summary": "Unsubscribe prepared", **prep}

        if primitive == "add_watch":
            res = self.runtime.add_watch(
                conversation_id=cid,
                query_or_url=str(args.get("query_or_url") or ""),
                cadence_seconds=float(args.get("cadence_seconds") or 1800.0),
                condition=str(args.get("condition") or "any_change"),
                title=str(args.get("title") or ""),
                task_id=task_id,
                step_id=step_id,
            )
            return {"ok": bool(res.get("ok")), "summary": "Added background Watch", **res}

        if primitive == "brain_store":
            ent = self.runtime.brain.upsert_entity(
                entity_type=str(args.get("entity_type") or "note"),
                name=str(args.get("name") or "Skill Note"),
                summary=str(args.get("summary") or ""),
                tier=1,
                actor="skill/runner",
            )
            return {"ok": True, "summary": f"Stored '{ent.get('name')}' to Brain", "entity": ent}

        if primitive == "draft_mail":
            return {
                "ok": True,
                "summary": f"Drafted email to {args.get('to') or '(recipient)'}",
                "draft": {"to": str(args.get("to") or ""), "subject": str(args.get("subject") or ""), "body": str(args.get("body") or "")},
            }

        if primitive == "actor_click_control":
            dom = _clean_domain(str(args.get("url") or ""))
            rec = self.runtime.recipes.get_best_recipe(dom) if dom else None
            sel = str(args.get("selector") or (rec or {}).get("selector") or "")
            lbl = str(args.get("label") or (rec or {}).get("label") or "")
            return {
                "ok": True,
                "needs_frontend_actor": True,
                "action_type": "actor_click_control",
                "url": str(args.get("url") or (rec or {}).get("sample_url") or ""),
                "selector": sel,
                "label": lbl,
                "summary": f"Ready to click '{lbl or sel}' on {dom}",
            }

        return {"ok": False, "error": f"Unknown mutating primitive: {primitive}"}

    def start_skill(self, slug_or_name: str, conversation_id: str = "default", *, _redteam_dryrun: bool = False) -> dict[str, Any]:
        ent = self._load_skill_by_slug(slug_or_name)
        attrs = ent.get("attributes") or {}
        ordered_steps, gate_steps = validate_skill_step_graph(
            attrs.get("step_graph") or [],
            attrs.get("send_gate_steps"),
        )
        if not _redteam_dryrun:
            from satz_evals import run_skill_redteam_gate

            rt_res = run_skill_redteam_gate(
                {
                    "name": ent.get("name") or slug_or_name,
                    "summary": ent.get("summary") or "",
                    "trigger_examples": attrs.get("trigger_examples") or [],
                    "step_graph": ordered_steps,
                    "send_gate_steps": gate_steps,
                    "domain_recipes": attrs.get("domain_recipes") or [],
                },
                runtime=self.runtime,
            )
            if not rt_res.get("passed"):
                fail_msg = "; ".join(f["reason"] for f in (rt_res.get("failures") or [])) or rt_res.get("summary", "Red-team gate failed")
                raise ValueError(f"Skill blocked by prompt-injection red-team gate: {fail_msg}")
        cid = str(conversation_id or "default")
        task = self.runtime.create_task(cid, goal=f"Skill: {ent['name']}", agent=f"skill:{ent['slug']}")
        tid = task["id"]
        self._active_runs[tid] = {
            "skill_slug": ent["slug"],
            "skill_name": ent["name"],
            "conversation_id": cid,
            "steps": ordered_steps,
            "cursor": 0,
            "outputs": {},
        }
        return self._advance_run(tid)

    def continue_after_confirm(
        self,
        task_id: str,
        step_id: str = "",
        confirm_token: str = "",
    ) -> dict[str, Any]:
        run_state = self._active_runs.get(task_id)
        if not run_state:
            return {"ok": False, "error": "Skill execution session not found or already finished."}
        if confirm_token:
            c_res = self.runtime.confirm_task_step(task_id, step_id, confirm_token)
            if not c_res.get("ok"):
                return c_res
        confirmed_step, gate_err = self.runtime._verify_confirmed_send_gate(task_id, step_id, mark_executed=True)
        if gate_err or not confirmed_step:
            return {"ok": False, "error": gate_err or "Send gate confirmation required."}

        idx = int(run_state.get("cursor") or 0)
        steps = run_state["steps"]
        cid = run_state["conversation_id"]
        if idx < len(steps):
            st = steps[idx]
            res = self._run_mutating_primitive(st["primitive"], st.get("args") or {}, cid, task_id, confirmed_step["id"])
            run_state["outputs"][st["id"]] = res
            self.runtime.append_task_step(
                task_id,
                f"Done · {st['summary']}: {res.get('summary') or res.get('error') or 'ok'}",
                kind="log",
            )
            run_state["cursor"] = idx + 1
        return self._advance_run(task_id)

    def _advance_run(self, task_id: str) -> dict[str, Any]:
        run_state = self._active_runs[task_id]
        steps = run_state["steps"]
        cid = run_state["conversation_id"]
        while run_state["cursor"] < len(steps):
            idx = run_state["cursor"]
            st = steps[idx]
            if st.get("mutating") or st.get("send_gate"):
                gate_summary = f"{st['summary']} ({st['primitive']})"
                updated = self.runtime.append_task_step(
                    task_id,
                    gate_summary,
                    kind="send_gate",
                    action_summary=gate_summary,
                    action_payload={
                        "action_type": "skill_continue",
                        "skill_slug": run_state["skill_slug"],
                        "primitive": st["primitive"],
                        **(st.get("args") or {}),
                    },
                )
                return {
                    "ok": True,
                    "status": "waiting_confirm",
                    "task": updated,
                    "outputs": run_state["outputs"],
                }

            out = self._run_read_primitive(st["primitive"], st.get("args") or {}, cid)
            run_state["outputs"][st["id"]] = out
            self.runtime.append_task_step(
                task_id,
                f"{st['summary']}: {out.get('summary') or 'done'}",
                kind="log",
            )
            run_state["cursor"] = idx + 1

        # All steps finished
        summary_lines = [f"**Skill completed · {run_state['skill_name']}**"]
        for st in steps:
            o = run_state["outputs"].get(st["id"]) or {}
            line = f"- **{st['summary']}**: {o.get('summary') or 'done'}"
            summary_lines.append(line)
            if o.get("markdown"):
                summary_lines.append("")
                summary_lines.append(str(o["markdown"]))
        final_task = self.runtime.complete_task(task_id, result_md="\n".join(summary_lines))

        # Update last_success_at on Skill entity
        try:
            ent = self._load_skill_by_slug(run_state["skill_slug"])
            attrs = dict(ent.get("attributes") or {})
            attrs["last_success_at"] = _utc_iso()
            save_skill_to_brain(
                self.runtime,
                {**attrs, "name": ent["name"], "summary": ent.get("summary") or ""},
                actor="skill/run_complete",
            )
        except Exception:
            pass

        self._active_runs.pop(task_id, None)
        return {
            "ok": True,
            "status": "completed",
            "task": final_task,
            "outputs": run_state["outputs"],
        }
