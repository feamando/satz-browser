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

import json
import re
import secrets
import threading
from datetime import datetime, timezone
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
    "project": "Projects",
    "note": "Notes",
    "fact": "Notes",
    "decision": "Decisions",
}

TIER1_TYPES = {"account", "person", "place", "address", "project"}

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


def _utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


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
    Section 2.4: Before prompt assembly, neutralise directive tags inside source text
    (`<brain_store>` -> `‹brain_store›`) so a page cannot plant one for the model to echo.
    """
    if not text:
        return ""
    out = re.sub(r"<\s*(/?)\s*brain_store\b([^>]*)>", r"‹\1brain_store\2›", text, flags=re.IGNORECASE)
    return out


class SatzBrain:
    """Manages the local Satz Brain knowledge graph on disk."""

    def __init__(self, brain_dir: Path):
        self.brain_dir = brain_dir
        self.lock = threading.RLock()
        self.registry_path = self.brain_dir / "registry.yaml"
        self.brain_md_path = self.brain_dir / "BRAIN.md"
        self.proposals: dict[str, dict[str, Any]] = {}
        self._ensure_layout()

    def _ensure_layout(self) -> None:
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

            # Assemble Markdown body
            body_lines: list[str] = []
            if not existing_body:
                body_lines.append(f"# {clean_name}")
                body_lines.append("")
                if effective_summary:
                    body_lines.append(effective_summary)
                    body_lines.append("")
            else:
                body_lines.append(existing_body)
                body_lines.append("")

            if merged_attrs:
                attr_block = "\n".join(f"- **{k}**: {v}" for k, v in merged_attrs.items())
                if "## Attributes" not in existing_body:
                    body_lines.append("## Attributes")
                    body_lines.append(attr_block)
                    body_lines.append("")
                else:
                    # Replace existing Attributes section or append new keys
                    for k, v in merged_attrs.items():
                        line_check = f"**{k}**:"
                        if line_check not in existing_body:
                            body_lines.append(f"- **{k}**: {v}")

            clean_content = (content or "").strip()
            if clean_content and clean_content not in existing_body:
                body_lines.append(f"## Captured Context ({today})")
                if source_url:
                    body_lines.append(f"Source: `{source_url}`")
                body_lines.append(clean_content)
                body_lines.append("")

            final_body = "\n".join(body_lines).strip()
            self._write_entity_file(abs_path, new_fm, final_body)

            reg["entities"][slug] = {
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
            self._save_registry(reg)
            self.regenerate_brain_md()

            return {
                "slug": slug,
                "type": norm_type,
                "name": clean_name,
                "path": rel_path,
                "tier": effective_tier,
                "summary": effective_summary,
                "attributes": merged_attrs,
                "updated": now_iso,
            }

    def delete_entity(self, slug: str) -> bool:
        with self.lock:
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
            return True

    def regenerate_brain_md(self) -> str:
        """
        Generates the compressed pipe-delimited BRAIN.md index following the
        PM-OS Brain / SGS-Brain two-tier format.
        """
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
                for k, v in list(attrs.items())[:4]:
                    if k == "source_url":
                        continue
                    attr_pairs.append(f"{k}:{str(v).replace('|', '/')[:60]}")
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
            return content

    def get_brain_summary(self) -> dict[str, Any]:
        with self.lock:
            reg = self._load_registry()
            brain_md = (
                self.brain_md_path.read_text(encoding="utf-8")
                if self.brain_md_path.exists()
                else self.regenerate_brain_md()
            )
            entities_out: list[dict[str, Any]] = []
            for slug, meta in sorted(
                (reg.get("entities") or {}).items(),
                key=lambda kv: str(kv[1].get("updated") or ""),
                reverse=True,
            ):
                entities_out.append(
                    {
                        "slug": slug,
                        "type": str(meta.get("$type") or "note"),
                        "name": str(meta.get("name") or slug),
                        "tier": int(meta.get("tier") or 2),
                        "summary": str(meta.get("summary") or ""),
                        "path": str(meta.get("$ref") or ""),
                        "attributes": meta.get("attributes") or {},
                        "updated": str(meta.get("updated") or ""),
                    }
                )
            return {
                "brain_dir": str(self.brain_dir),
                "brain_md": brain_md,
                "entity_count": len(entities_out),
                "entities": entities_out[:60],
            }

    def load_hot_entities(
        self,
        query: str,
        open_sources: list[dict[str, Any]] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Brain Loader: scans the user's query and open tabs for entity mentions
        or attribute overlap and loads the full entity Markdown files.
        """
        with self.lock:
            reg = self._load_registry()
            entities = reg.get("entities") or {}
            if not entities:
                return []

            search_blob = (query or "").lower()
            for src in open_sources or []:
                search_blob += " " + str(src.get("title") or "").lower()
                search_blob += " " + str(src.get("domain") or "").lower()

            query_tokens = [
                t for t in re.findall(r"[a-z0-9]{3,}", search_blob)
                if t not in {"the", "and", "for", "from", "with", "this", "that", "what", "where", "when", "give", "show", "tell"}
            ]

            scored: list[tuple[float, str, dict[str, Any]]] = []
            for slug, meta in entities.items():
                score = 0.0
                name_l = str(meta.get("name") or "").lower()
                summary_l = str(meta.get("summary") or "").lower()
                etype_l = str(meta.get("$type") or "").lower()
                attrs_str = json.dumps(meta.get("attributes") or {}, ensure_ascii=False).lower()

                if slug in search_blob or (name_l and name_l in search_blob):
                    score += 5.0
                for al in meta.get("aliases") or []:
                    if str(al).lower() in search_blob:
                        score += 4.0
                for tok in query_tokens:
                    if tok in name_l or tok in etype_l:
                        score += 2.0
                    elif tok in summary_l or tok in attrs_str:
                        score += 1.0
                if int(meta.get("tier") or 2) == 1:
                    score += 0.5

                if score > 0:
                    scored.append((score, slug, meta))

            scored.sort(key=lambda item: item[0], reverse=True)
            results: list[dict[str, Any]] = []
            for _sc, slug, meta in scored[:limit]:
                ref = meta.get("$ref")
                body_text = ""
                if ref:
                    _, body_text = self._parse_entity_file(self.brain_dir / str(ref))
                results.append(
                    {
                        "slug": slug,
                        "type": meta.get("$type") or "note",
                        "name": meta.get("name") or slug,
                        "path": ref or "",
                        "summary": meta.get("summary") or "",
                        "attributes": meta.get("attributes") or {},
                        "body": body_text[:1200],
                    }
                )
            return results

    def build_model_context(
        self,
        query: str,
        open_sources: list[dict[str, Any]] | None = None,
    ) -> str:
        """
        Builds the Brain context block injected into the model prompt:
        1. Compressed BRAIN.md index (Tier 1 & Tier 2)
        2. Hot-loaded full entity details matching the query or active tabs
        """
        with self.lock:
            reg = self._load_registry()
            entities = reg.get("entities") or {}
            if not entities:
                return (
                    "SATZ BRAIN (LOCAL KNOWLEDGE GRAPH):\n"
                    "No entities stored yet. You can store entities, addresses, contacts, accounts, "
                    "and notes into the Brain at any time using <brain_store>..."
                )

            brain_md = (
                self.brain_md_path.read_text(encoding="utf-8")
                if self.brain_md_path.exists()
                else self.regenerate_brain_md()
            )
            hot = self.load_hot_entities(query, open_sources, limit=5)

            parts = [brain_md.strip()]
            if hot:
                parts.append("\n## Hot-Loaded Brain Entities (Full Detail)")
                for h in hot:
                    attrs_json = json.dumps(h["attributes"], ensure_ascii=False) if h["attributes"] else "{}"
                    parts.append(
                        f"### [{h['type'].upper()}] {h['name']} ({h['path']})\n"
                        f"Summary: {h['summary']}\n"
                        f"Attributes: {attrs_json}\n"
                        f"{h['body']}"
                    )
            return "\n".join(parts)

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
        - Detects authenticated user accounts on known web apps (e.g. Gmail, GitHub, Outlook, Notion)
        - Extracts high-confidence email addresses/contacts in active email views
        """
        created_or_updated: list[dict[str, Any]] = []
        if not url or not domain:
            return created_or_updated

        # 1. Detect authenticated account from page title / text on major web apps
        emails_in_title = EMAIL_RE.findall(title or "")
        if "mail.google.com" in domain:
            acct_email = emails_in_title[0] if emails_in_title else ""
            acct_name = f"Gmail ({acct_email})" if acct_email else "Gmail Account"
            attrs: dict[str, Any] = {"service": "Gmail", "domain": domain, "url": url}
            if acct_email:
                attrs["email"] = acct_email
            ent = self.upsert_entity(
                entity_type="account",
                name=acct_name,
                summary=f"Authenticated Gmail session ({title[:100]})",
                attributes=attrs,
                aliases=["gmail", "google mail", "email", "my email", acct_email] if acct_email else ["gmail", "google mail", "email", "my email"],
                source_url=url,
                tier=1,
                actor="passive/browser",
            )
            created_or_updated.append(ent)
        elif any(k in domain for k in ("outlook.live.com", "outlook.office.com", "mail.proton.me")):
            acct_email = emails_in_title[0] if emails_in_title else ""
            acct_name = f"Mail ({acct_email or domain})"
            attrs = {"service": domain, "url": url}
            if acct_email:
                attrs["email"] = acct_email
            ent = self.upsert_entity(
                entity_type="account",
                name=acct_name,
                summary=f"Authenticated webmail session on {domain} ({title[:100]})",
                attributes=attrs,
                aliases=["email", "webmail", domain],
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
        pattern = re.compile(r"<brain_store>\s*(\{.*?\})\s*</brain_store>", re.DOTALL | re.IGNORECASE)

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

                    if allow_direct:
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
        if already_stored or not user_msg or not STORE_INTENT_RE.search(user_msg):
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
