#!/usr/bin/env python3
"""
Satz Brain Knowledgebase Manager (PM-OS / SGS-Brain Architecture)

Implements the Brain knowledgebase management approach for the Satz browser:
1. Typed Markdown entity files with YAML frontmatter, [[wikilinks]] relationships,
   structured attributes (address, email, url, account, etc.), and $events audit log.
2. Central `registry.yaml` with slug + alias_index resolution.
3. Compressed pipe-delimited `BRAIN.md` index (Tier 1: Core Accounts, People & Places;
   Tier 2: Connected Entities, Notes & Organizations) injected directly into model context.
4. Hot-topic loader (`load_hot_entities`) that pulls full Markdown for entities matching
   the user's prompt or active browser tabs.
5. Bidirectional enrichment:
   - Passive enrichment (`enrich_from_page`) as the user browses authenticated tabs & pages.
   - Explicit model/user write harness (`<brain_store>` directives + store-intent fallback).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


ENTITY_TYPE_DIRS: dict[str, str] = {
    "person": "Entities/People",
    "place": "Entities/Places",
    "address": "Entities/Places",
    "organization": "Entities/Organizations",
    "account": "Entities/Accounts",
    "document": "Entities/Documents",
    "order": "Entities/Orders",
    "promotion": "Entities/Promotions",
    "project": "Projects",
    "note": "Notes",
    "fact": "Notes",
    "decision": "Decisions",
    "story": "News/Stories",
    "claim": "News/Claims",
    "topic": "News/Topics",
    "source": "Sources/Media",
    "skill": "Skills",
}

BOOKING_OR_TRACKING_RE = re.compile(
    r"\b(?=[A-Z0-9-]{6,22}\b)(?:[A-Z]{1,4}\d{3,}[A-Z0-9]*|\d{5,}[A-Z0-9-]*|[A-Z]{2,}-\d{3,})\b"
)
MONEY_AMOUNT_RE = re.compile(
    r"(?:€|eur|usd|\$|£|gbp|chf)\s*\d+(?:[.,]\d+)?|\b\d+(?:[.,]\d+)?\s*(?:€|eur|usd|gbp|chf)\b",
    re.IGNORECASE,
)

TIER1_TYPES = {"account", "person", "place", "address", "project", "order"}

STORE_INTENT_RE = re.compile(
    r"\b(store|save|remember|record|keep|add\s+to\s+(?:the\s+)?(?:knowledge\s*base|brain|memory)|log\s+this|note\s+down)\b",
    re.IGNORECASE,
)

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Matches common street addresses (US/UK/EU/DE styles, e.g. "123 Main St...", "Friedrichstr. 12, 10117 Berlin")
ADDRESS_LINE_RE = re.compile(
    r"(?:"
    r"\b\d{1,5}\s+[A-ZÄÖÜa-zäöüß0-9.\-'\s]{3,45}\s+"
    r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Lane|Ln\.?|Drive|Dr\.?|Way|Court|Ct\.?|Place|Pl\.?|Square|Sq\.?|Straße|Str\.?|Strasse|Platz|Allee|Weg|Gasse)\b"
    r"[^\n]{0,60}"
    r"|"
    r"\b[A-ZÄÖÜ][A-ZÄÖÜa-zäöüß\-]+(?:straße|str\.|strasse|platz|allee|weg|gasse)\s+\d{1,4}[a-zA-Z]?(?:[,\s]+\d{4,5}\s+[A-ZÄÖÜa-zäöüß\-\s]+)?"
    r")",
    re.IGNORECASE,
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_iso_from_ts(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _parse_ts(val: Any) -> float | None:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        v = float(val)
        return v if v > 1_000_000_000.0 else None
    s = str(val).strip()
    if not s:
        return None
    try:
        v = float(s)
        if v > 1_000_000_000.0:
            return v
    except ValueError:
        pass
    try:
        iso_s = s.replace("Z", "+00:00")
        if len(iso_s) == 10 and iso_s[4] == "-" and iso_s[7] == "-":
            iso_s += "T12:00:00+00:00"
        dt = datetime.fromisoformat(iso_s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _entity_event_ts(meta: dict[str, Any]) -> float:
    attrs = meta.get("attributes") or {}
    for cand in (
        attrs.get("$published_ts"),
        attrs.get("published_at"),
        attrs.get("event_time"),
        meta.get("published_at"),
        attrs.get("$synced_ts"),
        attrs.get("synced_at"),
        meta.get("synced_at"),
        meta.get("updated"),
    ):
        parsed = _parse_ts(cand)
        if parsed is not None:
            return parsed
    return 0.0


def _format_time_tag(ts: float, now_ts: float | None = None) -> str:
    if ts <= 0.0:
        return ""
    cur = float(now_ts if now_ts is not None else time.time())
    diff = max(0.0, cur - ts)
    if diff < 120.0:
        age = "just now"
    elif diff < 3600.0:
        age = f"{int(diff // 60)}m ago"
    elif diff < 48 * 3600.0:
        age = f"{int(diff // 3600)}h ago"
    else:
        age = f"{int(diff // 86400)}d ago"
    dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    return f"{dt_str} · {age}"


_NEWS_TEMPORAL_RE = re.compile(
    r"\b(news|story|stories|headline|headlines|briefing|corroborated|world\s+news|top\s+stories|happened|developments?|synced)\b",
    re.IGNORECASE,
)


def _parse_temporal_query(query: str, now_ts: float | None = None) -> dict[str, Any]:
    cur = float(now_ts if now_ts is not None else time.time())
    q = (query or "").lower()
    recency_bias = False
    start_ts: float | None = None
    end_ts: float | None = None
    label: str | None = None

    date_m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", q)
    if date_m:
        try:
            dt = datetime.strptime(date_m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            start_ts = (dt - timedelta(hours=2)).timestamp()
            end_ts = (dt + timedelta(hours=26)).timestamp()
            label = date_m.group(1)
            recency_bias = True
        except Exception:
            pass
    elif re.search(r"\b(last\s+hour|past\s+hour|this\s+hour|just\s+now)\b", q):
        start_ts = cur - 3600.0
        end_ts = cur + 600.0
        label = "last hour"
        recency_bias = True
    elif re.search(r"\byesterday\b", q):
        today_mid = datetime.fromtimestamp(cur, tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        start_ts = (today_mid - timedelta(days=1, hours=2)).timestamp()
        end_ts = (today_mid + timedelta(hours=2)).timestamp()
        label = "yesterday"
    elif re.search(r"\b(today|today's|todays|this\s+morning|tonight)\b", q):
        start_ts = cur - 86400.0
        end_ts = cur + 600.0
        label = "today"
        recency_bias = True
    elif re.search(r"\b(this\s+week|past\s+week|last\s+week|last\s+7\s+days)\b", q):
        start_ts = cur - 7 * 86400.0
        end_ts = cur + 600.0
        label = "this week"
        recency_bias = True
    elif re.search(r"\b(latest|recent|recently|newest|current|currently|breaking|fresh|update|updates|top\s+stories)\b", q):
        recency_bias = True

    is_news_query = bool(_NEWS_TEMPORAL_RE.search(q))
    if is_news_query:
        recency_bias = True

    return {
        "recency_bias": recency_bias,
        "is_news_query": is_news_query,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "label": label,
    }


def slugify(value: str) -> str:
    s = value.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:64] or "entity"


def _dump_yaml(data: dict[str, Any]) -> str:
    if HAS_YAML:
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()
    return json.dumps(data, indent=2, ensure_ascii=False)


def _load_yaml(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    if HAS_YAML:
        try:
            res = yaml.safe_load(text)
            return res if isinstance(res, dict) else {}
        except Exception:
            pass
    try:
        res = json.loads(text)
        return res if isinstance(res, dict) else {}
    except Exception:
        return {}


def neutralize_brain_directives_in_source(text: str) -> str:
    """
    Section 2.4 & Tool Read/Act Boundary: Before prompt assembly or tool return, neutralise
    directive tags inside untrusted source text (`<brain_store>`, `<tool_call>`, `<tool_result>`)
    so a page or email cannot plant one for the model to echo or trigger.
    """
    if not text:
        return ""
    out = re.sub(
        r"<\s*(/?)\s*(brain_store|tool_call|tool_result)\b([^>]*)>",
        r"‹\1\2\3›",
        text,
        flags=re.IGNORECASE,
    )
    out = out.replace("<|tool_call>", "‹|tool_call›").replace("<tool_call|>", "‹tool_call|›")
    return out


_SHARED_ENCODERS: dict[str, Any] = {}
_SHARED_ENCODER_LOCK = threading.RLock()


class SatzBrain:
    """Manages the local Satz Brain knowledge graph on disk."""

    def __init__(self, brain_dir: Path, sgs_root: Path | None = None, locked: bool = False):
        self.brain_dir = brain_dir
        self.sgs_root = sgs_root
        self.locked = bool(locked)
        self.lock = threading.RLock()
        self.registry_path = self.brain_dir / "registry.yaml"
        self.brain_md_path = self.brain_dir / "BRAIN.md"
        self.proposals: dict[str, dict[str, Any]] = {}
        self._brain_md_cache: str = ""
        self._brain_md_mtime: float = -1.0
        self._summary_cache: dict[str, Any] | None = None
        self._summary_cache_mtime: float = -1.0
        self._summary_cache_brain_mtime: float = -1.0
        self._encoder: Any = None
        self._entity_emb_cache: dict[str, tuple[str, Any]] = {}
        if not self.locked:
            self._ensure_layout()

    def prewarm_encoder(self) -> bool:
        """Warms the Brain semantic/lexical encoder in the background without blocking callers."""
        if self.locked:
            return False
        try:
            enc = self._get_encoder()
            return enc is not None
        except Exception:
            return False

    def invalidate_summary_cache(self) -> None:
        with self.lock:
            self._summary_cache = None
            self._summary_cache_mtime = -1.0
            self._summary_cache_brain_mtime = -1.0

    def get_encoder_status(self) -> dict[str, Any]:
        sgs_base = self.sgs_root or (Path(__file__).resolve().parent.parent.parent / "sgs")
        ckpt = sgs_base / "checkpoints" / "planck13" / "best.pt"
        tok = sgs_base / "data" / "wikipedia" / "tokenizer.model"
        if ckpt.exists() and tok.exists():
            return {
                "mode": "planck13",
                "state": "ready",
                "label": "brain ranking: semantic (planck13)",
            }
        return {
            "mode": "lexical",
            "state": "missing",
            "label": "brain ranking: lexical (planck13 missing)",
        }

    def _get_encoder(self) -> Any:
        if self._encoder is not None:
            return self._encoder
        with _SHARED_ENCODER_LOCK:
            if self._encoder is not None:
                return self._encoder
            try:
                from src.planck3.encoders import make_encoder

                sgs_base = self.sgs_root or (Path(__file__).resolve().parent.parent.parent / "sgs")
                ckpt = sgs_base / "checkpoints" / "planck13" / "best.pt"
                tok = sgs_base / "data" / "wikipedia" / "tokenizer.model"
                cache_key = f"{ckpt}::{tok}" if (ckpt.exists() and tok.exists()) else "hash"
                if cache_key in _SHARED_ENCODERS:
                    self._encoder = _SHARED_ENCODERS[cache_key]
                    return self._encoder
                if ckpt.exists() and tok.exists():
                    self._encoder = make_encoder(
                        "planck",
                        checkpoint=str(ckpt),
                        tokenizer=str(tok),
                        device="cpu",
                    )
                else:
                    self._encoder = make_encoder("hash")
                _SHARED_ENCODERS[cache_key] = self._encoder
            except Exception:
                try:
                    from src.planck3.encoders import make_encoder

                    self._encoder = make_encoder("hash")
                except Exception:
                    self._encoder = None
            return self._encoder

    def get_cached_brain_md(self) -> str:
        if self.locked:
            return ""
        with self.lock:
            if not self.brain_md_path.exists():
                return self.regenerate_brain_md()
            try:
                mtime = self.brain_md_path.stat().st_mtime
                if self._brain_md_cache and mtime == self._brain_md_mtime:
                    return self._brain_md_cache
                text = self.brain_md_path.read_text(encoding="utf-8")
                self._brain_md_cache = text
                self._brain_md_mtime = mtime
                return text
            except OSError:
                return self.regenerate_brain_md()

    def _ensure_layout(self) -> None:
        if self.locked:
            return
        with self.lock:
            self.brain_dir.mkdir(parents=True, exist_ok=True)
            for rel_dir in set(ENTITY_TYPE_DIRS.values()):
                (self.brain_dir / rel_dir).mkdir(parents=True, exist_ok=True)
            if not self.registry_path.exists():
                self._save_registry(
                    {
                        "$schema": "brain://registry/v2",
                        "$version": 2,
                        "$updated": _utc_iso(),
                        "entities": {},
                        "alias_index": {},
                    }
                )
            if not self.brain_md_path.exists():
                self.regenerate_brain_md()

    def _load_registry(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {
                "$schema": "brain://registry/v2",
                "$version": 2,
                "$updated": _utc_iso(),
                "entities": {},
                "alias_index": {},
            }
        try:
            raw = self.registry_path.read_text(encoding="utf-8")
            data = _load_yaml(raw)
            if "entities" not in data or not isinstance(data["entities"], dict):
                data["entities"] = {}
            if "alias_index" not in data or not isinstance(data["alias_index"], dict):
                data["alias_index"] = {}
            return data
        except Exception:
            return {
                "$schema": "brain://registry/v2",
                "$version": 2,
                "$updated": _utc_iso(),
                "entities": {},
                "alias_index": {},
            }

    def _save_registry(self, reg: dict[str, Any]) -> None:
        reg["$updated"] = _utc_iso()
        alias_idx: dict[str, str] = {}
        for slug, entry in reg.get("entities", {}).items():
            name = str(entry.get("name") or "").strip().lower()
            if name:
                alias_idx[name] = slug
            for al in entry.get("aliases") or []:
                al_norm = str(al).strip().lower()
                if al_norm:
                    alias_idx[al_norm] = slug
        reg["alias_index"] = alias_idx
        self.registry_path.write_text(_dump_yaml(reg) + "\n", encoding="utf-8")

    def _parse_entity_file(self, path: Path) -> tuple[dict[str, Any], str]:
        if not path.exists():
            return {}, ""
        try:
            raw = path.read_text(encoding="utf-8")
            if raw.startswith("---"):
                parts = raw.split("---", 2)
                if len(parts) >= 3:
                    fm = _load_yaml(parts[1])
                    body = parts[2].strip()
                    return fm, body
            return {}, raw.strip()
        except Exception:
            return {}, ""

    def _write_entity_file(self, path: Path, frontmatter: dict[str, Any], body: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fm_str = _dump_yaml(frontmatter)
        full = f"---\n{fm_str}\n---\n\n{body.strip()}\n"
        path.write_text(full, encoding="utf-8")

    def upsert_entity(
        self,
        entity_type: str,
        name: str,
        summary: str = "",
        attributes: dict[str, Any] | None = None,
        content: str = "",
        relationships: list[str] | dict[str, list[str]] | None = None,
        aliases: list[str] | None = None,
        source_url: str = "",
        tier: int | None = None,
        actor: str = "agent/harness",
    ) -> dict[str, Any]:
        if self.locked:
            raise PermissionError("unlock a profile to save to your Brain")
        norm_type = (entity_type or "note").strip().lower()
        if norm_type not in ENTITY_TYPE_DIRS:
            norm_type = "note"
        clean_name = (name or "").strip() or "Untitled Entity"
        slug = slugify(clean_name)

        with self.lock:
            reg = self._load_registry()
            # Resolve via alias_index if already registered under an alias
            alias_idx = reg.get("alias_index") or {}
            if clean_name.lower() in alias_idx:
                slug = alias_idx[clean_name.lower()]

            # Section 4 (M18): For webmail accounts, upsert by (provider, email) so a second account
            # updates or keys cleanly while keeping the entity name as the provider.
            if norm_type == "account":
                in_attrs = attributes or {}
                provider_val = str(in_attrs.get("provider") or in_attrs.get("service") or clean_name).strip()
                email_val = str(in_attrs.get("email") or "").strip().lower()
                matched_slug: str | None = None
                for cand_slug, cand_meta in (reg.get("entities") or {}).items():
                    if str(cand_meta.get("$type") or "") != "account":
                        continue
                    cand_attrs = cand_meta.get("attributes") or {}
                    cand_prov = str(cand_attrs.get("provider") or cand_attrs.get("service") or cand_meta.get("name") or "").strip()
                    cand_email = str(cand_attrs.get("email") or "").strip().lower()
                    if cand_prov.lower() != provider_val.lower():
                        continue
                    if email_val and cand_email == email_val:
                        matched_slug = cand_slug
                        break
                    if email_val and not cand_email:
                        matched_slug = cand_slug
                        break
                    if not email_val:
                        matched_slug = cand_slug
                        break
                if matched_slug:
                    slug = matched_slug
                elif email_val:
                    # Check if another account on the same provider already exists with a different email
                    other_prov = any(
                        str(m.get("$type") or "") == "account"
                        and str((m.get("attributes") or {}).get("provider") or m.get("name") or "").strip().lower() == provider_val.lower()
                        for m in (reg.get("entities") or {}).values()
                    )
                    if other_prov:
                        slug = slugify(f"{provider_val}-{email_val}")

            if norm_type == "story":
                in_attrs = attributes or {}
                src_key = str(in_attrs.get("$source") or "").strip()
                cid_key = str(in_attrs.get("$cluster_id") or "").strip()
                if src_key or cid_key:
                    for cand_slug, cand_meta in (reg.get("entities") or {}).items():
                        if str(cand_meta.get("$type") or "") != "story":
                            continue
                        cand_attrs = cand_meta.get("attributes") or {}
                        if (src_key and str(cand_attrs.get("$source") or "").strip() == src_key) or (
                            cid_key and str(cand_attrs.get("$cluster_id") or "").strip() == cid_key
                        ):
                            slug = cand_slug
                            break

            if norm_type == "document":
                in_attrs = attributes or {}
                item_key = str(in_attrs.get("$item_key") or "").strip()
                if item_key:
                    matched_doc_slug: str | None = None
                    for cand_slug, cand_meta in (reg.get("entities") or {}).items():
                        if str(cand_meta.get("$type") or "") != "document":
                            continue
                        cand_attrs = cand_meta.get("attributes") or {}
                        if str(cand_attrs.get("$item_key") or "").strip() == item_key:
                            matched_doc_slug = cand_slug
                            break
                    if matched_doc_slug:
                        slug = matched_doc_slug
                    elif slug in (reg.get("entities") or {}):
                        existing_meta = reg["entities"][slug]
                        existing_ikey = str((existing_meta.get("attributes") or {}).get("$item_key") or "").strip()
                        if existing_ikey and existing_ikey != item_key:
                            short_suffix = hashlib.sha1(item_key.encode("utf-8")).hexdigest()[:6]
                            slug = f"{slug[:56]}-{short_suffix}"

            existing_entry = reg["entities"].get(slug)
            if existing_entry and existing_entry.get("$ref"):
                rel_path = str(existing_entry["$ref"])
            else:
                subdir = ENTITY_TYPE_DIRS.get(norm_type, "Notes")
                safe_filename = re.sub(r"[^A-Za-z0-9_\-]+", "_", clean_name).strip("_")[:60] or slug
                rel_path = f"{subdir}/{safe_filename}.md"

            abs_path = self.brain_dir / rel_path
            fm, existing_body = self._parse_entity_file(abs_path)

            is_create = not bool(fm)
            now_iso = _utc_iso()
            today = _utc_date()

            merged_aliases: list[str] = list(fm.get("aliases") or [])
            for a in aliases or []:
                a_str = str(a).strip()
                if a_str and a_str.lower() != clean_name.lower() and a_str not in merged_aliases:
                    merged_aliases.append(a_str)

            merged_attrs: dict[str, Any] = dict(fm.get("attributes") or {})
            for k, v in (attributes or {}).items():
                if v is not None and str(v).strip() != "":
                    merged_attrs[str(k).strip()] = v
            if source_url and "source_url" not in merged_attrs:
                merged_attrs["source_url"] = source_url

            # Merge relationships
            merged_rels: dict[str, list[str]] = {}
            old_rels = fm.get("relationships")
            if isinstance(old_rels, dict):
                for rk, rv in old_rels.items():
                    if isinstance(rv, list):
                        merged_rels[rk] = list(rv)
            if isinstance(relationships, dict):
                for rk, rv in relationships.items():
                    bucket = merged_rels.setdefault(rk, [])
                    for item in rv if isinstance(rv, list) else [rv]:
                        item_s = str(item).strip()
                        if item_s and item_s not in bucket:
                            bucket.append(item_s)
            elif isinstance(relationships, list):
                bucket = merged_rels.setdefault("relates_to", [])
                for item in relationships:
                    item_s = str(item).strip()
                    if item_s and item_s not in bucket:
                        bucket.append(item_s)

            effective_summary = (summary or fm.get("summary") or content[:160] or clean_name).strip()
            effective_summary = re.sub(r"\s+", " ", effective_summary)[:220]

            effective_tier = tier if tier in (1, 2) else int(fm.get("tier") or (1 if norm_type in TIER1_TYPES else 2))

            events: list[dict[str, Any]] = list(fm.get("$events") or [])
            events.append(
                {
                    "timestamp": now_iso,
                    "type": "entity_create" if is_create else "entity_update",
                    "actor": actor,
                    "summary": effective_summary[:120],
                }
            )
            events = events[-12:]

            new_fm: dict[str, Any] = {
                "type": norm_type,
                "name": clean_name,
                "slug": slug,
                "tier": effective_tier,
                "status": "active",
                "summary": effective_summary,
                "aliases": merged_aliases,
                "attributes": merged_attrs,
                "relationships": merged_rels,
                "$updated": now_iso,
                "created": fm.get("created") or today,
                "updated": today,
                "$events": events,
            }
            if norm_type == "skill":
                for sk_key in (
                    "trigger_examples",
                    "required_context",
                    "step_graph",
                    "send_gate_steps",
                    "domain_recipes",
                    "last_success_at",
                    "redteam_passed",
                    "redteam_checked_at",
                    "redteam_cases_run",
                    "redteam_summary",
                ):
                    if sk_key in merged_attrs:
                        new_fm[sk_key] = merged_attrs[sk_key]

            # Assemble Markdown body
            body_lines: list[str] = []
            refresh_story_body = bool(
                (
                    norm_type == "story"
                    and actor in ("news/hourly_sync", "user/news_save")
                    and (content or "").strip()
                )
                or (
                    norm_type == "document"
                    and actor in ("drives/background_sync", "drives/manual_sync")
                    and (content or "").strip()
                )
            )
            if not existing_body or refresh_story_body:
                body_lines.append(f"# {clean_name}")
                body_lines.append("")
                if effective_summary:
                    body_lines.append(effective_summary)
                    body_lines.append("")
            else:
                body_lines.append(existing_body)
                body_lines.append("")

            visible_attrs = {k: v for k, v in merged_attrs.items() if not str(k).startswith("$") and k != "source_url"}
            if visible_attrs:
                attr_block = "\n".join(f"- **{k}**: {v}" for k, v in visible_attrs.items())
                if refresh_story_body or "## Attributes" not in existing_body:
                    body_lines.append("## Attributes")
                    body_lines.append(attr_block)
                    body_lines.append("")
                else:
                    # Replace existing Attributes section or append new keys
                    for k, v in visible_attrs.items():
                        line_check = f"**{k}**:"
                        if line_check not in existing_body:
                            body_lines.append(f"- **{k}**: {v}")

            clean_content = (content or "").strip()
            if clean_content and (refresh_story_body or clean_content not in existing_body):
                body_lines.append(f"## Captured Context ({today})")
                if source_url:
                    body_lines.append(f"Source: `{source_url}`")
                body_lines.append(clean_content)
                body_lines.append("")

            final_body = "\n".join(body_lines).strip()
            self._write_entity_file(abs_path, new_fm, final_body)

            pub_at_str = str(merged_attrs.get("published_at") or "").strip()
            sync_at_str = str(merged_attrs.get("synced_at") or "").strip()
            pub_ts_num = _parse_ts(merged_attrs.get("$published_ts")) or _parse_ts(pub_at_str)
            reg_rec: dict[str, Any] = {
                "$type": norm_type,
                "$status": "active",
                "$ref": rel_path,
                "name": clean_name,
                "tier": effective_tier,
                "summary": effective_summary,
                "aliases": merged_aliases,
                "attributes": merged_attrs,
                "updated": now_iso,
            }
            if pub_at_str:
                reg_rec["published_at"] = pub_at_str
            if sync_at_str:
                reg_rec["synced_at"] = sync_at_str
            if pub_ts_num is not None:
                reg_rec["$published_ts"] = float(pub_ts_num)
            reg["entities"][slug] = reg_rec
            self._save_registry(reg)
            self.regenerate_brain_md()
            self.invalidate_summary_cache()

            return {
                "slug": slug,
                "type": norm_type,
                "name": clean_name,
                "path": rel_path,
                "tier": effective_tier,
                "summary": effective_summary,
                "attributes": merged_attrs,
                "published_at": pub_at_str or now_iso,
                "synced_at": sync_at_str,
                "updated": now_iso,
            }

    def delete_entity(self, slug: str) -> bool:
        with self.lock:
            self._entity_emb_cache.pop(slug, None)
            reg = self._load_registry()
            entry = reg.get("entities", {}).pop(slug, None)
            if not entry:
                return False
            ref = entry.get("$ref")
            if ref:
                p = self.brain_dir / str(ref)
                if p.exists():
                    try:
                        p.unlink()
                    except OSError:
                        pass
            self._save_registry(reg)
            self.regenerate_brain_md()
            self.invalidate_summary_cache()
            return True

    def delete_entities_by_source(self, sources: set[str], entity_type: str | None = None) -> int:
        """Removes entities matching any `$source` / `source_url` using registry metadata without rebuilding summaries per entity."""
        if not sources:
            return 0
        removed = 0
        with self.lock:
            reg = self._load_registry()
            entities = reg.get("entities") or {}
            to_delete: list[str] = []
            for slug, meta in entities.items():
                if entity_type and str(meta.get("$type") or "") != entity_type:
                    continue
                attrs = meta.get("attributes") or {}
                src = str(attrs.get("source_url") or attrs.get("$source") or "")
                if src in sources:
                    to_delete.append(slug)
            if not to_delete:
                return 0
            for slug in to_delete:
                self._entity_emb_cache.pop(slug, None)
                entry = entities.pop(slug, None)
                ref = entry.get("$ref") if isinstance(entry, dict) else None
                if ref:
                    p = self.brain_dir / str(ref)
                    if p.exists():
                        try:
                            p.unlink()
                        except OSError:
                            pass
                removed += 1
            self._save_registry(reg)
            self.regenerate_brain_md()
            self.invalidate_summary_cache()
        return removed

    def regenerate_brain_md(self) -> str:
        """
        Generates the compressed pipe-delimited BRAIN.md index following the
        PM-OS Brain / SGS-Brain two-tier format.
        """
        if self.locked:
            return ""
        with self.lock:
            reg = self._load_registry()
            entities: dict[str, dict[str, Any]] = reg.get("entities") or {}

            tier1_rows: list[str] = []
            tier2_rows: list[str] = []

            sorted_items = sorted(
                entities.items(),
                key=lambda kv: (int(kv[1].get("tier") or 2), str(kv[1].get("updated") or ""), kv[0]),
                reverse=False,
            )

            for slug, meta in sorted_items:
                etype = str(meta.get("$type") or "note")
                name = str(meta.get("name") or slug).replace("|", "/")
                status = str(meta.get("$status") or "active")
                summary = str(meta.get("summary") or "").replace("|", "/").replace("\n", " ")[:140]
                ref = str(meta.get("$ref") or "")
                attrs = meta.get("attributes") or {}
                attr_pairs = []
                for k, v in attrs.items():
                    if k == "source_url" or str(k).startswith("$"):
                        continue
                    attr_pairs.append(f"{k}:{str(v).replace('|', '/')[:60]}")
                    if len(attr_pairs) >= 6:
                        break
                attr_str = ",".join(attr_pairs) if attr_pairs else ref

                if int(meta.get("tier") or 2) == 1:
                    tier1_rows.append(f"{slug}|{etype}|{name}|{status}|{summary}|{attr_str}")
                else:
                    tier2_rows.append(f"{slug}|{etype}|{name}|{status}|{ref}|{summary[:90]}")

            lines = [
                "# BRAIN.md - Satz Personal Knowledge Graph Index",
                f"<!-- Generated: {_utc_iso()} | Architecture: PM-OS / SGS-Brain v2 -->",
                "",
                "## Core User Entities, Accounts, People & Places (Tier 1)",
                "id|type|name|status|summary|attributes",
            ]
            if tier1_rows:
                lines.extend(tier1_rows[:60])
            else:
                lines.append("(none recorded yet)")

            lines.extend(
                [
                    "",
                    "## Knowledge Graph Entities & Notes (Tier 2)",
                    "id|type|name|status|path|summary",
                ]
            )
            if tier2_rows:
                lines.extend(tier2_rows[:80])
            else:
                lines.append("(none recorded yet)")

            content = "\n".join(lines) + "\n"
            self.brain_md_path.write_text(content, encoding="utf-8")
            try:
                self._brain_md_mtime = self.brain_md_path.stat().st_mtime
            except OSError:
                self._brain_md_mtime = time.time()
            self._brain_md_cache = content
            return content

    def list_entities(self) -> list[dict[str, Any]]:
        return list(self.get_brain_summary().get("entities") or [])

    def get_entity_by_slug(self, slug: str, body_limit: int | None = 4000) -> dict[str, Any] | None:
        """Returns a full entity record (including clean attributes and body) by slug or alias."""
        if self.locked:
            return None
        key = slugify(slug) if slug else ""
        if not key:
            return None
        with self.lock:
            reg = self._load_registry()
            entities = reg.get("entities") or {}
            meta = entities.get(key)
            if meta is None:
                alias_idx = reg.get("alias_index") or {}
                mapped = alias_idx.get((slug or "").strip().lower())
                if mapped and mapped in entities:
                    key = mapped
                    meta = entities[mapped]
            if meta is None:
                return None
            return self._build_entity_record(key, meta, body_limit=body_limit)

    def _build_entity_record(
        self,
        slug: str,
        meta: dict[str, Any],
        *,
        now_snap: float | None = None,
        body_limit: int | None = 600,
    ) -> dict[str, Any]:
        raw_attrs = meta.get("attributes") or {}
        clean_attrs = {
            k: v
            for k, v in raw_attrs.items()
            if not str(k).startswith("$")
        }
        ref = str(meta.get("$ref") or "")
        fm: dict[str, Any] = {}
        body_text = ""
        if ref:
            try:
                fm, body_text = self._parse_entity_file(self.brain_dir / ref)
            except Exception:
                fm, body_text = {}, ""
        source_url = str(raw_attrs.get("source_url") or raw_attrs.get("$source") or "")
        ev_ts = _entity_event_ts(meta)
        cur_now = float(now_snap if now_snap is not None else time.time())
        body_out = body_text[:body_limit] if (body_limit is not None and body_limit > 0) else body_text
        record: dict[str, Any] = {
            "slug": slug,
            "type": str(meta.get("$type") or "note"),
            "name": str(meta.get("name") or slug),
            "tier": int(meta.get("tier") or 2),
            "summary": str(meta.get("summary") or ""),
            "path": ref,
            "source_url": source_url,
            "body": body_out,
            "attributes": clean_attrs,
            "published_at": str(raw_attrs.get("published_at") or meta.get("published_at") or meta.get("updated") or ""),
            "synced_at": str(raw_attrs.get("synced_at") or meta.get("synced_at") or ""),
            "timestamp_ts": round(ev_ts, 3) if ev_ts > 0 else 0.0,
            "age_label": _format_time_tag(ev_ts, cur_now),
            "updated": str(meta.get("updated") or ""),
        }
        if body_limit is None:
            record["aliases"] = list(meta.get("aliases") or fm.get("aliases") or [])
            record["relationships"] = list(fm.get("relationships") or meta.get("relationships") or [])
        return record

    def get_entity(self, slug: str) -> dict[str, Any] | None:
        """Reads the complete entity record (frontmatter + full Markdown body) by slug or alias."""
        if self.locked:
            return None
        key = (slug or "").strip()
        if key.startswith("brain:"):
            key = key[6:].strip()
        if not key:
            return None
        with self.lock:
            reg = self._load_registry()
            entities = reg.get("entities") or {}
            resolved_slug = key if key in entities else (reg.get("alias_index") or {}).get(key.lower(), "")
            if not resolved_slug:
                cand = slugify(key)
                if cand in entities:
                    resolved_slug = cand
            if not resolved_slug or resolved_slug not in entities:
                return None
            return self._build_entity_record(
                resolved_slug,
                entities[resolved_slug],
                body_limit=None,
            )

    def get_brain_summary(self) -> dict[str, Any]:
        enc_status = self.get_encoder_status()
        if self.locked:
            return {
                "brain_dir": "",
                "brain_md": "",
                "entity_count": 0,
                "entities": [],
                "locked": True,
                "message": "unlock a profile to save to your Brain",
                "encoder": enc_status,
                "brain_ranking": enc_status["label"],
            }
        with self.lock:
            try:
                reg_mtime = self.registry_path.stat().st_mtime if self.registry_path.exists() else -2.0
            except OSError:
                reg_mtime = -2.0
            try:
                bmd_mtime = self.brain_md_path.stat().st_mtime if self.brain_md_path.exists() else -2.0
            except OSError:
                bmd_mtime = -2.0
            if (
                self._summary_cache is not None
                and reg_mtime == self._summary_cache_mtime
                and bmd_mtime == self._summary_cache_brain_mtime
            ):
                now_snap = time.time()
                cached = self._summary_cache
                refreshed_entities: list[dict[str, Any]] = []
                for ent in cached.get("entities") or []:
                    ev_ts = float(ent.get("timestamp_ts") or 0.0)
                    ent_copy = dict(ent)
                    ent_copy["age_label"] = _format_time_tag(ev_ts, now_snap)
                    refreshed_entities.append(ent_copy)
                return {
                    "brain_dir": cached["brain_dir"],
                    "brain_md": cached["brain_md"],
                    "entity_count": cached["entity_count"],
                    "entities": refreshed_entities,
                    "locked": False,
                    "encoder": enc_status,
                    "brain_ranking": enc_status["label"],
                }

            reg = self._load_registry()
            brain_md = self.get_cached_brain_md()
            entities_out: list[dict[str, Any]] = []
            now_snap = time.time()
            for slug, meta in sorted(
                (reg.get("entities") or {}).items(),
                key=lambda kv: (_entity_event_ts(kv[1]), str(kv[1].get("updated") or "")),
                reverse=True,
            ):
                entities_out.append(
                    self._build_entity_record(slug, meta, now_snap=now_snap, body_limit=600)
                )
            summary_payload = {
                "brain_dir": str(self.brain_dir),
                "brain_md": brain_md,
                "entity_count": len(entities_out),
                "entities": entities_out[:120],
                "locked": False,
                "encoder": enc_status,
                "brain_ranking": enc_status["label"],
            }
            self._summary_cache = summary_payload
            try:
                self._summary_cache_mtime = self.registry_path.stat().st_mtime if self.registry_path.exists() else -2.0
                self._summary_cache_brain_mtime = self.brain_md_path.stat().st_mtime if self.brain_md_path.exists() else -2.0
            except OSError:
                self._summary_cache_mtime = reg_mtime
                self._summary_cache_brain_mtime = bmd_mtime
            return summary_payload

    def search_by_time(
        self,
        hours: float = 24.0,
        entity_types: list[str] | None = None,
        query: str = "",
        limit: int = 20,
        now_ts: float | None = None,
    ) -> list[dict[str, Any]]:
        if self.locked:
            return []
        cur = float(now_ts if now_ts is not None else time.time())
        cutoff = cur - max(0.1, float(hours)) * 3600.0
        type_filter = {t.strip().lower() for t in (entity_types or []) if t.strip()}
        q_low = (query or "").strip().lower()
        q_toks = re.findall(r"[a-z0-9äöüß]{3,}", q_low) if q_low else []
        matched: list[dict[str, Any]] = []
        for ent in self.get_brain_summary().get("entities") or []:
            if type_filter and str(ent.get("type") or "").lower() not in type_filter:
                continue
            ev_ts = float(ent.get("timestamp_ts") or 0.0)
            if ev_ts < cutoff:
                continue
            if q_toks:
                hay = f"{ent['slug']} {ent['name']} {ent['summary']} {ent.get('body') or ''}".lower()
                if q_low not in hay and not any(tok in hay for tok in q_toks):
                    continue
            matched.append(ent)
        matched.sort(key=lambda e: (-float(e.get("timestamp_ts") or 0.0), float((e.get("attributes") or {}).get("confidence10") or 0.0)))
        return matched[:limit]

    def search_entities(
        self,
        query: str,
        limit: int = 20,
        hours: float | None = None,
        entity_type: str | None = None,
        now_ts: float | None = None,
    ) -> list[dict[str, Any]]:
        if self.locked:
            return []
        q_str = (query or "").strip()
        cur = float(now_ts if now_ts is not None else time.time())
        cutoff = (cur - float(hours) * 3600.0) if (hours is not None and hours > 0) else None
        etype_f = entity_type.strip().lower() if entity_type else None

        if not q_str:
            ents = list(self.get_brain_summary().get("entities") or [])
            if etype_f:
                ents = [e for e in ents if str(e.get("type") or "").lower() == etype_f]
            if cutoff is not None:
                ents = [e for e in ents if float(e.get("timestamp_ts") or 0.0) >= cutoff]
            return ents[:limit]

        hot = self.load_hot_entities(q_str, open_sources=None, limit=limit * 2, now_ts=cur)
        seen_slugs = {h["slug"] for h in hot}
        q_low = q_str.lower()
        for ent in self.get_brain_summary().get("entities") or []:
            if ent["slug"] in seen_slugs:
                continue
            hay = f"{ent['slug']} {ent['name']} {ent['type']} {ent['summary']} {json.dumps(ent['attributes'], ensure_ascii=False)} {ent.get('body') or ''}".lower()
            if q_low in hay or any(tok in hay for tok in re.findall(r"[a-z0-9äöüß]{3,}", q_low)):
                hot.append(ent)
                seen_slugs.add(ent["slug"])
        if etype_f:
            hot = [e for e in hot if str(e.get("type") or "").lower() == etype_f]
        if cutoff is not None:
            hot = [e for e in hot if float(e.get("timestamp_ts") or 0.0) >= cutoff]
        return hot[:limit]

    def load_hot_entities(
        self,
        query: str,
        open_sources: list[dict[str, Any]] | None = None,
        limit: int = 5,
        now_ts: float | None = None,
    ) -> list[dict[str, Any]]:
        if self.locked:
            return []
        with self.lock:
            reg = self._load_registry()
            entities = reg.get("entities") or {}
            if not entities:
                return []

            cur_now = float(now_ts if now_ts is not None else time.time())
            temporal = _parse_temporal_query(query or "", now_ts=cur_now)

            search_blob = (query or "").lower()
            for src in open_sources or []:
                search_blob += " " + str(src.get("title") or "").lower()
                search_blob += " " + str(src.get("domain") or "").lower()

            query_tokens = [
                t for t in re.findall(r"[a-z0-9]{3,}", search_blob)
                if t not in {"the", "and", "for", "from", "with", "this", "that", "what", "where", "when", "does", "give", "show", "tell"}
            ]

            scored: list[tuple[float, str, dict[str, Any]]] = []
            slug_list = list(entities.keys())
            ent_texts: list[str] = []
            for slug in slug_list:
                meta = entities[slug]
                aliases_str = " ".join(str(a) for a in (meta.get("aliases") or []))
                ent_texts.append(
                    f"{meta.get('name') or slug} {aliases_str} {meta.get('summary') or ''}"
                )

            sim_scores: dict[str, float] = {}
            if search_blob.strip() and ent_texts:
                enc = self._get_encoder()
                if enc is not None:
                    try:
                        import numpy as np

                        missing_indices: list[int] = []
                        missing_texts: list[str] = []
                        for idx, sl in enumerate(slug_list):
                            txt = ent_texts[idx]
                            cached = self._entity_emb_cache.get(sl)
                            if cached is None or cached[0] != txt:
                                missing_indices.append(idx)
                                missing_texts.append(txt)

                        q_and_missing = [search_blob[:400]] + missing_texts
                        with _SHARED_ENCODER_LOCK:
                            encoded_batch = enc.encode(q_and_missing).astype(np.float32)
                        q_vec = encoded_batch[0]
                        for m_offset, orig_idx in enumerate(missing_indices):
                            sl = slug_list[orig_idx]
                            self._entity_emb_cache[sl] = (ent_texts[orig_idx], encoded_batch[1 + m_offset])

                        cand_vecs = np.stack([self._entity_emb_cache[sl][1] for sl in slug_list], axis=0)
                        dots = cand_vecs @ q_vec
                        for idx, sl in enumerate(slug_list):
                            sim_scores[sl] = float(dots[idx])
                    except Exception:
                        pass

            for slug, meta in entities.items():
                score = 0.0
                name_l = str(meta.get("name") or "").lower()
                summary_l = str(meta.get("summary") or "").lower()
                etype_l = str(meta.get("$type") or "").lower()
                attrs_dict = meta.get("attributes") or {}
                attrs_str = json.dumps(attrs_dict, ensure_ascii=False).lower()
                ev_ts = _entity_event_ts(meta)
                age_hours = max(0.0, (cur_now - ev_ts) / 3600.0) if ev_ts > 0.0 else 1e6

                if slug in search_blob or (name_l and name_l in search_blob):
                    score += 5.0
                for al in meta.get("aliases") or []:
                    if str(al).lower() in search_blob:
                        score += 4.0
                matched_name_toks = 0
                matched_type = False
                for tok in query_tokens:
                    if tok in name_l:
                        score += 2.5
                        matched_name_toks += 1
                    elif tok in etype_l or tok.rstrip("s") == etype_l:
                        score += 2.0
                        matched_type = True
                    elif tok in summary_l or tok in attrs_str:
                        score += 1.0
                if matched_name_toks >= 2 or (matched_name_toks >= 1 and matched_type):
                    score += 3.0
                if any(w in search_blob for w in ("arrive", "delivery", "shipped", "tracking", "package", "parcel")) and etype_l == "order":
                    score += 3.5
                if any(w in search_blob for w in ("code", "voucher", "discount", "promo", "coupon")) and etype_l == "promotion":
                    score += 3.5
                if etype_l == "skill":
                    for trig in attrs_dict.get("trigger_examples") or []:
                        t_l = str(trig or "").strip().lower()
                        if t_l and (t_l in search_blob or (query_tokens and any(tok in t_l for tok in query_tokens))):
                            score += 4.0
                            break
                if int(meta.get("tier") or 2) == 1:
                    score += 1.0

                sim = sim_scores.get(slug, 0.0)
                if sim > 0.12:
                    score += sim * 2.5

                # Time-aware ranking for synced news stories and timestamped knowledge
                has_topical_signal = score > (1.0 if int(meta.get("tier") or 2) == 1 else 0.2)
                is_news_story_temporal = temporal["is_news_query"] and etype_l in ("story", "claim")
                if ev_ts > 0.0 and (has_topical_signal or is_news_story_temporal):
                    if temporal["start_ts"] is not None:
                        end_bound = temporal["end_ts"] if temporal["end_ts"] is not None else (cur_now + 600.0)
                        if temporal["start_ts"] <= ev_ts <= end_bound:
                            span_pos = math.exp(-age_hours / 36.0)
                            score += 1.2 + 2.6 * span_pos
                        elif etype_l == "story":
                            score -= 2.5
                    elif temporal["recency_bias"]:
                        score += 2.8 * math.exp(-age_hours / 48.0)
                    elif etype_l in ("story", "claim", "note"):
                        score += 0.9 * math.exp(-age_hours / 72.0)

                    if etype_l == "story" and score > 0.0:
                        try:
                            conf10 = float(attrs_dict.get("confidence10") or 0.0)
                        except (TypeError, ValueError):
                            conf10 = 0.0
                        score += min(0.8, conf10 / 12.5)

                if score > 0.6:
                    scored.append((score, slug, meta))

            scored.sort(key=lambda item: item[0], reverse=True)
            results: list[dict[str, Any]] = []
            for sc_val, slug, meta in scored[:limit]:
                ref = meta.get("$ref")
                body_text = ""
                if ref:
                    _, body_text = self._parse_entity_file(self.brain_dir / str(ref))
                raw_attrs = meta.get("attributes") or {}
                clean_attrs = {
                    k: v
                    for k, v in raw_attrs.items()
                    if not str(k).startswith("$")
                }
                source_url = str(raw_attrs.get("source_url") or raw_attrs.get("$source") or "")
                ev_ts = _entity_event_ts(meta)
                results.append(
                    {
                        "slug": slug,
                        "type": meta.get("$type") or "note",
                        "name": meta.get("name") or slug,
                        "tier": int(meta.get("tier") or 2),
                        "path": ref or "",
                        "source_url": source_url,
                        "summary": meta.get("summary") or "",
                        "attributes": clean_attrs,
                        "published_at": str(raw_attrs.get("published_at") or meta.get("published_at") or meta.get("updated") or ""),
                        "synced_at": str(raw_attrs.get("synced_at") or meta.get("synced_at") or ""),
                        "timestamp_ts": round(ev_ts, 3) if ev_ts > 0.0 else 0.0,
                        "age_label": _format_time_tag(ev_ts, cur_now),
                        "body": body_text[:1400],
                        "score": round(float(sc_val), 3),
                    }
                )
            return results

    def build_model_context_with_citations(
        self,
        query: str,
        open_sources: list[dict[str, Any]] | None = None,
        max_chars: int = 3400,
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Section 3.2 (M9) & Section 6 (M20):
        - Keeps BRAIN.md cached in memory (reloaded only when mtime changes).
        - Numbers Brain items used in the prompt as `[B1]`, `[B2]`, ... in a separate
          `brain_sources` list so answers can cite `[B1]`, `[B2]` and the citation checker
          can verify them.
        """
        if self.locked:
            return (
                (
                    "SATZ BRAIN (LOCAL KNOWLEDGE GRAPH):\n"
                    "Brain is locked (unlock a profile to save to your Brain)."
                )[:max_chars],
                [],
            )
        with self.lock:
            reg = self._load_registry()
            entities = reg.get("entities") or {}
            if not entities:
                return (
                    (
                        "SATZ BRAIN (LOCAL KNOWLEDGE GRAPH):\n"
                        "No entities stored yet. You can store entities, addresses, contacts, accounts, "
                        "and notes into the Brain at any time using <brain_store>..."
                    )[:max_chars],
                    [],
                )

            # Warm / validate in-memory BRAIN.md cache via mtime check
            _ = self.get_cached_brain_md()

            hot = self.load_hot_entities(query, open_sources, limit=5)
            brain_sources: list[dict[str, Any]] = []
            seen_slugs: set[str] = set()

            for h in hot:
                slug = str(h["slug"])
                if slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                b_idx = len(brain_sources) + 1
                cite_lbl = f"B{b_idx}"
                clean_h_attrs = {
                    k: v
                    for k, v in (h.get("attributes") or {}).items()
                    if not str(k).startswith("$")
                }
                attrs_json = json.dumps(clean_h_attrs, ensure_ascii=False) if clean_h_attrs else "{}"
                body_str = str(h.get("body") or "").strip()
                full_text = f"{h['name']} ({h['type']}) {h.get('summary') or ''} {attrs_json} {body_str}".strip()
                brain_sources.append(
                    {
                        "id": f"brain:{slug}",
                        "citation": cite_lbl,
                        "cite_label": cite_lbl,
                        "b_index": b_idx,
                        "slug": slug,
                        "name": str(h["name"]),
                        "type": str(h["type"]),
                        "summary": str(h.get("summary") or ""),
                        "path": str(h.get("path") or ""),
                        "source_url": str(h.get("source_url") or ""),
                        "attributes": clean_h_attrs,
                        "published_at": str(h.get("published_at") or ""),
                        "timestamp_ts": float(h.get("timestamp_ts") or 0.0),
                        "age_label": str(h.get("age_label") or ""),
                        "body": body_str,
                        "text": full_text[:1200],
                        "full_text": full_text,
                    }
                )

            lines: list[str] = [
                "# NUMBERED SATZ BRAIN ITEMS (cite inline as [B1], [B2], ... when used):"
            ]
            if not brain_sources:
                lines.append("(no matching Brain entities for this query)")
            else:
                for bs in brain_sources:
                    attrs_json = (
                        json.dumps(bs["attributes"], ensure_ascii=False)
                        if bs["attributes"]
                        else "{}"
                    )
                    age_line = f"Time: {bs['age_label']}\n" if bs.get("age_label") else ""
                    block = (
                        f"\n[{bs['cite_label']}] ({bs['type']}) {bs['name']} · {bs['summary']}\n"
                        f"{age_line}"
                        f"Attributes: {attrs_json}"
                    )
                    if bs["body"]:
                        block += f"\nDetails: {bs['body'][:900]}"
                    cur_len = sum(len(x) + 1 for x in lines)
                    if cur_len + len(block) <= max_chars:
                        lines.append(block)
                    else:
                        rem = max_chars - cur_len
                        if rem > 80:
                            lines.append(block[:rem])
                        break

            return "\n".join(lines)[:max_chars], brain_sources

    def build_model_context(
        self,
        query: str,
        open_sources: list[dict[str, Any]] | None = None,
        max_chars: int = 3000,
    ) -> str:
        ctx, _ = self.build_model_context_with_citations(
            query=query,
            open_sources=open_sources,
            max_chars=max_chars,
        )
        return ctx

    def enrich_from_page(
        self,
        url: str,
        domain: str,
        title: str,
        text: str,
        conversation_id: str = "default",
    ) -> list[dict[str, Any]]:
        """
        Passive Brain enrichment as the user browses:
        - Detects authenticated user accounts on known web apps (e.g. Gmail, GitHub, Outlook, Proton Mail)
        - Entity name is the provider; address goes in `attributes.email`. Upserts by `(provider, email)`.
        """
        created_or_updated: list[dict[str, Any]] = []
        if self.locked or not url or not domain:
            return created_or_updated

        emails_found = EMAIL_RE.findall(f"{title or ''}\n{(text or '')[:600]}")
        acct_email = emails_found[0].lower() if emails_found else ""

        provider: str | None = None
        aliases_base: list[str] = ["email", "webmail"]
        if "mail.google.com" in domain:
            provider = "Gmail"
            aliases_base = ["gmail", "google mail", "email", "my email"]
        elif "outlook.live.com" in domain or "outlook.office.com" in domain:
            provider = "Outlook"
            aliases_base = ["outlook", "email", "webmail", domain]
        elif "mail.proton.me" in domain:
            provider = "Proton Mail"
            aliases_base = ["proton", "proton mail", "email", "webmail", domain]

        if provider:
            attrs: dict[str, Any] = {
                "provider": provider,
                "service": provider,
                "domain": domain,
                "url": url,
                "last_seen": _utc_iso(),
            }
            if acct_email:
                attrs["email"] = acct_email
            aliases = list(aliases_base)
            if acct_email and acct_email not in aliases:
                aliases.append(acct_email)
            ent = self.upsert_entity(
                entity_type="account",
                name=provider,
                summary=f"Authenticated {provider} session ({(title or domain)[:100]})",
                attributes=attrs,
                aliases=aliases,
                source_url=url,
                tier=1,
                actor="passive/browser",
            )
            created_or_updated.append(ent)

        return created_or_updated

    def extract_and_execute_brain_directives(
        self,
        raw_text: str,
        source_url: str = "",
        user_msg: str | None = None,
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Section 2.4:
        Parses <brain_store>JSON</brain_store> blocks from model output.
        - Executed directly ONLY when the user's own message matches `STORE_INTENT_RE`.
        - Otherwise each directive becomes a proposal (`proposals`) shown under the answer:
          `[store] <type>: <name>, <summary/attrs> [accept] [reject]`.
        Returns `(cleaned_text, stored_entities, proposals)`.
        """
        stored: list[dict[str, Any]] = []
        proposals: list[dict[str, Any]] = []
        allow_direct = bool(user_msg and STORE_INTENT_RE.search(user_msg))
        pattern = re.compile(
            r"(?:```(?:xml|json|html)?\s*)?<brain_store>\s*(?:```(?:json)?\s*)?(\{.*?\})\s*(?:```\s*)?</brain_store>(?:\s*```)?",
            re.DOTALL | re.IGNORECASE,
        )

        def _replacer(match: re.Match) -> str:
            payload_str = match.group(1).strip()
            try:
                data = json.loads(payload_str)
                if isinstance(data, dict):
                    etype = str(data.get("type") or "note")
                    ename = str(data.get("name") or data.get("title") or "Saved Fact")
                    esummary = str(data.get("summary") or "")
                    eattrs = data.get("attributes") if isinstance(data.get("attributes"), dict) else {}
                    econtent = str(data.get("content") or data.get("summary") or "")
                    erels = data.get("relationships")
                    ealiases = data.get("aliases") if isinstance(data.get("aliases"), list) else []
                    esrc = str(data.get("source_url") or source_url or "")

                    if allow_direct and not self.locked:
                        ent = self.upsert_entity(
                            entity_type=etype,
                            name=ename,
                            summary=esummary,
                            attributes=eattrs,
                            content=econtent,
                            relationships=erels,
                            aliases=ealiases,
                            source_url=esrc,
                            tier=1,
                            actor="model/brain_store",
                        )
                        stored.append(ent)
                    else:
                        pid = f"prop-{secrets.token_hex(6)}"
                        prop = {
                            "proposal_id": pid,
                            "type": etype,
                            "name": ename,
                            "summary": esummary,
                            "attributes": eattrs,
                            "content": econtent,
                            "relationships": erels,
                            "aliases": ealiases,
                            "source_url": esrc,
                        }
                        with self.lock:
                            self.proposals[pid] = prop
                        proposals.append(prop)
            except Exception as e:
                print(f"[satz-brain] failed to parse <brain_store>: {e}", flush=True)
            return ""

        cleaned = pattern.sub(_replacer, raw_text).strip()
        return cleaned, stored, proposals

    def accept_proposal(self, proposal_id: str) -> dict[str, Any]:
        """POST /brain/accept {proposal_id} -> commits a pending Brain proposal to disk."""
        if self.locked:
            raise PermissionError("unlock a profile to save to your Brain")
        with self.lock:
            prop = self.proposals.pop(proposal_id, None)
            if not prop:
                raise KeyError(f"Proposal '{proposal_id}' not found or already resolved.")
            return self.upsert_entity(
                entity_type=prop["type"],
                name=prop["name"],
                summary=prop["summary"],
                attributes=prop["attributes"],
                content=prop["content"],
                relationships=prop["relationships"],
                aliases=prop["aliases"],
                source_url=prop["source_url"],
                tier=1,
                actor="user/proposal_accept",
            )

    def scrub_pii_for_external_query(self, raw_query: str) -> str:
        """
        Strips personal identifiers (emails, street addresses, booking/order codes,
        invoice amounts, and non-public personal contact names from Brain) before
        sending a topic query to an external web search engine.
        """
        cleaned = str(raw_query or "").strip()
        if not cleaned:
            return ""
        cleaned = EMAIL_RE.sub(" ", cleaned)
        cleaned = ADDRESS_LINE_RE.sub(" ", cleaned)
        cleaned = BOOKING_OR_TRACKING_RE.sub(" ", cleaned)
        cleaned = MONEY_AMOUNT_RE.sub(" ", cleaned)

        if not self.locked:
            try:
                with self.lock:
                    reg = self._load_registry()
                entities = reg.get("entities") or {}
                for _slug, meta in entities.items():
                    etype = str(meta.get("$type") or "").lower()
                    attrs = meta.get("attributes") or {}
                    if etype == "person" and not attrs.get("public_figure"):
                        for nm in [meta.get("name"), *(meta.get("aliases") or [])]:
                            nm_s = str(nm or "").strip()
                            if len(nm_s) >= 3:
                                cleaned = re.sub(
                                    rf"\b{re.escape(nm_s)}\b",
                                    " ",
                                    cleaned,
                                    flags=re.IGNORECASE,
                                )
                    elif etype == "account":
                        em = str(attrs.get("email") or "").strip()
                        if em:
                            cleaned = cleaned.replace(em, " ")
            except Exception:
                pass

        cleaned = re.sub(r"\b(?:for|on|of|by|with|to|from)\s*$", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.;:-")
        return cleaned

    def reject_proposal(self, proposal_id: str) -> bool:
        with self.lock:
            return self.proposals.pop(proposal_id, None) is not None

    def ensure_explicit_store_fulfilled(
        self,
        user_msg: str,
        assistant_msg: str,
        sources: list[dict[str, Any]],
        already_stored: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Fallback guarantee: if the user explicitly asked to store/save/remember something
        (e.g. "store the address on this email") and the local model answered without emitting
        a <brain_store> tag, deterministically extract and store the entity in SatzBrain.
        """
        if self.locked or already_stored or not user_msg or not STORE_INTENT_RE.search(user_msg):
            return already_stored

        combined_source_text = "\n".join(
            f"{s.get('title', '')}\n{s.get('text', '')}" for s in (sources or [])
        )
        primary_url = str(sources[0].get("url") or "") if sources else ""
        primary_title = str(sources[0].get("title") or "") if sources else ""

        user_l = user_msg.lower()
        search_pool = f"{assistant_msg}\n{combined_source_text}"

        attrs: dict[str, Any] = {}
        entity_type = "note"
        entity_name = "Saved Browser Note"
        summary = ""

        # Check if user is asking to store an address
        if "address" in user_l or "location" in user_l or "where" in user_l:
            entity_type = "place"
            addr_matches = ADDRESS_LINE_RE.findall(search_pool)
            emails = EMAIL_RE.findall(search_pool)
            if addr_matches:
                best_addr = addr_matches[0].strip(" ,.;:-")
                attrs["address"] = best_addr
                entity_name = f"Address ({best_addr[:42]})"
                summary = f"Stored address from {primary_title or primary_url or 'conversation'}: {best_addr}"
            else:
                # Use assistant's extracted answer or key lines from the source
                clean_ans = assistant_msg.strip()
                attrs["address_note"] = clean_ans[:240]
                entity_name = f"Address from {primary_title[:36] or 'Email'}"
                summary = clean_ans[:200] or f"Address note from {user_msg}"
            if emails:
                attrs["associated_email"] = emails[0]
        elif "email" in user_l or "contact" in user_l or "sender" in user_l:
            entity_type = "person"
            emails = EMAIL_RE.findall(search_pool)
            if emails:
                attrs["email"] = emails[0]
                entity_name = emails[0]
                summary = f"Contact stored from {primary_title or primary_url}: {emails[0]}"
            else:
                entity_name = f"Contact ({primary_title[:36] or 'Saved'})"
                summary = assistant_msg.strip()[:200] or user_msg
        else:
            entity_type = "note"
            entity_name = re.sub(
                STORE_INTENT_RE, "", user_msg
            ).strip(" .,;:!?\"'")[:50] or "Saved Fact"
            summary = assistant_msg.strip()[:200] or user_msg

        if primary_url:
            attrs["source_url"] = primary_url
        if primary_title:
            attrs["source_title"] = primary_title

        ent = self.upsert_entity(
            entity_type=entity_type,
            name=entity_name,
            summary=summary,
            attributes=attrs,
            content=f"User request: {user_msg}\nExtracted details: {assistant_msg[:600]}",
            source_url=primary_url,
            tier=1,
            actor="harness/store_intent",
        )
        return [ent]
