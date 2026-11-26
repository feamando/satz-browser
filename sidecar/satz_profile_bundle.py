#!/usr/bin/env python3
"""
Portable Offline Profile Bundle Export, Ingest & UUID Most-Recently-Updated Merge

Produces and consumes standalone `.satzprofile` encrypted files protected solely by
the user's 6-digit PIN (Argon2id + HKDF-SHA256 `info=b"satz-profile-export-v1"` + AES-256-GCM
over zlib-compressed JSON). No source-machine OS keyring secrets are required to decrypt,
so bundles move freely offline between devices.
"""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from satz_passwords import (
    PIN_REGEX,
    _slugify_profile,
    _utc_iso,
    decrypt_portable_bundle,
    encrypt_portable_bundle,
)

# Excludes bulky re-fetchable caches (mail bodies/HTML/attachments, drive file trees, news articles).
SYNC_META_TABLES_CONFIG: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("satz_provider_categories", "category_id", ("updated_at",)),
    ("satz_provider_entries", "id", ("updated_at", "created_at")),
    ("satz_provider_suggestions", "suggestion_id", ("updated_at",)),
    ("satz_news_topics", "topic_id", ("updated_at", "created_at")),
    ("satz_news_feeds", "feed_id", ("updated_at",)),
    ("satz_news_followed_stories", "story_id", ("updated_at", "created_at")),
    ("satz_bookmarks", "bookmark_id", ("changed_at", "last_indexed_at")),
    ("satz_watches", "watch_id", ("changed_at", "last_checked_at", "created_at")),
)


def _to_epoch(val: Any) -> float:
    """Converts numeric epochs or ISO-8601 date strings to UTC float seconds."""
    if val is None or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return max(0.0, float(val))
    raw = str(val).strip()
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        iso = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, float(dt.timestamp()))
    except Exception:
        return 0.0


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    if not _table_exists(conn, table_name):
        return []
    return [str(r[1]) for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]


def _fetch_table_dicts(conn: sqlite3.Connection, table_name: str) -> list[dict[str, Any]]:
    cols = _table_columns(conn, table_name)
    if not cols:
        return []
    col_sql = ", ".join(f'"{c}"' for c in cols)
    rows = conn.execute(f'SELECT {col_sql} FROM "{table_name}"').fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({cols[i]: r[i] for i in range(len(cols))})
    return out


def _read_dir_files(root_dir: Path, *, max_file_bytes: int = 24 * 1024 * 1024) -> dict[str, dict[str, Any]]:
    """Packs regular files inside `root_dir` as relative POSIX paths -> `{b64, mtime}`."""
    files: dict[str, dict[str, Any]] = {}
    if not root_dir.exists() or not root_dir.is_dir():
        return files
    for fp in sorted(root_dir.rglob("*")):
        if not fp.is_file():
            continue
        rel = fp.relative_to(root_dir).as_posix()
        if rel.endswith(".tmp") or rel.startswith(".trash/") or rel == ".DS_Store":
            continue
        try:
            st = fp.stat()
            if st.st_size > max_file_bytes:
                continue
            raw = fp.read_bytes()
            files[rel] = {
                "b64": base64.b64encode(raw).decode("ascii"),
                "mtime": float(st.st_mtime),
            }
        except Exception:
            continue
    return files


def _frontmatter_epoch(md_bytes: bytes, fallback_mtime: float = 0.0) -> float:
    """Extracts YAML frontmatter `updated` or `created` timestamp from a Brain Markdown note."""
    try:
        text = md_bytes.decode("utf-8", errors="ignore")
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                fm_text = parts[1]
                for key in ("updated:", "created:"):
                    for line in fm_text.splitlines():
                        s = line.strip()
                        if s.startswith(key):
                            val = s[len(key) :].strip().strip('"').strip("'")
                            ts = _to_epoch(val)
                            if ts > 0.0:
                                return ts
    except Exception:
        pass
    return max(0.0, float(fallback_mtime or 0.0))


def ensure_planck_sync_triggers(conn: sqlite3.Connection) -> None:
    """Ensures `satz_meta_ts`, `satz_sync_tombstones`, and update triggers exist on `planck_store.sqlite`."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS satz_meta_ts (
            key TEXT PRIMARY KEY,
            updated_at REAL NOT NULL DEFAULT 0.0
        );
        CREATE TABLE IF NOT EXISTS satz_sync_tombstones (
            table_name TEXT NOT NULL,
            row_key TEXT NOT NULL,
            deleted_at REAL NOT NULL DEFAULT 0.0,
            PRIMARY KEY (table_name, row_key)
        );
        """
    )
    if _table_exists(conn, "satz_meta"):
        conn.execute(
            "INSERT OR IGNORE INTO satz_meta_ts (key, updated_at) SELECT key, 0.0 FROM satz_meta"
        )
        conn.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS trg_satz_meta_ai AFTER INSERT ON satz_meta
            BEGIN
                INSERT INTO satz_meta_ts (key, updated_at)
                VALUES (NEW.key, (julianday('now') - 2440587.5) * 86400.0)
                ON CONFLICT(key) DO UPDATE SET updated_at = excluded.updated_at;
                DELETE FROM satz_sync_tombstones WHERE table_name = 'satz_meta' AND row_key = NEW.key;
            END;
            CREATE TRIGGER IF NOT EXISTS trg_satz_meta_au AFTER UPDATE ON satz_meta
            BEGIN
                INSERT INTO satz_meta_ts (key, updated_at)
                VALUES (NEW.key, (julianday('now') - 2440587.5) * 86400.0)
                ON CONFLICT(key) DO UPDATE SET updated_at = excluded.updated_at;
                DELETE FROM satz_sync_tombstones WHERE table_name = 'satz_meta' AND row_key = NEW.key;
            END;
            CREATE TRIGGER IF NOT EXISTS trg_satz_meta_ad AFTER DELETE ON satz_meta
            BEGIN
                DELETE FROM satz_meta_ts WHERE key = OLD.key;
                INSERT INTO satz_sync_tombstones (table_name, row_key, deleted_at)
                VALUES ('satz_meta', OLD.key, (julianday('now') - 2440587.5) * 86400.0)
                ON CONFLICT(table_name, row_key) DO UPDATE SET deleted_at = excluded.deleted_at;
            END;
            """
        )

    for tbl, pk_col in (
        ("satz_news_topics", "topic_id"),
        ("satz_news_feeds", "feed_id"),
        ("satz_news_followed_stories", "story_id"),
        ("satz_provider_entries", "id"),
        ("satz_provider_categories", "category_id"),
        ("satz_bookmarks", "bookmark_id"),
        ("satz_watches", "watch_id"),
        ("personal", "domain"),
    ):
        if _table_exists(conn, tbl):
            conn.executescript(
                f"""
                CREATE TRIGGER IF NOT EXISTS trg_{tbl}_sync_ad AFTER DELETE ON "{tbl}"
                BEGIN
                    INSERT INTO satz_sync_tombstones (table_name, row_key, deleted_at)
                    VALUES ('{tbl}', CAST(OLD."{pk_col}" AS TEXT), (julianday('now') - 2440587.5) * 86400.0)
                    ON CONFLICT(table_name, row_key) DO UPDATE SET deleted_at = excluded.deleted_at;
                END;
                CREATE TRIGGER IF NOT EXISTS trg_{tbl}_sync_ai AFTER INSERT ON "{tbl}"
                BEGIN
                    DELETE FROM satz_sync_tombstones
                    WHERE table_name = '{tbl}' AND row_key = CAST(NEW."{pk_col}" AS TEXT);
                END;
                """
            )
    conn.commit()


def _collect_planck_store_snapshot(conn: sqlite3.Connection) -> tuple[dict[str, Any], float]:
    """Reads all portable settings & knowledge tables from a `planck_store.sqlite` connection."""
    ensure_planck_sync_triggers(conn)
    max_ts = 0.0

    ts_map = {
        str(r["key"]): float(r["updated_at"] or 0.0)
        for r in conn.execute("SELECT key, updated_at FROM satz_meta_ts").fetchall()
    }
    meta_rows: list[dict[str, Any]] = []
    for r in conn.execute("SELECT key, value FROM satz_meta").fetchall():
        k = str(r["key"])
        uts = float(ts_map.get(k, 0.0))
        max_ts = max(max_ts, uts)
        meta_rows.append({"key": k, "value": str(r["value"]), "updated_at": uts})

    tombstones = _fetch_table_dicts(conn, "satz_sync_tombstones")
    for tb in tombstones:
        max_ts = max(max_ts, _to_epoch(tb.get("deleted_at")))

    snapshot: dict[str, Any] = {
        "satz_meta": meta_rows,
        "satz_sync_tombstones": tombstones,
    }

    table_names = (
        "domains",
        "personal",
        "feedback",
        "facts",
        "passages",
        "edges",
        "queries",
        "satz_domain_visits",
        "satz_bookmarks",
        "satz_provider_categories",
        "satz_provider_entries",
        "satz_provider_suggestions",
        "satz_news_topics",
        "satz_news_feeds",
        "satz_news_followed_stories",
        "satz_news_followed_story_updates",
        "watches",
        "satz_watches",
        "satz_domain_recipes",
        "satz_skill_proposals",
    )
    for tname in table_names:
        rows = _fetch_table_dicts(conn, tname)
        snapshot[tname] = rows
        for row in rows:
            for col in ("updated_at", "changed_at", "last_success_at", "ts", "retrieved_at", "created_at"):
                if col in row:
                    max_ts = max(max_ts, _to_epoch(row.get(col)))
    return snapshot, max_ts


def _row_ts(row: dict[str, Any], ts_cols: tuple[str, ...]) -> float:
    best = 0.0
    for c in ts_cols:
        best = max(best, _to_epoch(row.get(c)))
    return best


def _upsert_row_dict(
    conn: sqlite3.Connection,
    table_name: str,
    pk_cols: tuple[str, ...],
    row: dict[str, Any],
    allowed_cols: list[str],
) -> None:
    cols = [c for c in allowed_cols if c in row]
    if not cols:
        return
    col_sql = ", ".join(f'"{c}"' for c in cols)
    ph_sql = ", ".join("?" for _ in cols)
    non_pk = [c for c in cols if c not in pk_cols]
    pk_sql = ", ".join(f'"{c}"' for c in pk_cols)
    if non_pk:
        upd_sql = ", ".join(f'"{c}" = excluded."{c}"' for c in non_pk)
        sql = (
            f'INSERT INTO "{table_name}" ({col_sql}) VALUES ({ph_sql}) '
            f'ON CONFLICT({pk_sql}) DO UPDATE SET {upd_sql}'
        )
    else:
        sql = (
            f'INSERT OR IGNORE INTO "{table_name}" ({col_sql}) VALUES ({ph_sql})'
        )
    conn.execute(sql, [row[c] for c in cols])


def _merge_keyed_table(
    conn: sqlite3.Connection,
    table_name: str,
    pk_col: str,
    ts_cols: tuple[str, ...],
    incoming_rows: list[dict[str, Any]],
    incoming_tombstones: dict[str, float],
    local_tombstones: dict[str, float],
    *,
    is_merge: bool,
    nat_key_fn: Any = None,
    sanitize_insert_fn: Any = None,
) -> None:
    """Merges a keyed settings/knowledge table taking newer `updated_at` / deletion tombstones."""
    cols = _table_columns(conn, table_name)
    if not cols:
        return

    local_rows = _fetch_table_dicts(conn, table_name)
    by_pk: dict[str, dict[str, Any]] = {str(r[pk_col]): r for r in local_rows if r.get(pk_col) is not None}
    by_nat: dict[str, str] = {}
    if callable(nat_key_fn):
        for pk_val, r in by_pk.items():
            nk = nat_key_fn(r)
            if nk:
                by_nat[nk] = pk_val

    for raw_in in incoming_rows or []:
        row = dict(raw_in)
        if pk_col not in row or row[pk_col] is None:
            continue
        in_pk = str(row[pk_col])
        in_ts = _row_ts(row, ts_cols)

        matched_pk = in_pk if in_pk in by_pk else ""
        if not matched_pk and callable(nat_key_fn):
            nk = nat_key_fn(row)
            if nk and nk in by_nat:
                matched_pk = by_nat[nk]
                row[pk_col] = by_pk[matched_pk][pk_col]

        if not matched_pk:
            # Check if deleted locally more recently
            loc_del = max(local_tombstones.get(in_pk, 0.0), 0.0)
            if is_merge and loc_del > in_ts and loc_del > 0.0:
                continue
            if callable(sanitize_insert_fn):
                row = sanitize_insert_fn(row, existing=None)
            _upsert_row_dict(conn, table_name, (pk_col,), row, cols)
            by_pk[str(row[pk_col])] = row
            if callable(nat_key_fn):
                nk = nat_key_fn(row)
                if nk:
                    by_nat[nk] = str(row[pk_col])
        else:
            loc_row = by_pk[matched_pk]
            loc_ts = _row_ts(loc_row, ts_cols)
            if in_ts > loc_ts:
                if callable(sanitize_insert_fn):
                    row = sanitize_insert_fn(row, existing=loc_row)
                _upsert_row_dict(conn, table_name, (pk_col,), row, cols)
                by_pk[matched_pk] = row

    if is_merge and incoming_tombstones:
        for del_pk, del_ts in incoming_tombstones.items():
            if del_ts <= 0.0:
                continue
            loc_row = by_pk.get(del_pk)
            loc_ts = _row_ts(loc_row, ts_cols) if loc_row is not None else 0.0
            if loc_row is not None and del_ts > loc_ts:
                conn.execute(f'DELETE FROM "{table_name}" WHERE "{pk_col}" = ?', (del_pk,))
            if del_ts >= local_tombstones.get(del_pk, 0.0):
                conn.execute(
                    """
                    INSERT INTO satz_sync_tombstones (table_name, row_key, deleted_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(table_name, row_key) DO UPDATE SET
                        deleted_at = MAX(satz_sync_tombstones.deleted_at, excluded.deleted_at)
                    """,
                    (table_name, del_pk, float(del_ts)),
                )


def _merge_satz_meta(
    conn: sqlite3.Connection,
    incoming_meta: list[dict[str, Any]],
    inc_tombstones: dict[str, float],
    loc_tombstones: dict[str, float],
    *,
    is_merge: bool,
) -> None:
    loc_rows = {
        str(r["key"]): str(r["value"])
        for r in conn.execute("SELECT key, value FROM satz_meta").fetchall()
    }
    loc_ts = {
        str(r["key"]): float(r["updated_at"] or 0.0)
        for r in conn.execute("SELECT key, updated_at FROM satz_meta_ts").fetchall()
    }
    inc_map: dict[str, tuple[str, float]] = {}
    for item in incoming_meta or []:
        k = str(item.get("key") or "")
        if not k:
            continue
        inc_map[k] = (str(item.get("value") or ""), float(item.get("updated_at") or 0.0))

    # Apply newer live entries
    for k, (val, its) in inc_map.items():
        if k in loc_rows:
            if not is_merge or its > loc_ts.get(k, 0.0):
                conn.execute(
                    "INSERT INTO satz_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (k, val),
                )
                conn.execute(
                    "INSERT INTO satz_meta_ts (key, updated_at) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET updated_at = excluded.updated_at",
                    (k, float(its)),
                )
        else:
            ldel = loc_tombstones.get(k, 0.0)
            if is_merge and ldel > its and ldel > 0.0:
                continue
            conn.execute(
                "INSERT INTO satz_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (k, val),
            )
            conn.execute(
                "INSERT INTO satz_meta_ts (key, updated_at) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET updated_at = excluded.updated_at",
                (k, float(its)),
            )

    # Apply incoming tombstones
    if inc_tombstones:
        for k, dts in inc_tombstones.items():
            if dts <= 0.0:
                continue
            if k in loc_rows and (not is_merge or dts > loc_ts.get(k, 0.0)):
                conn.execute("DELETE FROM satz_meta WHERE key = ?", (k,))
            if dts >= loc_tombstones.get(k, 0.0):
                conn.execute(
                    """
                    INSERT INTO satz_sync_tombstones (table_name, row_key, deleted_at)
                    VALUES ('satz_meta', ?, ?)
                    ON CONFLICT(table_name, row_key) DO UPDATE SET
                        deleted_at = MAX(satz_sync_tombstones.deleted_at, excluded.deleted_at)
                    """,
                    (k, float(dts)),
                )


def _merge_planck_knowledge_tables(conn: sqlite3.Connection, snap: dict[str, Any], *, is_merge: bool) -> None:
    """Merges Planck core knowledge tables (`domains`, `personal`, `feedback`, `facts`, `passages`, `edges`, `queries`, `satz_domain_visits`)."""
    # domains (domain PK)
    d_cols = _table_columns(conn, "domains")
    for r in snap.get("domains") or []:
        _upsert_row_dict(conn, "domains", ("domain",), r, d_cols)

    # feedback & edges
    f_cols = _table_columns(conn, "feedback")
    loc_fb_ts = {
        str(r["id"]): float(r["ts"] or 0.0)
        for r in conn.execute("SELECT id, ts FROM feedback").fetchall()
    }
    for r in snap.get("feedback") or []:
        rid = str(r.get("id") or "")
        its = _to_epoch(r.get("ts"))
        if rid and (rid not in loc_fb_ts or its > loc_fb_ts[rid]):
            _upsert_row_dict(conn, "feedback", ("id",), r, f_cols)

    e_cols = _table_columns(conn, "edges")
    loc_edges = {
        (str(r["src"]), str(r["dst"])): float(r["ts"] or 0.0)
        for r in conn.execute("SELECT src, dst, ts FROM edges").fetchall()
    }
    for r in snap.get("edges") or []:
        ek = (str(r.get("src") or ""), str(r.get("dst") or ""))
        its = _to_epoch(r.get("ts"))
        if ek[0] and ek[1] and (ek not in loc_edges or its > loc_edges[ek]):
            _upsert_row_dict(conn, "edges", ("src", "dst"), r, e_cols)

    # satz_domain_visits (take cumulative max)
    for r in snap.get("satz_domain_visits") or []:
        dom = str(r.get("domain") or "")
        if not dom:
            continue
        conn.execute(
            """
            INSERT INTO satz_domain_visits (domain, visits, dwell_seconds, last_visited)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(domain) DO UPDATE SET
                visits = MAX(satz_domain_visits.visits, excluded.visits),
                dwell_seconds = MAX(satz_domain_visits.dwell_seconds, excluded.dwell_seconds),
                last_visited = MAX(satz_domain_visits.last_visited, excluded.last_visited)
            """,
            (dom, int(r.get("visits") or 0), float(r.get("dwell_seconds") or 0.0), float(r.get("last_visited") or 0.0)),
        )

    # facts (natural key avoids INTEGER AUTOINCREMENT id collision across devices)
    fact_cols = [c for c in _table_columns(conn, "facts") if c != "id"]
    if fact_cols:
        loc_facts = {
            (
                str(r["question_norm"] or ""),
                str(r["entity"] or ""),
                str(r["attribute"] or ""),
                str(r["value"] or ""),
                str(r["source_url"] or ""),
            ): (int(r["id"]), float(r["retrieved_at"] or 0.0))
            for r in conn.execute(
                "SELECT id, question_norm, entity, attribute, value, source_url, retrieved_at FROM facts"
            ).fetchall()
        }
        ins_sql = f"INSERT INTO facts ({', '.join(fact_cols)}) VALUES ({', '.join('?' for _ in fact_cols)})"
        for r in snap.get("facts") or []:
            nk = (
                str(r.get("question_norm") or ""),
                str(r.get("entity") or ""),
                str(r.get("attribute") or ""),
                str(r.get("value") or ""),
                str(r.get("source_url") or ""),
            )
            its = _to_epoch(r.get("retrieved_at"))
            if nk not in loc_facts:
                conn.execute(ins_sql, [r.get(c) for c in fact_cols])
            elif its > loc_facts[nk][1]:
                upd_cols = [c for c in fact_cols if c in r]
                set_sql = ", ".join(f'"{c}" = ?' for c in upd_cols)
                conn.execute(
                    f"UPDATE facts SET {set_sql} WHERE id = ?",
                    [*[r[c] for c in upd_cols], loc_facts[nk][0]],
                )

    # passages (natural key `(url, text_norm)` prevents AUTOINCREMENT FTS rowid collision)
    pas_cols = [c for c in _table_columns(conn, "passages") if c != "id"]
    if pas_cols:
        loc_passages = {
            (str(r["url"] or ""), str(r["text_norm"] or "")): (int(r["id"]), float(r["ts"] or 0.0))
            for r in conn.execute("SELECT id, url, text_norm, ts FROM passages").fetchall()
        }
        ins_sql = f"INSERT INTO passages ({', '.join(pas_cols)}) VALUES ({', '.join('?' for _ in pas_cols)})"
        for r in snap.get("passages") or []:
            nk = (str(r.get("url") or ""), str(r.get("text_norm") or ""))
            its = _to_epoch(r.get("ts"))
            if nk not in loc_passages:
                conn.execute(ins_sql, [r.get(c) for c in pas_cols])
            elif is_merge and its > loc_passages[nk][1]:
                upd_cols = [c for c in pas_cols if c in r]
                set_sql = ", ".join(f'"{c}" = ?' for c in upd_cols)
                conn.execute(
                    f"UPDATE passages SET {set_sql} WHERE id = ?",
                    [*[r[c] for c in upd_cols], loc_passages[nk][0]],
                )

    # queries (natural key `(question, entity)`)
    q_cols = [c for c in _table_columns(conn, "queries") if c != "id"]
    if q_cols:
        loc_queries = {
            (str(r["question"] or ""), str(r["entity"] or "")): (int(r["id"]), float(r["ts"] or 0.0))
            for r in conn.execute("SELECT id, question, entity, ts FROM queries").fetchall()
        }
        ins_sql = f"INSERT INTO queries ({', '.join(q_cols)}) VALUES ({', '.join('?' for _ in q_cols)})"
        for r in snap.get("queries") or []:
            nk = (str(r.get("question") or ""), str(r.get("entity") or ""))
            its = _to_epoch(r.get("ts"))
            if nk not in loc_queries:
                conn.execute(ins_sql, [r.get(c) for c in q_cols])
            elif its > loc_queries[nk][1]:
                conn.execute(
                    "UPDATE queries SET ts = ? WHERE id = ?",
                    (its, loc_queries[nk][0]),
                )


def _merge_planck_store_conn(conn: sqlite3.Connection, snap: dict[str, Any], *, is_merge: bool) -> None:
    """Applies or UUID-merges portable `planck_store` setups, trust scores, and knowledge."""
    ensure_planck_sync_triggers(conn)

    # Index incoming & local tombstones by table -> {row_key: deleted_at}
    inc_tb: dict[str, dict[str, float]] = {}
    for item in snap.get("satz_sync_tombstones") or []:
        tname = str(item.get("table_name") or "")
        rk = str(item.get("row_key") or "")
        dts = _to_epoch(item.get("deleted_at"))
        if tname and rk:
            inc_tb.setdefault(tname, {})[rk] = max(dts, inc_tb.get(tname, {}).get(rk, 0.0))

    loc_tb: dict[str, dict[str, float]] = {}
    for row in conn.execute("SELECT table_name, row_key, deleted_at FROM satz_sync_tombstones").fetchall():
        loc_tb.setdefault(str(row["table_name"]), {})[str(row["row_key"])] = float(row["deleted_at"] or 0.0)

    _merge_satz_meta(
        conn,
        snap.get("satz_meta") or [],
        inc_tb.get("satz_meta", {}),
        loc_tb.get("satz_meta", {}),
        is_merge=is_merge,
    )

    _merge_keyed_table(
        conn,
        "personal",
        "domain",
        ("ts",),
        snap.get("personal") or [],
        inc_tb.get("personal", {}),
        loc_tb.get("personal", {}),
        is_merge=is_merge,
    )
    _merge_keyed_table(
        conn,
        "satz_provider_categories",
        "category_id",
        ("updated_at",),
        snap.get("satz_provider_categories") or [],
        inc_tb.get("satz_provider_categories", {}),
        loc_tb.get("satz_provider_categories", {}),
        is_merge=is_merge,
    )
    _merge_keyed_table(
        conn,
        "satz_provider_entries",
        "id",
        ("updated_at", "created_at"),
        snap.get("satz_provider_entries") or [],
        inc_tb.get("satz_provider_entries", {}),
        loc_tb.get("satz_provider_entries", {}),
        is_merge=is_merge,
        nat_key_fn=lambda r: f"{str(r.get('category_id') or '').lower()}::{str(r.get('provider_slug') or '').lower()}",
    )
    _merge_keyed_table(
        conn,
        "satz_provider_suggestions",
        "suggestion_id",
        ("updated_at",),
        snap.get("satz_provider_suggestions") or [],
        inc_tb.get("satz_provider_suggestions", {}),
        loc_tb.get("satz_provider_suggestions", {}),
        is_merge=is_merge,
    )
    _merge_keyed_table(
        conn,
        "satz_news_topics",
        "topic_id",
        ("updated_at", "created_at"),
        snap.get("satz_news_topics") or [],
        inc_tb.get("satz_news_topics", {}),
        loc_tb.get("satz_news_topics", {}),
        is_merge=is_merge,
        nat_key_fn=lambda r: str(r.get("name") or "").strip().lower(),
    )

    def _sanitize_feed_row(row: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
        out = dict(row)
        if existing is not None:
            # Preserve local device polling cursors while updating feed config
            for col in ("etag", "last_modified", "last_fetched_at", "last_synced_at", "sync_status", "error_count", "backoff_until"):
                if col in existing:
                    out[col] = existing[col]
        else:
            out["etag"] = None
            out["last_modified"] = None
            out["last_fetched_at"] = 0.0
            out["last_synced_at"] = 0.0
            out["sync_status"] = "pending"
            out["error_count"] = 0
            out["backoff_until"] = 0.0
        return out

    _merge_keyed_table(
        conn,
        "satz_news_feeds",
        "feed_id",
        ("updated_at",),
        snap.get("satz_news_feeds") or [],
        inc_tb.get("satz_news_feeds", {}),
        loc_tb.get("satz_news_feeds", {}),
        is_merge=is_merge,
        nat_key_fn=lambda r: str(r.get("feed_url") or "").strip().lower(),
        sanitize_insert_fn=_sanitize_feed_row,
    )
    _merge_keyed_table(
        conn,
        "satz_news_followed_stories",
        "story_id",
        ("updated_at", "created_at"),
        snap.get("satz_news_followed_stories") or [],
        inc_tb.get("satz_news_followed_stories", {}),
        loc_tb.get("satz_news_followed_stories", {}),
        is_merge=is_merge,
    )

    # Followed story updates (composite PK story_id, article_id)
    upd_cols = _table_columns(conn, "satz_news_followed_story_updates")
    if upd_cols:
        loc_upd = {
            (str(r["story_id"]), str(r["article_id"])): float(r["added_at"] or 0.0)
            for r in conn.execute("SELECT story_id, article_id, added_at FROM satz_news_followed_story_updates").fetchall()
        }
        for r in snap.get("satz_news_followed_story_updates") or []:
            k = (str(r.get("story_id") or ""), str(r.get("article_id") or ""))
            its = _to_epoch(r.get("added_at"))
            if k[0] and k[1] and (k not in loc_upd or its > loc_upd[k]):
                _upsert_row_dict(conn, "satz_news_followed_story_updates", ("story_id", "article_id"), r, upd_cols)

    def _sanitize_bookmark(row: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
        out = dict(row)
        if existing is None:
            # New machine hasn't cached page body yet; prompt re-index cleanly
            out["last_indexed_at"] = 0.0
            out["text_chars"] = 0
            out["status"] = "pending"
        return out

    _merge_keyed_table(
        conn,
        "satz_bookmarks",
        "bookmark_id",
        ("changed_at", "last_indexed_at"),
        snap.get("satz_bookmarks") or [],
        inc_tb.get("satz_bookmarks", {}),
        loc_tb.get("satz_bookmarks", {}),
        is_merge=is_merge,
        nat_key_fn=lambda r: str(r.get("url") or "").strip(),
        sanitize_insert_fn=_sanitize_bookmark,
    )
    _merge_keyed_table(
        conn,
        "satz_watches",
        "watch_id",
        ("changed_at", "last_checked_at", "created_at"),
        snap.get("satz_watches") or [],
        inc_tb.get("satz_watches", {}),
        loc_tb.get("satz_watches", {}),
        is_merge=is_merge,
    )

    # watches (INTEGER id PK; match naturally by question)
    w_cols = [c for c in _table_columns(conn, "watches") if c != "id"]
    if w_cols:
        loc_watches = {
            str(r["question"] or ""): (int(r["id"]), max(_to_epoch(r["last_checked"]), _to_epoch(r["created"])))
            for r in conn.execute("SELECT id, question, last_checked, created FROM watches").fetchall()
        }
        ins_w_sql = f"INSERT INTO watches ({', '.join(w_cols)}) VALUES ({', '.join('?' for _ in w_cols)})"
        for r in snap.get("watches") or []:
            qk = str(r.get("question") or "")
            its = max(_to_epoch(r.get("last_checked")), _to_epoch(r.get("created")))
            if qk and qk not in loc_watches:
                conn.execute(ins_w_sql, [r.get(c) for c in w_cols])
            elif qk and its > loc_watches[qk][1]:
                upd_cols = [c for c in w_cols if c in r]
                set_sql = ", ".join(f'"{c}" = ?' for c in upd_cols)
                conn.execute(
                    f"UPDATE watches SET {set_sql} WHERE id = ?",
                    [*[r[c] for c in upd_cols], loc_watches[qk][0]],
                )

    # domain recipes (composite PK domain, control_key)
    rec_cols = _table_columns(conn, "satz_domain_recipes")
    if rec_cols:
        loc_rec = {
            (str(r["domain"]), str(r["control_key"])): float(r["last_success_at"] or 0.0)
            for r in conn.execute("SELECT domain, control_key, last_success_at FROM satz_domain_recipes").fetchall()
        }
        for r in snap.get("satz_domain_recipes") or []:
            rk = (str(r.get("domain") or ""), str(r.get("control_key") or ""))
            its = _to_epoch(r.get("last_success_at"))
            if rk[0] and rk[1] and (rk not in loc_rec or its > loc_rec[rk]):
                _upsert_row_dict(conn, "satz_domain_recipes", ("domain", "control_key"), r, rec_cols)

    _merge_keyed_table(
        conn,
        "satz_skill_proposals",
        "proposal_id",
        ("updated_at", "created_at"),
        snap.get("satz_skill_proposals") or [],
        inc_tb.get("satz_skill_proposals", {}),
        loc_tb.get("satz_skill_proposals", {}),
        is_merge=is_merge,
        nat_key_fn=lambda r: str(r.get("pattern_key") or ""),
    )

    _merge_planck_knowledge_tables(conn, snap, is_merge=is_merge)
    conn.commit()


def _collect_mail_snapshot(conn: sqlite3.Connection, mail_model_dir: Path) -> tuple[dict[str, Any], float]:
    max_ts = 0.0
    ts_map: dict[str, float] = {}
    if _table_exists(conn, "mail_settings_ts"):
        ts_map = {
            str(r["key"]): float(r["updated_at"] or 0.0)
            for r in conn.execute("SELECT key, updated_at FROM mail_settings_ts").fetchall()
        }
    settings_rows: list[dict[str, Any]] = []
    if _table_exists(conn, "mail_settings"):
        for r in conn.execute("SELECT key, value FROM mail_settings").fetchall():
            k = str(r["key"])
            uts = float(ts_map.get(k, 0.0))
            max_ts = max(max_ts, uts)
            settings_rows.append({"key": k, "value": str(r["value"]), "updated_at": uts})

    accounts_rows = _fetch_table_dicts(conn, "accounts")
    for ac in accounts_rows:
        max_ts = max(max_ts, _to_epoch(ac.get("updated_at")))

    tombstones = _fetch_table_dicts(conn, "mail_sync_tombstones")
    for tb in tombstones:
        max_ts = max(max_ts, _to_epoch(tb.get("deleted_at")))

    model_files = _read_dir_files(mail_model_dir)
    for mf in model_files.values():
        max_ts = max(max_ts, float(mf.get("mtime") or 0.0))

    return {
        "mail_settings": settings_rows,
        "accounts": accounts_rows,
        "tombstones": tombstones,
        "mail_model_files": model_files,
    }, max_ts


def _merge_mail_snapshot(
    conn: sqlite3.Connection,
    mail_model_dir: Path,
    snap: dict[str, Any],
    *,
    is_merge: bool,
) -> None:
    if not snap:
        return
    inc_tb: dict[str, dict[str, float]] = {}
    for item in snap.get("tombstones") or []:
        tname = str(item.get("table_name") or "")
        rk = str(item.get("row_key") or "")
        dts = _to_epoch(item.get("deleted_at"))
        if tname and rk:
            inc_tb.setdefault(tname, {})[rk] = max(dts, inc_tb.get(tname, {}).get(rk, 0.0))

    loc_tb: dict[str, dict[str, float]] = {}
    if _table_exists(conn, "mail_sync_tombstones"):
        for r in conn.execute("SELECT table_name, row_key, deleted_at FROM mail_sync_tombstones").fetchall():
            loc_tb.setdefault(str(r["table_name"]), {})[str(r["row_key"])] = float(r["deleted_at"] or 0.0)

    # mail_settings
    if _table_exists(conn, "mail_settings"):
        loc_rows = {
            str(r["key"]): str(r["value"])
            for r in conn.execute("SELECT key, value FROM mail_settings").fetchall()
        }
        loc_ts = (
            {
                str(r["key"]): float(r["updated_at"] or 0.0)
                for r in conn.execute("SELECT key, updated_at FROM mail_settings_ts").fetchall()
            }
            if _table_exists(conn, "mail_settings_ts")
            else {}
        )
        for item in snap.get("mail_settings") or []:
            k = str(item.get("key") or "")
            if not k:
                continue
            val = str(item.get("value") or "")
            its = float(item.get("updated_at") or 0.0)
            if k in loc_rows:
                if not is_merge or its > loc_ts.get(k, 0.0):
                    conn.execute(
                        "INSERT INTO mail_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (k, val),
                    )
                    if _table_exists(conn, "mail_settings_ts"):
                        conn.execute(
                            "INSERT INTO mail_settings_ts (key, updated_at) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET updated_at = excluded.updated_at",
                            (k, float(its)),
                        )
            else:
                ldel = loc_tb.get("mail_settings", {}).get(k, 0.0)
                if is_merge and ldel > its and ldel > 0.0:
                    continue
                conn.execute(
                    "INSERT INTO mail_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (k, val),
                )
                if _table_exists(conn, "mail_settings_ts"):
                    conn.execute(
                        "INSERT INTO mail_settings_ts (key, updated_at) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET updated_at = excluded.updated_at",
                        (k, float(its)),
                    )
        for k, dts in inc_tb.get("mail_settings", {}).items():
            if dts > 0.0 and k in loc_rows and (not is_merge or dts > loc_ts.get(k, 0.0)):
                conn.execute("DELETE FROM mail_settings WHERE key = ?", (k,))

    # accounts
    acc_cols = _table_columns(conn, "accounts")
    if acc_cols:
        loc_accts = {str(r["id"]): r for r in _fetch_table_dicts(conn, "accounts")}
        by_email = {str(r.get("email") or "").strip().lower(): aid for aid, r in loc_accts.items() if r.get("email")}
        inc_accts = snap.get("accounts") or []
        msg_counts: dict[str, int] = {}
        if _table_exists(conn, "messages"):
            for r in conn.execute("SELECT account_id, COUNT(*) AS c FROM messages GROUP BY account_id").fetchall():
                msg_counts[str(r["account_id"])] = int(r["c"] or 0)

        for raw_ac in inc_accts:
            ac = dict(raw_ac)
            aid = str(ac.get("id") or "")
            if not aid:
                continue
            its = _to_epoch(ac.get("updated_at"))
            em_key = str(ac.get("email") or "").strip().lower()
            matched_id = aid if aid in loc_accts else by_email.get(em_key, "")
            if not matched_id:
                ldel = loc_tb.get("accounts", {}).get(aid, 0.0)
                if is_merge and ldel > its and ldel > 0.0:
                    continue
                # Fresh install on destination: reset last_sync_at so full inbox syncs automatically
                ac["last_sync_at"] = 0.0
                ac["last_error"] = ""
                _upsert_row_dict(conn, "accounts", ("id",), ac, acc_cols)
            else:
                loc_ac = loc_accts[matched_id]
                lts = _to_epoch(loc_ac.get("updated_at"))
                if its > lts:
                    ac["id"] = matched_id
                    if msg_counts.get(matched_id, 0) > 0:
                        ac["last_sync_at"] = loc_ac.get("last_sync_at", 0.0)
                        ac["last_error"] = loc_ac.get("last_error", "")
                    else:
                        ac["last_sync_at"] = 0.0
                        ac["last_error"] = ""
                    _upsert_row_dict(conn, "accounts", ("id",), ac, acc_cols)

        if is_merge:
            for del_id, dts in inc_tb.get("accounts", {}).items():
                loc_ac = loc_accts.get(del_id)
                if loc_ac and dts > _to_epoch(loc_ac.get("updated_at")):
                    conn.execute("DELETE FROM accounts WHERE id = ?", (del_id,))

    conn.commit()

    # mail_model files
    model_files = snap.get("mail_model_files") or {}
    if model_files:
        mail_model_dir.mkdir(parents=True, exist_ok=True)
        for rel, meta in model_files.items():
            clean_rel = Path(str(rel))
            if clean_rel.is_absolute() or ".." in clean_rel.parts:
                continue
            dest = mail_model_dir / clean_rel
            inc_mtime = float(meta.get("mtime") or 0.0)
            if dest.exists() and is_merge:
                try:
                    if dest.stat().st_mtime >= inc_mtime and inc_mtime > 0.0:
                        continue
                except OSError:
                    pass
            try:
                raw_bytes = base64.b64decode(meta.get("b64") or "")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw_bytes)
                if inc_mtime > 0.0:
                    os.utime(dest, (inc_mtime, inc_mtime))
            except Exception:
                continue


def _collect_drives_snapshot(conn: sqlite3.Connection) -> tuple[dict[str, Any], float]:
    max_ts = 0.0
    rows = _fetch_table_dicts(conn, "drive_sync_state")
    for r in rows:
        max_ts = max(max_ts, _to_epoch(r.get("updated_at")))
    tombstones = _fetch_table_dicts(conn, "drive_sync_tombstones")
    for tb in tombstones:
        max_ts = max(max_ts, _to_epoch(tb.get("deleted_at")))
    return {"drive_sync_state": rows, "tombstones": tombstones}, max_ts


def _merge_drives_snapshot(conn: sqlite3.Connection, snap: dict[str, Any], *, is_merge: bool) -> None:
    if not snap or not _table_exists(conn, "drive_sync_state"):
        return
    cols = _table_columns(conn, "drive_sync_state")
    loc_rows = {str(r["provider"]): r for r in _fetch_table_dicts(conn, "drive_sync_state")}
    inc_tb = {
        str(item.get("row_key") or ""): _to_epoch(item.get("deleted_at"))
        for item in (snap.get("tombstones") or [])
        if str(item.get("table_name") or "") == "drive_sync_state"
    }
    loc_tb = (
        {
            str(r["row_key"]): float(r["deleted_at"] or 0.0)
            for r in conn.execute("SELECT row_key, deleted_at FROM drive_sync_tombstones WHERE table_name = 'drive_sync_state'").fetchall()
        }
        if _table_exists(conn, "drive_sync_tombstones")
        else {}
    )
    item_counts: dict[str, int] = {}
    if _table_exists(conn, "drive_items"):
        for r in conn.execute("SELECT provider, COUNT(*) AS c FROM drive_items GROUP BY provider").fetchall():
            item_counts[str(r["provider"])] = int(r["c"] or 0)

    for raw_r in snap.get("drive_sync_state") or []:
        r = dict(raw_r)
        prov = str(r.get("provider") or "")
        if not prov:
            continue
        its = _to_epoch(r.get("updated_at"))
        loc_r = loc_rows.get(prov)
        if loc_r is None:
            ldel = loc_tb.get(prov, 0.0)
            if is_merge and ldel > its and ldel > 0.0:
                continue
            r["delta_token"] = ""
            r["last_synced_at"] = 0.0
            r["total_files"] = 0
            r["indexed_docs"] = 0
            r["status"] = "idle"
            r["last_error"] = ""
            _upsert_row_dict(conn, "drive_sync_state", ("provider",), r, cols)
        else:
            lts = _to_epoch(loc_r.get("updated_at"))
            if its > lts:
                if item_counts.get(prov, 0) > 0:
                    for col in ("delta_token", "last_synced_at", "total_files", "indexed_docs", "status", "last_error"):
                        r[col] = loc_r.get(col, r.get(col))
                else:
                    r["delta_token"] = ""
                    r["last_synced_at"] = 0.0
                    r["total_files"] = 0
                    r["indexed_docs"] = 0
                    r["status"] = "idle"
                    r["last_error"] = ""
                _upsert_row_dict(conn, "drive_sync_state", ("provider",), r, cols)

    if is_merge:
        for del_prov, dts in inc_tb.items():
            loc_r = loc_rows.get(del_prov)
            if loc_r and dts > _to_epoch(loc_r.get("updated_at")):
                conn.execute("DELETE FROM drive_sync_state WHERE provider = ?", (del_prov,))
    conn.commit()


def _merge_brain_directory(brain_dir: Path, brain_files: dict[str, dict[str, Any]], *, is_merge: bool) -> None:
    """Unpacks or most-recent-wins merges `brain/` Markdown notes and `registry.yaml`, then rebuilds `BRAIN.md`."""
    from satz_brain import SatzBrain, _dump_yaml, _load_yaml

    brain_dir.mkdir(parents=True, exist_ok=True)
    incoming_reg: dict[str, Any] | None = None

    if not is_merge or not (brain_dir / "registry.yaml").exists():
        # Fresh install into empty Brain directory
        for rel, meta in (brain_files or {}).items():
            clean_rel = Path(str(rel))
            if clean_rel.is_absolute() or ".." in clean_rel.parts:
                continue
            dest = brain_dir / clean_rel
            try:
                raw_bytes = base64.b64decode(meta.get("b64") or "")
            except Exception:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw_bytes)
            mtime = float(meta.get("mtime") or 0.0)
            if mtime > 0.0:
                try:
                    os.utime(dest, (mtime, mtime))
                except OSError:
                    pass
        sb = SatzBrain(brain_dir, locked=False)
        sb.regenerate_brain_md()
        sb.invalidate_summary_cache()
        return

    # UUID merge: compare per-file updated timestamps
    for rel, meta in (brain_files or {}).items():
        clean_rel = Path(str(rel))
        if clean_rel.is_absolute() or ".." in clean_rel.parts:
            continue
        rel_posix = clean_rel.as_posix()
        try:
            raw_bytes = base64.b64decode(meta.get("b64") or "")
        except Exception:
            continue
        if rel_posix == "registry.yaml":
            try:
                parsed = _load_yaml(raw_bytes.decode("utf-8", errors="ignore"))
                if isinstance(parsed, dict):
                    incoming_reg = parsed
            except Exception:
                pass
            continue
        if rel_posix == "BRAIN.md":
            # Regenerated from merged registry below
            continue

        dest = brain_dir / clean_rel
        inc_mtime = float(meta.get("mtime") or 0.0)
        inc_ts = _frontmatter_epoch(raw_bytes, fallback_mtime=inc_mtime)
        write_file = not dest.exists()
        if dest.exists():
            try:
                loc_bytes = dest.read_bytes()
                loc_ts = _frontmatter_epoch(loc_bytes, fallback_mtime=dest.stat().st_mtime)
                if inc_ts > loc_ts:
                    write_file = True
            except OSError:
                write_file = True
        if write_file:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw_bytes)
            if inc_mtime > 0.0:
                try:
                    os.utime(dest, (inc_mtime, inc_mtime))
                except OSError:
                    pass

    # Merge registry.yaml entities by newer `updated`/`created` timestamp
    sb = SatzBrain(brain_dir, locked=False)
    loc_reg = sb._load_registry(copy_for_write=True)
    if incoming_reg and isinstance(incoming_reg.get("entities"), dict):
        loc_entities: dict[str, Any] = dict(loc_reg.get("entities") or {})
        for slug, inc_entry in incoming_reg["entities"].items():
            if not isinstance(inc_entry, dict):
                continue
            loc_entry = loc_entities.get(slug)
            if not isinstance(loc_entry, dict):
                loc_entities[slug] = inc_entry
                continue
            inc_ets = max(
                _to_epoch(inc_entry.get("updated")),
                _to_epoch(inc_entry.get("created")),
            )
            loc_ets = max(
                _to_epoch(loc_entry.get("updated")),
                _to_epoch(loc_entry.get("created")),
            )
            if inc_ets > loc_ets:
                loc_entities[slug] = inc_entry
        loc_reg["entities"] = loc_entities
        sb._save_registry(loc_reg)
    sb.regenerate_brain_md()
    sb.invalidate_summary_cache()


def export_profile_bundle(
    runtime: Any,
    *,
    profile_id: str | None = None,
    pin: str | None = None,
) -> dict[str, Any]:
    """
    Exports a profile's decrypted vault + Brain + settings/knowledge setups into a standalone
    PIN-encrypted `.satzprofile` bundle (no hardware/keychain dependency).
    """
    runtime.passwords.on_progress and runtime._relay_password_progress("vault", "running", "exporting_profile")
    target_meta, env_map, vault_meta_ts, verified_pin = runtime.passwords.export_profile_vault(
        profile_id=profile_id,
        pin=pin,
    )
    pid = str(target_meta["id"])
    pdir = runtime.passwords.get_profile_dir(pid)
    brain_files = _read_dir_files(pdir / "brain")

    max_ts = max(
        _to_epoch(target_meta.get("updated_at")),
        max((float(v) for v in (vault_meta_ts.get("k") or {}).values()), default=0.0),
        max((float(v) for v in (vault_meta_ts.get("d") or {}).values()), default=0.0),
        max((float(v.get("mtime") or 0.0) for v in brain_files.values()), default=0.0),
    )

    is_active = bool(runtime.passwords.unlocked and runtime.passwords.active_profile_id == pid)
    store_path = runtime.passwords.get_profile_store_path(pid)
    planck_snap: dict[str, Any] = {}
    if is_active:
        with runtime.store_lock:
            planck_snap, pts = _collect_planck_store_snapshot(runtime.store.db)
            max_ts = max(max_ts, pts)
    elif store_path.exists():
        tmp_store = type(runtime.store)(store_path)
        try:
            runtime._init_satz_tables_on_conn(tmp_store.db)
            planck_snap, pts = _collect_planck_store_snapshot(tmp_store.db)
            max_ts = max(max_ts, pts)
        finally:
            tmp_store.close()

    mail_snap: dict[str, Any] = {}
    mail_db_path = pdir / "mail.sqlite"
    mail_model_dir = pdir / "mail_model"
    if is_active and getattr(runtime, "mail", None) is not None:
        with runtime.mail.db_lock:
            m_conn = runtime.mail._ensure_connection()
            mail_snap, mts = _collect_mail_snapshot(m_conn, mail_model_dir)
            max_ts = max(max_ts, mts)
    elif mail_db_path.exists() or mail_model_dir.exists():
        if mail_db_path.exists():
            m_conn = sqlite3.connect(str(mail_db_path), timeout=5.0)
            m_conn.row_factory = sqlite3.Row
            try:
                if getattr(runtime, "mail", None) is not None:
                    runtime.mail._init_schema(m_conn)
                mail_snap, mts = _collect_mail_snapshot(m_conn, mail_model_dir)
                max_ts = max(max_ts, mts)
            finally:
                m_conn.close()
        else:
            mail_snap = {"mail_model_files": _read_dir_files(mail_model_dir)}

    drives_snap: dict[str, Any] = {}
    drives_db_path = pdir / "drives.sqlite"
    if is_active and getattr(runtime, "drives", None) is not None:
        with runtime.drives._db_lock:
            d_conn = runtime.drives._get_conn()
            drives_snap, dts = _collect_drives_snapshot(d_conn)
            max_ts = max(max_ts, dts)
    elif drives_db_path.exists():
        d_conn = sqlite3.connect(str(drives_db_path), timeout=5.0)
        d_conn.row_factory = sqlite3.Row
        try:
            if getattr(runtime, "drives", None) is not None:
                runtime.drives._init_tables(d_conn)
            drives_snap, dts = _collect_drives_snapshot(d_conn)
            max_ts = max(max_ts, dts)
        finally:
            d_conn.close()

    eff_updated_iso = (
        datetime.fromtimestamp(max_ts, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if max_ts > 0.0
        else str(target_meta.get("updated_at") or target_meta.get("last_active_at") or target_meta.get("created_at") or _utc_iso())
    )
    bundle_obj = {
        "bundle_version": 1,
        "exported_at": _utc_iso(),
        "manifest": {
            "uuid": str(target_meta.get("uuid") or ""),
            "id": pid,
            "name": str(target_meta.get("name") or pid),
            "created_at": str(target_meta.get("created_at") or _utc_iso()),
            "updated_at": eff_updated_iso,
        },
        "vault": {
            "env": env_map,
            "meta_ts": vault_meta_ts,
        },
        "brain_files": brain_files,
        "planck_store": planck_snap,
        "mail_store": mail_snap,
        "drives_store": drives_snap,
    }
    payload_bytes = json.dumps(bundle_obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    enc_bytes = encrypt_portable_bundle(payload_bytes, verified_pin)
    runtime.passwords.on_progress and runtime._relay_password_progress("vault", "done", None)
    return {
        "profile_id": pid,
        "profile_uuid": str(target_meta.get("uuid") or ""),
        "profile_name": str(target_meta.get("name") or pid),
        "filename": f"{_slugify_profile(pid)}.satzprofile",
        "bytes_len": len(enc_bytes),
        "bundle_b64": base64.b64encode(enc_bytes).decode("ascii"),
    }


def import_profile_bundle(
    runtime: Any,
    raw_bundle_bytes: bytes,
    pin: str,
    *,
    local_pin: str = "",
    activate: bool = True,
) -> dict[str, Any]:
    """
    Decrypts an offline `.satzprofile` bundle with the user's 6-digit PIN and installs it
    as a normal local profile, or merges settings/credentials/Brain by most-recent timestamp
    if a local profile with the same UUID already exists.
    """
    clean_pin = (pin or "").strip()
    if not PIN_REGEX.match(clean_pin):
        raise ValueError("PIN must be exactly 6 digits.")

    runtime._relay_password_progress("vault", "running", "decrypting_bundle")
    plaintext_bytes = decrypt_portable_bundle(raw_bundle_bytes, clean_pin)
    try:
        bundle_obj = json.loads(plaintext_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError("Corrupted profile bundle payload.") from exc
    if not isinstance(bundle_obj, dict) or int(bundle_obj.get("bundle_version") or 0) != 1:
        raise ValueError("Unsupported profile bundle version.")

    manifest = bundle_obj.get("manifest") if isinstance(bundle_obj.get("manifest"), dict) else {}
    vault_data = bundle_obj.get("vault") if isinstance(bundle_obj.get("vault"), dict) else {}
    incoming_env = {str(k): str(v) for k, v in (vault_data.get("env") or {}).items()}
    incoming_meta_ts = vault_data.get("meta_ts") if isinstance(vault_data.get("meta_ts"), dict) else {}

    runtime._relay_password_progress("vault", "running", "merging_profile")
    prepared = runtime.passwords.prepare_profile_import(
        manifest,
        incoming_env,
        incoming_meta_ts,
        clean_pin,
        local_pin=local_pin,
    )
    pid = str(prepared["pid"])
    pdir = Path(prepared["pdir"])
    is_merge = prepared["action"] == "merge"
    is_currently_active = bool(runtime.passwords.unlocked and runtime.passwords.active_profile_id == pid)

    # 1. Unpack / merge Brain directory
    brain_files = bundle_obj.get("brain_files") if isinstance(bundle_obj.get("brain_files"), dict) else {}
    _merge_brain_directory(pdir / "brain", brain_files, is_merge=is_merge)

    # 2. Unpack / merge planck_store.sqlite
    planck_snap = bundle_obj.get("planck_store") if isinstance(bundle_obj.get("planck_store"), dict) else {}
    if planck_snap:
        if is_currently_active:
            with runtime.store_lock:
                runtime._init_satz_tables_on_conn(runtime.store.db)
                _merge_planck_store_conn(runtime.store.db, planck_snap, is_merge=is_merge)
        else:
            store_path = runtime.passwords.get_profile_store_path(pid)
            store_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_store = type(runtime.store)(store_path)
            try:
                runtime._init_satz_tables_on_conn(tmp_store.db)
                _merge_planck_store_conn(tmp_store.db, planck_snap, is_merge=is_merge)
            finally:
                tmp_store.close()

    # 3. Unpack / merge mail.sqlite + mail_model/
    mail_snap = bundle_obj.get("mail_store") if isinstance(bundle_obj.get("mail_store"), dict) else {}
    if mail_snap and getattr(runtime, "mail", None) is not None:
        mail_model_dir = pdir / "mail_model"
        if is_currently_active:
            with runtime.mail.db_lock:
                m_conn = runtime.mail._ensure_connection()
                _merge_mail_snapshot(m_conn, mail_model_dir, mail_snap, is_merge=is_merge)
        else:
            mail_db_path = pdir / "mail.sqlite"
            mail_db_path.parent.mkdir(parents=True, exist_ok=True)
            m_conn = sqlite3.connect(str(mail_db_path), timeout=5.0)
            m_conn.row_factory = sqlite3.Row
            try:
                runtime.mail._init_schema(m_conn)
                _merge_mail_snapshot(m_conn, mail_model_dir, mail_snap, is_merge=is_merge)
            finally:
                m_conn.close()

    # 4. Unpack / merge drives.sqlite
    drives_snap = bundle_obj.get("drives_store") if isinstance(bundle_obj.get("drives_store"), dict) else {}
    if drives_snap and getattr(runtime, "drives", None) is not None:
        if is_currently_active:
            with runtime.drives._db_lock:
                d_conn = runtime.drives._get_conn()
                _merge_drives_snapshot(d_conn, drives_snap, is_merge=is_merge)
        else:
            drives_db_path = pdir / "drives.sqlite"
            drives_db_path.parent.mkdir(parents=True, exist_ok=True)
            d_conn = sqlite3.connect(str(drives_db_path), timeout=5.0)
            d_conn.row_factory = sqlite3.Row
            try:
                runtime.drives._init_tables(d_conn)
                _merge_drives_snapshot(d_conn, drives_snap, is_merge=is_merge)
            finally:
                d_conn.close()

    # 5. Seal OS-bound vault.enc & unlock/refresh active runtime
    res = runtime.passwords.finalize_profile_import(prepared, activate=activate)
    runtime._relay_password_progress("vault", "done", None)
    return {
        **res,
        "import_action": prepared["action"],
        "imported_profile_id": pid,
        "imported_profile_uuid": prepared["uuid"],
        "imported_profile_name": prepared["name"],
        "unlocking": False,
    }
