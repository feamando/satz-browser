#!/usr/bin/env python3
"""Satz Development Brain Index Graph DB (`dev/brain/`).

Reuses `sidecar/satz_brain.py` (`SatzBrain`, `registry.yaml`, `BRAIN.md`,
`PlanckEncoder` semantic embeddings) combined with a committed single-file
SQLite Graph + FTS5 + Vector DB (`dev/brain/brain_index.sqlite`) covering all
artifacts under `dev/` (and `docs/design/`, `docs/evals/`).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SIDECAR_DIR = REPO_ROOT / "sidecar"
VENDOR_DIR = SIDECAR_DIR / "planck_vendor"

for p in (str(SIDECAR_DIR), str(VENDOR_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from satz_brain import SatzBrain, _load_yaml, slugify  # noqa: E402

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]


_TEXT_EXTS = {".md", ".yaml", ".yml", ".json", ".jsonl", ".py", ".ps1", ".sh", ".html", ".txt"}
_SKIP_DIR_NAMES = {"__pycache__", ".pytest_cache", ".git", "node_modules", "target"}
_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)#\s]+)(?:#[^)\s]*)?\)")
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_FTS_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{1,}")

_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    area TEXT NOT NULL,
    title TEXT NOT NULL,
    path TEXT UNIQUE NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL,
    tags TEXT NOT NULL,
    frontmatter_json TEXT NOT NULL,
    body TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    mtime REAL NOT NULL,
    size_bytes INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
CREATE INDEX IF NOT EXISTS idx_nodes_area ON nodes(area);
CREATE TABLE IF NOT EXISTS edges (
    src_id TEXT NOT NULL,
    dst_id TEXT NOT NULL,
    rel TEXT NOT NULL,
    weight REAL NOT NULL,
    PRIMARY KEY (src_id, dst_id, rel)
);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_id);
CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    id UNINDEXED,
    title,
    path,
    kind,
    area,
    summary,
    tags,
    body,
    tokenize='porter unicode61'
);
CREATE TABLE IF NOT EXISTS embeddings (
    node_id TEXT PRIMARY KEY,
    encoder TEXT NOT NULL,
    dim INTEGER NOT NULL,
    vec BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS eval_runs (
    run_id TEXT PRIMARY KEY,
    ran_at TEXT NOT NULL,
    encoder TEXT NOT NULL,
    cases_total INTEGER NOT NULL,
    hit_at_1 REAL NOT NULL,
    recall_at_3 REAL NOT NULL,
    recall_at_5 REAL NOT NULL,
    mrr REAL NOT NULL,
    term_accuracy REAL NOT NULL,
    avg_latency_ms REAL NOT NULL,
    passed INTEGER NOT NULL,
    details_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS search_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    query TEXT NOT NULL,
    top_k INTEGER NOT NULL,
    top_ids TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    encoder TEXT NOT NULL
);
"""


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pack_vec(vec: list[float] | Any) -> bytes:
    if np is not None and hasattr(vec, "tolist"):
        arr = [float(x) for x in vec.tolist()]
    else:
        arr = [float(x) for x in vec]
    norm = sum(x * x for x in arr) ** 0.5
    if norm > 1e-12:
        arr = [x / norm for x in arr]
    return struct.pack(f"<{len(arr)}f", *arr)


def _unpack_vec(blob: bytes) -> list[float]:
    n = len(blob) // 4
    if n <= 0:
        return []
    return list(struct.unpack(f"<{n}f", blob))


def _fallback_hash_embed(text: str, dim: int = 256) -> list[float]:
    vec = [0.0] * dim
    toks = re.findall(r"[a-z0-9]{2,}", (text or "").lower())
    for tok in toks:
        digest = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if (digest[4] & 1) == 0 else -1.0
        vec[idx] += sign
    norm = sum(x * x for x in vec) ** 0.5
    if norm > 1e-12:
        vec = [x / norm for x in vec]
    return vec


def _classify_node(rel_posix: str) -> tuple[str, str, str]:
    """Returns (kind, area, entity_type_for_satz_brain)."""
    if rel_posix.startswith("dev/plans/"):
        area = "plans"
        if Path(rel_posix).name.lower().startswith("tasks"):
            return "tasks", area, "project"
        return "plan", area, "project"
    if rel_posix.startswith("dev/versions/snapshots/"):
        return "snapshot", "versions", "decision"
    if rel_posix.startswith("dev/versions/"):
        return "version", "versions", "decision"
    if rel_posix.startswith("dev/docs/"):
        return "doc", "docs", "note"
    if rel_posix.startswith("dev/analytics/"):
        return "analytics", "analytics", "note"
    if rel_posix.startswith("dev/agents/hooks/"):
        return "hook", "agents/hooks", "skill"
    if rel_posix.startswith("dev/agents/skills/"):
        return "skill", "agents/skills", "skill"
    if rel_posix.startswith("dev/agents/behavior/"):
        return "behavior", "agents/behavior", "note"
    if rel_posix.startswith("dev/agents/roles/"):
        return "role", "agents/roles", "person"
    if rel_posix.startswith("dev/agents/evals/"):
        return "eval", "agents/evals", "note"
    if rel_posix.startswith("dev/agents/"):
        return "instructions", "agents", "decision"
    if rel_posix.startswith("docs/evals/"):
        return "runtime_eval", "docs/evals", "note"
    if rel_posix.startswith("docs/design/"):
        return "design", "docs/design", "note"
    return "dev_doc", "dev", "note"


def _extract_title_summary_tags(path: Path, rel_posix: str, raw: str) -> tuple[str, str, str, list[str], dict[str, Any]]:
    fm: dict[str, Any] = {}
    body = raw
    if path.suffix.lower() == ".md" and raw.lstrip().startswith("---"):
        stripped = raw.lstrip()
        parts = stripped.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = _load_yaml(parts[1]) or {}
            except Exception:
                fm = {}
            body = parts[2].strip()

    title = str(fm.get("title") or fm.get("name") or "").strip()
    if not title:
        for line in body.splitlines():
            m = re.match(r"^#\s+(.+)$", line.strip())
            if m:
                title = m.group(1).strip().strip("*")
                break
    if not title:
        if path.name in ("v1.md", "tasks.md", "SKILL.md", "README.md"):
            title = f"{path.parent.name}/{path.name}"
        else:
            title = path.stem

    status = str(fm.get("status") or "").strip()
    if not status:
        m_st = re.search(r"(?im)^\-\s+\*\*Status:\*\*\s*(.+)$", body)
        status = m_st.group(1).strip() if m_st else "active"

    summary = str(fm.get("summary") or fm.get("description") or "").strip()
    if not summary:
        for line in body.splitlines():
            clean = line.strip()
            if not clean or clean.startswith(("#", "---", "```", "|", "![", ">", "- **Plan:**")):
                continue
            summary = re.sub(r"\s+", " ", clean.lstrip("-* ").strip())[:220]
            if len(summary) >= 24:
                break
    if not summary:
        summary = f"{path.name} ({rel_posix})"

    tags: list[str] = []
    if isinstance(fm.get("tags"), list):
        tags.extend(str(x).strip() for x in fm["tags"] if str(x).strip())
    for seg in Path(rel_posix).parts[:-1]:
        if seg not in ("dev", "agents", "docs", "_template"):
            tags.append(seg.lower())
    tags.append(path.stem.lower())
    dedup_tags = list(dict.fromkeys(tags))
    return title, summary, status, dedup_tags, fm


def _resolve_rel_target(src_file: Path, target: str, repo_root: Path) -> str | None:
    if not target or target.startswith(("http://", "https://", "mailto:", "satzmail://", "file://", "#")):
        return None
    clean_tgt = target.split("#", 1)[0].split("?", 1)[0].strip()
    if not clean_tgt:
        return None
    cand = (src_file.parent / clean_tgt).resolve()
    try:
        rel = cand.relative_to(repo_root.resolve()).as_posix()
        return rel
    except ValueError:
        return None


class DevBrain:
    """Running Graph DB & SatzBrain manager over the `dev/` development workspace."""

    def __init__(self, repo_root: Path | None = None):
        self.repo_root = (repo_root or REPO_ROOT).resolve()
        self.dev_root = self.repo_root / "dev"
        self.brain_dir = self.dev_root / "brain"
        self.db_path = self.brain_dir / "brain_index.sqlite"
        self.satz_brain = SatzBrain(
            self.brain_dir,
            sgs_root=self.repo_root.parent / "sgs",
            locked=False,
        )

    def _connect(self, readonly: bool = False) -> sqlite3.Connection:
        self.brain_dir.mkdir(parents=True, exist_ok=True)
        if readonly and self.db_path.is_file():
            uri = f"{self.db_path.as_uri()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        else:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        if not readonly:
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(_DB_SCHEMA)
        return conn

    def iter_source_files(self) -> list[Path]:
        files: list[Path] = []
        roots = [self.dev_root]
        for extra in (
            self.repo_root / "docs" / "design",
            self.repo_root / "docs" / "evals",
        ):
            if extra.is_dir():
                roots.append(extra)

        brain_resolved = self.brain_dir.resolve()
        for root in roots:
            if not root.is_dir():
                continue
            for p in sorted(root.rglob("*")):
                if not p.is_file():
                    continue
                if any(part in _SKIP_DIR_NAMES for part in p.parts):
                    continue
                pr = p.resolve()
                if pr == brain_resolved or brain_resolved in pr.parents:
                    continue
                if p.suffix.lower() not in _TEXT_EXTS:
                    continue
                if p.stat().st_size > 2_000_000:
                    continue
                files.append(p)
        return files

    def _encode_batch(self, texts: list[str]) -> tuple[str, list[bytes]]:
        enc = self.satz_brain._get_encoder()
        if enc is not None and np is not None:
            enc_name = str(getattr(enc, "name", "planck"))
            try:
                vecs = enc.encode(texts).astype(np.float32)
                return enc_name, [_pack_vec(vecs[i]) for i in range(len(texts))]
            except Exception:
                pass
        return "hash-256", [_pack_vec(_fallback_hash_embed(t)) for t in texts]

    def _encode_query(self, query: str, preferred_encoder: str) -> tuple[str, list[float]]:
        if preferred_encoder != "hash-256" and np is not None:
            enc = self.satz_brain._get_encoder()
            if enc is not None:
                try:
                    vec = enc.encode([query[:512]]).astype(np.float32)[0]
                    return str(getattr(enc, "name", "planck")), _unpack_vec(_pack_vec(vec))
                except Exception:
                    pass
        return "hash-256", _fallback_hash_embed(query)

    def _discover_broken_links(self, files: list[Path]) -> list[dict[str, str]]:
        broken: list[dict[str, str]] = []
        for p in files:
            if p.suffix.lower() != ".md":
                continue
            rel_src = p.relative_to(self.repo_root).as_posix()
            raw = p.read_text(encoding="utf-8", errors="replace")
            for m in _LINK_RE.finditer(raw):
                tgt = m.group(1)
                resolved = _resolve_rel_target(p, tgt, self.repo_root)
                if not resolved:
                    continue
                full = self.repo_root / resolved
                if not full.exists():
                    broken.append({"source": rel_src, "target": tgt, "resolved": resolved})
        return broken

    def reindex(self) -> dict[str, Any]:
        files = self.iter_source_files()
        now_iso = _utc_iso()
        records: list[dict[str, Any]] = []
        path_to_id: dict[str, str] = {}
        name_to_ids: dict[str, list[str]] = {}

        for p in files:
            rel_posix = p.relative_to(self.repo_root).as_posix()
            raw = p.read_text(encoding="utf-8", errors="replace")
            st = p.stat()
            chash = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
            kind, area, brain_type = _classify_node(rel_posix)
            title, summary, status, tags, fm = _extract_title_summary_tags(p, rel_posix, raw)
            nid = rel_posix
            rec = {
                "id": nid,
                "kind": kind,
                "area": area,
                "brain_type": brain_type,
                "title": title,
                "path": rel_posix,
                "summary": summary,
                "status": status,
                "tags": tags,
                "fm": fm,
                "body": raw[:24000],
                "content_hash": chash,
                "updated_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "mtime": float(st.st_mtime),
                "size_bytes": int(st.st_size),
                "file_path": p,
                "raw": raw,
            }
            records.append(rec)
            path_to_id[rel_posix] = nid
            for alias in (
                p.name.lower(),
                p.stem.lower(),
                f"{p.parent.name}/{p.name}".lower(),
                slugify(title),
            ):
                name_to_ids.setdefault(alias, []).append(nid)

        edges: set[tuple[str, str, str, float]] = set()
        for rec in records:
            src_id = rec["id"]
            src_file: Path = rec["file_path"]
            raw = rec["raw"]

            # 1. Explicit relative Markdown links
            for m in _LINK_RE.finditer(raw):
                resolved = _resolve_rel_target(src_file, m.group(1), self.repo_root)
                if not resolved:
                    continue
                if resolved in path_to_id and path_to_id[resolved] != src_id:
                    edges.add((src_id, path_to_id[resolved], "links_to", 1.0))
                else:
                    # Directory link (e.g. "versions/" -> README inside dir)
                    readme_cand = resolved.rstrip("/") + "/README.md"
                    v1_cand = resolved.rstrip("/") + "/v1.md"
                    for dc in (readme_cand, v1_cand):
                        if dc in path_to_id and path_to_id[dc] != src_id:
                            edges.add((src_id, path_to_id[dc], "links_to", 0.9))
                            break

            # 2. [[wikilinks]] matching Satz Brain convention
            for wm in _WIKILINK_RE.finditer(raw):
                target_txt = wm.group(1).strip()
                resolved = _resolve_rel_target(src_file, target_txt, self.repo_root)
                if resolved and resolved in path_to_id and path_to_id[resolved] != src_id:
                    edges.add((src_id, path_to_id[resolved], "wikilinks", 1.0))
                else:
                    for dst_id in name_to_ids.get(target_txt.lower(), []) or name_to_ids.get(slugify(target_txt), []):
                        if dst_id != src_id:
                            edges.add((src_id, dst_id, "wikilinks", 0.95))

            # 3. Structural co-membership inside dev/plans/<slug>/
            if rec["kind"] == "tasks":
                v1_rel = str(src_file.parent.relative_to(self.repo_root).as_posix()) + "/v1.md"
                if v1_rel in path_to_id:
                    edges.add((src_id, path_to_id[v1_rel], "tasks_for", 1.0))
                    edges.add((path_to_id[v1_rel], src_id, "has_tasks", 1.0))

            # 4. Version notes <-> Plan version coupling
            m_ver = re.match(r"^dev/versions/NOTES_(v\d+\.\d+)\.md$", rec["path"])
            if m_ver:
                ver_pref = f"dev/plans/{m_ver.group(1)}-"
                for dst in records:
                    if dst["path"].startswith(ver_pref) and dst["kind"] == "plan":
                        edges.add((src_id, dst["id"], "documents_release", 1.0))
                        edges.add((dst["id"], src_id, "released_in", 1.0))

        # Encode node summaries + titles + key content cleanly in one batch
        embed_texts = [
            f"{r['title']} ({r['kind']} {r['area']}): {r['summary']} {' '.join(r['tags'])} {r['raw'][:380]}"
            for r in records
        ]
        encoder_name, embed_blobs = self._encode_batch(embed_texts) if records else ("hash-256", [])

        # Update SQLite DB cleanly in a single transaction
        conn = self._connect(readonly=False)
        try:
            with conn:
                conn.execute("DELETE FROM nodes")
                conn.execute("DELETE FROM edges")
                conn.execute("DELETE FROM nodes_fts")
                conn.execute("DELETE FROM embeddings")

                for idx, r in enumerate(records):
                    conn.execute(
                        """
                        INSERT INTO nodes (
                            id, kind, area, title, path, summary, status, tags,
                            frontmatter_json, body, content_hash, updated_at, mtime, size_bytes
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            r["id"],
                            r["kind"],
                            r["area"],
                            r["title"],
                            r["path"],
                            r["summary"],
                            r["status"],
                            json.dumps(r["tags"], ensure_ascii=False),
                            json.dumps(r["fm"], ensure_ascii=False),
                            r["body"],
                            r["content_hash"],
                            r["updated_at"],
                            r["mtime"],
                            r["size_bytes"],
                        ),
                    )
                    conn.execute(
                        "INSERT INTO nodes_fts (id, title, path, kind, area, summary, tags, body) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            r["id"],
                            r["title"],
                            r["path"],
                            r["kind"],
                            r["area"],
                            r["summary"],
                            " ".join(r["tags"]),
                            r["body"],
                        ),
                    )
                    conn.execute(
                        "INSERT INTO embeddings (node_id, encoder, dim, vec) VALUES (?, ?, ?, ?)",
                        (r["id"], encoder_name, len(embed_blobs[idx]) // 4, embed_blobs[idx]),
                    )

                for src_id, dst_id, rel, w in sorted(edges):
                    conn.execute(
                        "INSERT OR REPLACE INTO edges (src_id, dst_id, rel, weight) VALUES (?, ?, ?, ?)",
                        (src_id, dst_id, rel, w),
                    )

                for mk, mv in (
                    ("schema_version", "1"),
                    ("last_reindex_ts", now_iso),
                    ("encoder", encoder_name),
                    ("node_count", str(len(records))),
                    ("edge_count", str(len(edges))),
                ):
                    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (mk, mv))
        finally:
            conn.close()

        # Sync SatzBrain central registry.yaml + BRAIN.md + summary entity cards cleanly
        self._sync_satz_brain_registry(records, edges, now_iso)

        return {
            "ok": True,
            "nodes": len(records),
            "edges": len(edges),
            "encoder": encoder_name,
            "db_path": str(self.db_path),
        }

    def _sync_satz_brain_registry(
        self,
        records: list[dict[str, Any]],
        edges: set[tuple[str, str, str, float]],
        now_iso: str,
    ) -> None:
        out_edges: dict[str, list[str]] = {}
        for s_id, d_id, _rel, _w in edges:
            out_edges.setdefault(s_id, []).append(d_id)

        with self.satz_brain.lock:
            reg = self.satz_brain._load_registry(copy_for_write=True)
            entities: dict[str, Any] = {}
            alias_index: dict[str, str] = {}

            for r in records:
                slug = slugify(r["path"].removesuffix(".md").replace("/", "-"))
                rel_slugs = [
                    slugify(d.removesuffix(".md").replace("/", "-"))
                    for d in sorted(set(out_edges.get(r["id"], [])))[:12]
                ]
                tier = 1 if r["kind"] in ("instructions", "plan", "version", "doc", "role", "skill") else 2
                entities[slug] = {
                    "$type": r["brain_type"],
                    "name": r["title"],
                    "tier": tier,
                    "$status": r["status"],
                    "$ref": f"../{r['path'].removeprefix('dev/')}" if r["path"].startswith("dev/") else f"../../{r['path']}",
                    "summary": r["summary"][:200],
                    "aliases": [r["path"], r["title"].lower()],
                    "attributes": {
                        "dev_kind": r["kind"],
                        "area": r["area"],
                        "path": r["path"],
                        "content_hash": r["content_hash"][:12],
                    },
                    "relationships": rel_slugs,
                    "updated": now_iso,
                }
                alias_index[r["path"].lower()] = slug
                alias_index[r["title"].lower()] = slug

            reg["entities"] = entities
            reg["alias_index"] = alias_index
            reg["$updated"] = now_iso
            self.satz_brain._save_registry(reg)
        self.satz_brain.regenerate_brain_md()

    def search(
        self,
        query: str,
        *,
        kind: str | None = None,
        area: str | None = None,
        limit: int = 8,
        include_neighbors: bool = True,
        log_query: bool = False,
        exclude_paths: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.db_path.is_file():
            self.reindex()

        t0 = time.perf_counter()
        conn = self._connect(readonly=not log_query)
        try:
            q = (query or "").strip()
            filters: list[str] = []
            params: list[Any] = []
            if kind:
                filters.append("kind = ?")
                params.append(kind.strip().lower())
            if area:
                filters.append("area = ?")
                params.append(area.strip().lower())
            where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

            rows = conn.execute(
                f"SELECT id, kind, area, title, path, summary, status, tags, body FROM nodes {where_sql}",
                params,
            ).fetchall()
            if not rows:
                return []

            by_id = {
                r["id"]: dict(r)
                for r in rows
                if not exclude_paths or r["path"] not in exclude_paths
            }

            if not q:
                out = []
                for r in rows[:limit]:
                    item = {
                        "id": r["id"],
                        "kind": r["kind"],
                        "area": r["area"],
                        "title": r["title"],
                        "path": r["path"],
                        "summary": r["summary"],
                        "score": 1.0,
                        "snippet": r["summary"],
                        "neighbors": self._get_neighbors(conn, r["id"]) if include_neighbors else [],
                    }
                    out.append(item)
                return out

            # 1. BM25 via FTS5 (quoted tokens joined by OR so punctuation never breaks syntax)
            fts_tokens = _FTS_TOKEN_RE.findall(q)
            fts_scores: dict[str, float] = {}
            if fts_tokens:
                fts_expr = " OR ".join(f'"{tok.replace(chr(34), "")}"' for tok in fts_tokens[:12])
                try:
                    fts_rows = conn.execute(
                        "SELECT id, bm25(nodes_fts, 4.0, 2.5, 2.0, 1.5, 2.5, 2.0, 1.0) AS rank "
                        "FROM nodes_fts WHERE nodes_fts MATCH ? ORDER BY rank ASC LIMIT 40",
                        (fts_expr,),
                    ).fetchall()
                    for idx, fr in enumerate(fts_rows):
                        if fr["id"] in by_id:
                            # bm25 returns negative or small numbers (smaller = better in SQLite)
                            fts_scores[fr["id"]] = max(0.2, 6.0 / (1.0 + idx * 0.45))
                except sqlite3.OperationalError:
                    pass

            # 2. Semantic similarity via stored embeddings
            meta_enc_row = conn.execute("SELECT value FROM meta WHERE key = 'encoder'").fetchone()
            db_encoder = str(meta_enc_row["value"]) if meta_enc_row else "hash-256"
            _qenc, q_vec = self._encode_query(q, db_encoder)
            sem_scores: dict[str, float] = {}
            if q_vec:
                emb_rows = conn.execute("SELECT node_id, dim, vec FROM embeddings").fetchall()
                for er in emb_rows:
                    nid = er["node_id"]
                    if nid not in by_id:
                        continue
                    v = _unpack_vec(er["vec"])
                    if len(v) == len(q_vec):
                        dot = sum(a * b for a, b in zip(q_vec, v))
                        if dot > 0.0:
                            sem_scores[nid] = float(dot)

            # 3. Lexical / SatzBrain title-path-tag hybrid scoring
            q_low = q.lower()
            q_terms = [t.lower() for t in _FTS_TOKEN_RE.findall(q) if len(t) >= 2]
            scored: list[tuple[float, str]] = []
            for nid, rec in by_id.items():
                title_l = rec["title"].lower()
                path_l = rec["path"].lower()
                summary_l = rec["summary"].lower()
                tags_l = rec["tags"].lower()
                body_l = rec["body"].lower()

                sc = 0.0
                sc += fts_scores.get(nid, 0.0)
                sc += sem_scores.get(nid, 0.0) * 3.0

                if q_low in path_l or q_low in title_l:
                    sc += 5.0
                if q_low in body_l:
                    sc += 2.0

                hit_terms = 0
                for term in q_terms:
                    term_hit = False
                    if term in title_l:
                        sc += 2.2
                        term_hit = True
                    if term in path_l or term in tags_l:
                        sc += 1.6
                        term_hit = True
                    if term in summary_l:
                        sc += 1.2
                        term_hit = True
                    if term in body_l:
                        sc += 0.6
                        term_hit = True
                    if term_hit:
                        hit_terms += 1

                if q_terms:
                    sc += 3.0 * (hit_terms / len(q_terms))

                if sc > 0.35:
                    scored.append((sc, nid))

            scored.sort(key=lambda x: (-x[0], x[1]))
            top_ids = [nid for _s, nid in scored[:limit]]

            results: list[dict[str, Any]] = []
            for sc_val, nid in scored[:limit]:
                rec = by_id[nid]
                snippet = self._extract_snippet(rec["body"], q_terms, rec["summary"])
                results.append(
                    {
                        "id": nid,
                        "kind": rec["kind"],
                        "area": rec["area"],
                        "title": rec["title"],
                        "path": rec["path"],
                        "summary": rec["summary"],
                        "status": rec["status"],
                        "score": round(float(sc_val), 3),
                        "snippet": snippet,
                        "neighbors": self._get_neighbors(conn, nid) if include_neighbors else [],
                    }
                )

            if log_query:
                lat_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                with conn:
                    conn.execute(
                        "INSERT INTO search_log (ts, query, top_k, top_ids, latency_ms, encoder) VALUES (?, ?, ?, ?, ?, ?)",
                        (_utc_iso(), q, limit, json.dumps(top_ids), lat_ms, db_encoder),
                    )
            return results
        finally:
            conn.close()

    @staticmethod
    def _extract_snippet(body: str, terms: list[str], fallback: str) -> str:
        lines = [ln.strip() for ln in (body or "").splitlines() if ln.strip()]
        if not lines:
            return fallback
        scored_lines: list[tuple[int, int, str, set[str]]] = []
        for idx, ln in enumerate(lines):
            low = ln.lower()
            matched = {t for t in terms if t in low}
            if matched:
                scored_lines.append((len(matched), -idx, ln, matched))
        if not scored_lines:
            return fallback
        scored_lines.sort(reverse=True)
        picked: list[str] = []
        covered: set[str] = set()
        # First pass: prioritize lines that cover previously uncovered query terms
        for _cnt, _neg_idx, ln, matched in scored_lines:
            if len(picked) >= 5:
                break
            if matched - covered:
                picked.append(ln[:220])
                covered.update(matched)
        # Fill remaining slot if fewer than 2 lines picked
        if len(picked) < 2:
            for _cnt, _neg_idx, ln, _matched in scored_lines:
                clipped = ln[:220]
                if clipped not in picked:
                    picked.append(clipped)
                    if len(picked) >= 2:
                        break
        return " | ".join(picked)[:720]

    @staticmethod
    def _get_neighbors(conn: sqlite3.Connection, node_id: str, limit: int = 8) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT e.dst_id AS neighbor_id, e.rel AS rel, 'out' AS dir, n.title AS title, n.kind AS kind
            FROM edges e JOIN nodes n ON n.id = e.dst_id WHERE e.src_id = ?
            UNION ALL
            SELECT e.src_id AS neighbor_id, e.rel AS rel, 'in' AS dir, n.title AS title, n.kind AS kind
            FROM edges e JOIN nodes n ON n.id = e.src_id WHERE e.dst_id = ?
            LIMIT ?
            """,
            (node_id, node_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_node(self, query_id: str, depth: int = 1) -> dict[str, Any] | None:
        if not self.db_path.is_file():
            return None
        conn = self._connect(readonly=True)
        try:
            clean = query_id.strip().replace("\\", "/")
            row = conn.execute("SELECT * FROM nodes WHERE id = ? OR path = ?", (clean, clean)).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT * FROM nodes WHERE path LIKE ? ORDER BY length(path) ASC LIMIT 1",
                    (f"%{clean}%",),
                ).fetchone()
            if not row:
                return None
            out = dict(row)
            out["tags"] = json.loads(out.get("tags") or "[]")
            out["neighbors"] = self._get_neighbors(conn, row["id"], limit=20)
            if depth >= 2:
                second_hop: list[dict[str, Any]] = []
                seen = {row["id"]} | {n["neighbor_id"] for n in out["neighbors"]}
                for nb in out["neighbors"]:
                    for nb2 in self._get_neighbors(conn, nb["neighbor_id"], limit=6):
                        if nb2["neighbor_id"] not in seen:
                            seen.add(nb2["neighbor_id"])
                            second_hop.append({**nb2, "via": nb["neighbor_id"]})
                out["two_hop_neighbors"] = second_hop[:20]
            return out
        finally:
            conn.close()

    def monitor(self) -> dict[str, Any]:
        files = self.iter_source_files()
        expected = {
            p.relative_to(self.repo_root).as_posix(): hashlib.sha256(
                p.read_text(encoding="utf-8", errors="replace").encode("utf-8", errors="replace")
            ).hexdigest()
            for p in files
        }
        broken_links = self._discover_broken_links(files)

        if not self.db_path.is_file():
            return {
                "ok": False,
                "reason": "brain_index.sqlite missing",
                "disk_files": len(expected),
                "broken_edge_count": len(broken_links),
                "broken_links": broken_links[:20],
            }

        conn = self._connect(readonly=True)
        try:
            db_rows = conn.execute("SELECT id, content_hash FROM nodes").fetchall()
            db_hashes = {r["id"]: r["content_hash"] for r in db_rows}
            fts_count = int(conn.execute("SELECT COUNT(*) FROM nodes_fts").fetchone()[0])
            emb_count = int(conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0])
            edge_count = int(conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0])
            orphan_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM nodes n
                    WHERE NOT EXISTS (SELECT 1 FROM edges e WHERE e.src_id = n.id OR e.dst_id = n.id)
                    """
                ).fetchone()[0]
            )
            last_eval = conn.execute(
                "SELECT run_id, ran_at, encoder, hit_at_1, recall_at_3, recall_at_5, mrr, term_accuracy, passed "
                "FROM eval_runs ORDER BY ran_at DESC LIMIT 1"
            ).fetchone()
            meta = {
                r["key"]: r["value"]
                for r in conn.execute("SELECT key, value FROM meta").fetchall()
            }
        finally:
            conn.close()

        stale = [k for k, h in expected.items() if db_hashes.get(k) != h]
        extra = [k for k in db_hashes if k not in expected]
        fts_ok = fts_count == len(db_hashes)
        emb_ok = emb_count == len(db_hashes)
        reg_ok = (self.brain_dir / "registry.yaml").is_file() and (self.brain_dir / "BRAIN.md").is_file()
        ok = bool(len(stale) == 0 and len(extra) == 0 and fts_ok and emb_ok and reg_ok and len(broken_links) == 0)

        return {
            "ok": ok,
            "db_path": str(self.db_path),
            "encoder": meta.get("encoder", "unknown"),
            "last_reindex_ts": meta.get("last_reindex_ts", ""),
            "disk_files": len(expected),
            "nodes": len(db_hashes),
            "fts_nodes": fts_count,
            "embeddings": emb_count,
            "edges": edge_count,
            "orphan_nodes": orphan_count,
            "stale_count": len(stale),
            "stale_files": stale[:20],
            "extra_files": extra[:20],
            "broken_edge_count": len(broken_links),
            "broken_links": broken_links[:20],
            "registry_and_brain_md_ok": reg_ok,
            "latest_eval": dict(last_eval) if last_eval else None,
        }

    def evaluate(
        self,
        cases_path: Path | None = None,
        *,
        min_mrr: float = 0.70,
        min_recall5: float = 0.85,
        record: bool = False,
    ) -> dict[str, Any]:
        eval_file = cases_path or (self.dev_root / "agents" / "evals" / "dev_brain_eval_cases.json")
        cases = json.loads(eval_file.read_text(encoding="utf-8"))
        if not self.db_path.is_file():
            self.reindex()

        hit1 = 0
        rec3 = 0
        rec5 = 0
        rr_sum = 0.0
        term_hits = 0
        lat_ms_list: list[float] = []
        per_case: list[dict[str, Any]] = []

        for c in cases:
            expected = set(c.get("expected_any") or [])
            exp_terms = [str(t).lower() for t in (c.get("expected_terms") or [])]
            t0 = time.perf_counter()
            res = self.search(
                c["query"],
                limit=5,
                include_neighbors=True,
                log_query=False,
                exclude_paths={"dev/agents/evals/dev_brain_eval_cases.json"},
            )
            lat_ms = (time.perf_counter() - t0) * 1000.0
            lat_ms_list.append(lat_ms)

            got_paths = [r["path"] for r in res]
            first_rank = next((idx + 1 for idx, p in enumerate(got_paths) if p in expected), None)
            if first_rank == 1:
                hit1 += 1
            if first_rank is not None and first_rank <= 3:
                rec3 += 1
            if first_rank is not None and first_rank <= 5:
                rec5 += 1
            if first_rank is not None:
                rr_sum += 1.0 / float(first_rank)

            top3_blob = " ".join(
                f"{r['title']} {r['summary']} {r['snippet']}" for r in res[:3]
            ).lower()
            terms_ok = all(term in top3_blob for term in exp_terms) if exp_terms else True
            if terms_ok:
                term_hits += 1

            per_case.append(
                {
                    "id": c["id"],
                    "rank": first_rank,
                    "terms_ok": terms_ok,
                    "top3": got_paths[:3],
                    "latency_ms": round(lat_ms, 2),
                }
            )

        n = max(1, len(cases))
        metrics = {
            "ok": True,
            "cases_total": len(cases),
            "hit_at_1": round(hit1 / n, 4),
            "recall_at_3": round(rec3 / n, 4),
            "recall_at_5": round(rec5 / n, 4),
            "mrr": round(rr_sum / n, 4),
            "term_accuracy": round(term_hits / n, 4),
            "avg_latency_ms": round(sum(lat_ms_list) / n, 2),
            "passed": bool((rr_sum / n) >= min_mrr and (rec5 / n) >= min_recall5),
            "thresholds": {"min_mrr": min_mrr, "min_recall5": min_recall5},
            "details": per_case,
        }

        if record:
            conn = self._connect(readonly=False)
            try:
                enc_row = conn.execute("SELECT value FROM meta WHERE key = 'encoder'").fetchone()
                enc_name = str(enc_row["value"]) if enc_row else "hash-256"
                run_id = f"eval-{int(time.time())}"
                ran_at = _utc_iso()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO eval_runs (
                            run_id, ran_at, encoder, cases_total,
                            hit_at_1, recall_at_3, recall_at_5, mrr, term_accuracy,
                            avg_latency_ms, passed, details_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            ran_at,
                            enc_name,
                            metrics["cases_total"],
                            metrics["hit_at_1"],
                            metrics["recall_at_3"],
                            metrics["recall_at_5"],
                            metrics["mrr"],
                            metrics["term_accuracy"],
                            metrics["avg_latency_ms"],
                            int(metrics["passed"]),
                            json.dumps(per_case, ensure_ascii=False),
                        ),
                    )
            finally:
                conn.close()

            hist_path = self.dev_root / "analytics" / "dev_brain_eval_history.jsonl"
            hist_path.parent.mkdir(parents=True, exist_ok=True)
            row = {
                "ts": _utc_iso(),
                "encoder": enc_name,
                "cases_total": metrics["cases_total"],
                "hit_at_1": metrics["hit_at_1"],
                "recall_at_3": metrics["recall_at_3"],
                "recall_at_5": metrics["recall_at_5"],
                "mrr": metrics["mrr"],
                "term_accuracy": metrics["term_accuracy"],
                "avg_latency_ms": metrics["avg_latency_ms"],
                "passed": metrics["passed"],
            }
            with open(hist_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

        return metrics

    def capture_version_snapshot(self) -> Path:
        pkg = json.loads((self.repo_root / "package.json").read_text(encoding="utf-8"))
        tauri_cfg = json.loads((self.repo_root / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
        cargo_raw = (self.repo_root / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
        m_ver = re.search(r'(?m)^version\s*=\s*"([^"]+)"', cargo_raw)
        cargo_ver = m_ver.group(1).strip() if m_ver else ""

        def _git(args: list[str]) -> str:
            p = subprocess.run(["git", *args], cwd=str(self.repo_root), capture_output=True, text=True)
            return (p.stdout or "").strip() if p.returncode == 0 else ""

        sha = _git(["rev-parse", "--short", "HEAD"]) or "uncommitted"
        branch = _git(["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
        req_file = self.repo_root / "sidecar" / "requirements-runtime.txt"
        req_hash = hashlib.sha256(req_file.read_bytes()).hexdigest()[:16] if req_file.is_file() else ""

        planck_chunks = []
        planck_dir = self.repo_root / "sidecar" / "models" / "planck"
        if planck_dir.is_dir():
            for fp in sorted(planck_dir.rglob("*")):
                if fp.is_file():
                    planck_chunks.append(
                        {"path": fp.relative_to(self.repo_root).as_posix(), "bytes": fp.stat().st_size}
                    )

        def _file_sha256(path: Path) -> str:
            h = hashlib.sha256()
            with path.open("rb") as fh:
                while True:
                    chunk = fh.read(1024 * 1024)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()

        release_binaries: list[dict[str, Any]] = []
        rel_root = self.repo_root / "src-tauri" / "target" / "release"
        if rel_root.is_dir():
            bin_candidates: list[Path] = []
            for exe_name in ("satz-browser.exe", "satz.exe", "satz-browser", "satz"):
                ep = rel_root / exe_name
                if ep.is_file():
                    bin_candidates.append(ep)
            bundle_root = rel_root / "bundle"
            if bundle_root.is_dir():
                for bp in sorted(bundle_root.rglob("*")):
                    if bp.is_file() and bp.suffix.lower() in (".exe", ".msi", ".dmg", ".sig", ".gz", ".zip"):
                        bin_candidates.append(bp)
            for fp in bin_candidates:
                st = fp.stat()
                entry: dict[str, Any] = {
                    "path": fp.relative_to(self.repo_root).as_posix(),
                    "bytes": st.st_size,
                    "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "sha256": _file_sha256(fp),
                }
                if fp.suffix.lower() == ".sig" and st.st_size <= 2048:
                    entry["sig_preview"] = fp.read_text(encoding="utf-8", errors="replace").strip()
                release_binaries.append(entry)

        mon_snap = dict(self.monitor())
        mon_snap["db_path"] = self.db_path.relative_to(self.repo_root).as_posix()
        ver = str(pkg.get("version") or tauri_cfg.get("version") or "0.0.0")
        snap = {
            "version": ver,
            "captured_at": _utc_iso(),
            "git": {"branch": branch, "short_sha": sha},
            "manifests": {
                "package_json": pkg.get("version"),
                "tauri_conf": tauri_cfg.get("version"),
                "cargo_toml": cargo_ver,
            },
            "requirements_runtime_sha256_16": req_hash,
            "shipped_planck_files": planck_chunks,
            "release_binaries": release_binaries,
            "dev_brain_monitor": mon_snap,
        }
        snap_dir = self.dev_root / "versions" / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        out_path = snap_dir / f"v{ver}_{sha}.json"
        out_path.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        # Refresh searchable Markdown ledger under dev/versions/BINARY_RELEASES.md
        ledger_rows = [
            "# Built Binaries & Release Snapshot Ledger (`dev/versions/`)",
            "",
            "Auto-updated by `python scripts/dev_brain.py snapshot`.",
            "",
        ]
        for snap_file in sorted(snap_dir.glob("*.json"), reverse=True):
            try:
                sdata = json.loads(snap_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            bins = sdata.get("release_binaries") or []
            ledger_rows.append(
                f"## `v{sdata.get('version')}` (`{(sdata.get('git') or {}).get('short_sha')}`, captured `{sdata.get('captured_at')}`)"
            )
            ledger_rows.append(f"- Snapshot: [{snap_file.name}](snapshots/{snap_file.name})")
            if not bins:
                ledger_rows.append("- Release binaries recorded: none")
            else:
                for b in bins:
                    mb = round(float(b.get("bytes", 0)) / (1024 * 1024), 2)
                    ledger_rows.append(
                        f"- `{b.get('path')}` — `{mb} MB` (`{b.get('bytes')}` B, sha256 `{str(b.get('sha256', ''))[:16]}...`, mtime `{b.get('mtime')}`)"
                    )
            ledger_rows.append("")
        (self.dev_root / "versions" / "BINARY_RELEASES.md").write_text(
            "\n".join(ledger_rows), encoding="utf-8"
        )
        return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Satz Dev Brain Index Graph DB CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("reindex", help="Rebuild dev/brain registry, BRAIN.md, and brain_index.sqlite")

    p_search = sub.add_parser("search", help="Hybrid FTS5 + semantic + graph search across dev/")
    p_search.add_argument("query")
    p_search.add_argument("--kind", default="")
    p_search.add_argument("--area", default="")
    p_search.add_argument("--limit", type=int, default=8)
    p_search.add_argument("--neighbors", action="store_true")
    p_search.add_argument("--log", action="store_true")
    p_search.add_argument("--json", action="store_true")

    p_node = sub.add_parser("node", help="Inspect a node and its graph neighborhood")
    p_node.add_argument("target")
    p_node.add_argument("--depth", type=int, default=2)
    p_node.add_argument("--json", action="store_true")

    p_mon = sub.add_parser("monitor", help="Check graph freshness, links, FTS5 parity, and status")
    p_mon.add_argument("--json", action="store_true")

    p_eval = sub.add_parser("eval", help="Evaluate retrieval accuracy on labeled queries")
    p_eval.add_argument("--cases", default="")
    p_eval.add_argument("--min-mrr", type=float, default=0.70)
    p_eval.add_argument("--min-recall5", type=float, default=0.85)
    p_eval.add_argument("--record", action="store_true")
    p_eval.add_argument("--json", action="store_true")

    sub.add_parser("snapshot", help="Record current version snapshot into dev/versions/snapshots/ and reindex")

    args = parser.parse_args()
    brain = DevBrain(REPO_ROOT)

    if args.cmd == "reindex":
        res = brain.reindex()
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "search":
        res = brain.search(
            args.query,
            kind=args.kind or None,
            area=args.area or None,
            limit=args.limit,
            include_neighbors=args.neighbors,
            log_query=args.log,
        )
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            for idx, r in enumerate(res, 1):
                print(f"{idx}. [{r['kind']}] {r['title']} ({r['path']}) score={r['score']}")
                print(f"   {r['snippet']}")
                if r["neighbors"]:
                    nb_str = ", ".join(f"{n['rel']}->{n['neighbor_id']}" for n in r["neighbors"][:4])
                    print(f"   links: {nb_str}")
        return 0

    if args.cmd == "node":
        res = brain.get_node(args.target, depth=args.depth)
        if not res:
            print(f"Node not found: {args.target}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(f"id: {res['id']}\nkind: {res['kind']} area: {res['area']}\ntitle: {res['title']}\nsummary: {res['summary']}")
            for nb in res["neighbors"]:
                print(f"  ({nb['dir']}) {nb['rel']} -> {nb['neighbor_id']} [{nb['kind']}]")
        return 0

    if args.cmd == "monitor":
        res = brain.monitor()
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res.get("ok") else 1

    if args.cmd == "eval":
        cpath = Path(args.cases) if args.cases else None
        res = brain.evaluate(cpath, min_mrr=args.min_mrr, min_recall5=args.min_recall5, record=args.record)
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(
                f"Eval cases={res['cases_total']} hit@1={res['hit_at_1']} "
                f"recall@3={res['recall_at_3']} recall@5={res['recall_at_5']} "
                f"mrr={res['mrr']} terms={res['term_accuracy']} avg_ms={res['avg_latency_ms']} passed={res['passed']}"
            )
            for d in res["details"]:
                mark = "OK" if d["rank"] and d["terms_ok"] else "MISS"
                print(f"  [{mark}] {d['id']} rank={d['rank']} terms_ok={d['terms_ok']} top={d['top3'][0] if d['top3'] else None}")
        return 0 if res["passed"] else 1

    if args.cmd == "snapshot":
        snap_path = brain.capture_version_snapshot()
        stats = brain.reindex()
        print(json.dumps({"ok": True, "snapshot": str(snap_path), **stats}, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
