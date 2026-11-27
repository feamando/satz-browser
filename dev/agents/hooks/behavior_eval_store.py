#!/usr/bin/env python3
"""Fast local capture store & throttled background-worker launcher for behavior/error telemetry."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import security_audit
from hook_common import ERROR_LOG, REPO_ROOT

DEFAULT_RAW_DB_PATH = REPO_ROOT / "dev" / "agents" / "behavior" / "raw_events.sqlite"
DEFAULT_WORKER_LOG_PATH = REPO_ROOT / "dev" / "agents" / "behavior" / "worker.log"
WORKER_SCRIPT = REPO_ROOT / "scripts" / "agent_background_worker.py"


def get_raw_db_path() -> Path:
    override = os.environ.get("SATZ_BEHAVIOR_DB_PATH", "").strip()
    if override:
        return Path(override)
    return DEFAULT_RAW_DB_PATH


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    target = db_path or get_raw_db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=2.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            harness TEXT NOT NULL,
            conv_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            prompt_text TEXT NOT NULL DEFAULT '',
            tool_name TEXT NOT NULL DEFAULT '',
            rel_paths_json TEXT NOT NULL DEFAULT '[]',
            ok INTEGER NOT NULL DEFAULT 1,
            error_text TEXT NOT NULL DEFAULT '',
            termination_reason TEXT NOT NULL DEFAULT '',
            transcript_path TEXT NOT NULL DEFAULT '',
            analyzed INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_events_analyzed ON raw_events(analyzed, ts)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS worker_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    return conn


def record_event(
    *,
    harness: str,
    conv_id: str,
    event_type: str,
    prompt_text: str = "",
    tool_name: str = "",
    rel_paths: list[str] | None = None,
    ok: bool = True,
    error_text: str = "",
    termination_reason: str = "",
    transcript_path: str = "",
    db_path: Path | None = None,
) -> int:
    """Append a normalized behavior/error telemetry event quickly and safely (scrubbed before persistence)."""
    clean_prompt = security_audit.redact_text(prompt_text) if prompt_text else ""
    clean_err = security_audit.redact_text(error_text) if error_text else ""
    clean_transcript = security_audit.redact_text(transcript_path) if transcript_path else ""
    conn = _connect(db_path)
    try:
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with conn:
            cur = conn.execute(
                """
                INSERT INTO raw_events (
                    ts, harness, conv_id, event_type, prompt_text, tool_name,
                    rel_paths_json, ok, error_text, termination_reason, transcript_path, analyzed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    now_iso,
                    harness[:32],
                    conv_id[:128],
                    event_type[:48],
                    clean_prompt[:2000],
                    tool_name[:64],
                    json.dumps((rel_paths or [])[:20], ensure_ascii=True),
                    1 if ok else 0,
                    clean_err[:1500],
                    termination_reason[:64],
                    clean_transcript[:500],
                ),
            )
            return int(cur.lastrowid or 0)
    finally:
        conn.close()


def count_unanalyzed(db_path: Path | None = None) -> int:
    target = db_path or get_raw_db_path()
    if not target.exists():
        return 0
    conn = _connect(target)
    try:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM raw_events WHERE analyzed = 0").fetchone()
        return int(row["cnt"]) if row else 0
    finally:
        conn.close()


def should_spawn_worker(
    *,
    min_new_events: int = 5,
    cooldown_seconds: int = 180,
    has_errors: bool = False,
    db_path: Path | None = None,
) -> bool:
    """Debounce detached background analysis runs across rapid turns."""
    if os.environ.get("SATZ_DISABLE_BG_WORKER") == "1":
        return False
    target = db_path or get_raw_db_path()
    if not target.exists():
        return False

    conn = _connect(target)
    try:
        row_cnt = conn.execute("SELECT COUNT(*) AS cnt FROM raw_events WHERE analyzed = 0").fetchone()
        pending = int(row_cnt["cnt"]) if row_cnt else 0
        if pending == 0:
            return False
        if not has_errors and pending < min_new_events:
            return False

        now = time.time()
        last_row = conn.execute("SELECT value FROM worker_state WHERE key = 'last_spawn_ts'").fetchone()
        if last_row:
            try:
                if (now - float(last_row["value"])) < cooldown_seconds:
                    return False
            except Exception:
                pass

        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO worker_state (key, value) VALUES ('last_spawn_ts', ?)",
                (str(now),),
            )
        return True
    finally:
        conn.close()


def spawn_background_worker() -> bool:
    """Launch scripts/agent_background_worker.py detached without blocking the caller."""
    if not WORKER_SCRIPT.is_file():
        return False
    log_path = DEFAULT_WORKER_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        log_fh = open(log_path, "a", encoding="utf-8")
    except Exception:
        log_fh = open(os.devnull, "w", encoding="utf-8")

    try:
        kwargs: dict[str, Any] = {
            "cwd": str(REPO_ROOT),
            "stdin": subprocess.DEVNULL,
            "stdout": log_fh,
            "stderr": log_fh,
            "close_fds": True,
        }
        if sys.platform == "win32":
            flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
            )
            kwargs["creationflags"] = flags
        else:
            kwargs["start_new_session"] = True

        subprocess.Popen([sys.executable, str(WORKER_SCRIPT), "run", "--quiet"], **kwargs)
        return True
    except Exception:
        return False
    finally:
        try:
            log_fh.close()
        except Exception:
            pass


def record_error_incident(
    *,
    scope: str,
    summary: str,
    root_cause: str,
    fix_ref: str = "",
    severity: str = "medium",
    error_log_path: Path | None = None,
) -> bool:
    """Append a deduplicated engineering/agent error entry to error_log.jsonl."""
    clean_summary = security_audit.redact_text(summary)
    clean_root = security_audit.redact_text(root_cause)
    env_override = os.environ.get("SATZ_ERROR_LOG_PATH", "").strip()
    target = error_log_path or (Path(env_override) if env_override else ERROR_LOG)
    target.parent.mkdir(parents=True, exist_ok=True)
    sig = hashlib.sha256(f"{scope}|{clean_summary[:200]}".encode("utf-8", errors="ignore")).hexdigest()[:10]
    err_id = f"err-auto-{sig}"

    existing_ids: set[str] = set()
    if target.is_file():
        for raw in target.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not raw.strip():
                continue
            try:
                item = json.loads(raw)
                if item.get("id"):
                    existing_ids.add(str(item["id"]))
            except Exception:
                continue

    if err_id in existing_ids:
        return False

    record = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "id": err_id,
        "scope": scope,
        "severity": severity,
        "summary": clean_summary[:400],
        "root_cause": clean_root[:500],
        "fix_ref": fix_ref,
    }
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=True) + "\n")
    return True
