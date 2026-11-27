#!/usr/bin/env python3
"""
Per-instance local analytics & telemetry engine for Satz Browser (`<app_data_dir>/dev/`).

Creates a structured local `dev/` workspace inside each user installation's AppData directory:
- Windows: %APPDATA%\\com.satz.browser\\dev\\
- macOS:   ~/Library/Application Support/com.satz.browser/dev/
- Linux:   ~/.local/share/com.satz.browser/dev/

All metrics stay strictly local by default, scrub PII/secrets/raw content before storage,
and emit a hosted-ready envelope with sequential export cursors for future opt-in cloud ingestion.
"""

from __future__ import annotations

import json
import os
import platform
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SENSITIVE_KEYS = {
    "prompt",
    "user_msg",
    "answer",
    "bad_assistant_answer",
    "password",
    "secret",
    "token",
    "api_key",
    "cookie",
    "authorization",
    "email",
    "body",
    "raw_html",
}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
PATH_USER_RE = re.compile(r"(?:[A-Za-z]:\\Users\\|/Users/|/home/)[^\\/\s]+", re.I)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scrub_value(key: str, value: Any) -> Any:
    lk = key.lower()
    if lk in SENSITIVE_KEYS or any(sk in lk for sk in ("secret", "password", "token", "api_key")):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k): _scrub_value(str(k), v) for k, v in list(value.items())[:30]}
    if isinstance(value, list):
        return [_scrub_value(key, v) for v in value[:20]]
    if isinstance(value, str):
        cleaned = EMAIL_RE.sub("[email]", value)
        cleaned = URL_RE.sub(lambda m: m.group(0).split("/", 3)[:3][-1] if len(m.group(0).split("/")) >= 3 else "[url]", cleaned)
        cleaned = PATH_USER_RE.sub("<user_home>", cleaned)
        return cleaned[:240]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:120]


class SatzTelemetryManager:
    """Local-first per-instance browser telemetry stored under `<app_data_dir>/dev/`."""

    def __init__(self, app_data_dir: Path | str, *, app_version: str = "0.5.0") -> None:
        self.app_data_dir = Path(app_data_dir)
        self.app_version = str(app_version or "0.5.0")
        self.dev_root = self.app_data_dir / "dev"
        self.analytics_dir = self.dev_root / "analytics"
        self.evals_dir = self.dev_root / "evals"
        self.instance_path = self.dev_root / "instance.json"
        self.db_path = self.analytics_dir / "telemetry.sqlite"
        self.events_jsonl_path = self.analytics_dir / "events.jsonl"
        self._lock = threading.Lock()
        self._ensure_layout()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=3.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telemetry_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                ts TEXT NOT NULL,
                instance_id TEXT NOT NULL,
                app_version TEXT NOT NULL,
                os TEXT NOT NULL,
                subsystem TEXT NOT NULL,
                event_name TEXT NOT NULL,
                ok INTEGER NOT NULL DEFAULT 1,
                duration_ms REAL,
                error_code TEXT NOT NULL DEFAULT '',
                metrics_json TEXT NOT NULL DEFAULT '{}',
                exported INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tel_sub ON telemetry_events(subsystem, event_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tel_exp ON telemetry_events(exported, seq)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS eval_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                run_type TEXT NOT NULL,
                cases_total INTEGER NOT NULL DEFAULT 0,
                passed_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                passed INTEGER NOT NULL DEFAULT 0,
                details_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        return conn

    def _ensure_layout(self) -> None:
        with self._lock:
            self.analytics_dir.mkdir(parents=True, exist_ok=True)
            self.evals_dir.mkdir(parents=True, exist_ok=True)

            readme = self.dev_root / "README.md"
            if not readme.is_file():
                readme.write_text(
                    "# Satz Browser Instance Dev & Telemetry Folder\n\n"
                    "Created automatically per browser installation for local diagnostics, "
                    "analytics summaries, and eval tracking.\n\n"
                    "- `analytics/telemetry.sqlite` — Scrubbed local runtime & harness metrics (hosted sync disabled by default)\n"
                    "- `analytics/events.jsonl` — Inspectable JSONL telemetry tail\n"
                    "- `evals/` — Local eval snapshots & failure captures\n"
                    "- `instance.json` — Instance metadata & opt-in hosted sync preferences\n",
                    encoding="utf-8",
                )

            if not self.instance_path.is_file():
                meta = {
                    "schema_version": 1,
                    "instance_id": uuid.uuid4().hex,
                    "created_at": _utc_iso(),
                    "updated_at": _utc_iso(),
                    "app_version": self.app_version,
                    "os": platform.system().lower(),
                    "arch": platform.machine().lower(),
                    "hosted_sync_enabled": False,
                    "hosted_endpoint": "",
                }
                self.instance_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
            else:
                try:
                    meta = json.loads(self.instance_path.read_text(encoding="utf-8"))
                    if meta.get("app_version") != self.app_version:
                        meta["app_version"] = self.app_version
                        meta["updated_at"] = _utc_iso()
                        self.instance_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
                except Exception:
                    pass

            conn = self._connect()
            conn.close()

    def get_instance_meta(self) -> dict[str, Any]:
        try:
            return json.loads(self.instance_path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "schema_version": 1,
                "instance_id": "unknown",
                "app_version": self.app_version,
                "os": platform.system().lower(),
                "hosted_sync_enabled": False,
                "hosted_endpoint": "",
            }

    def record(
        self,
        subsystem: str,
        event_name: str,
        *,
        ok: bool = True,
        duration_ms: float | None = None,
        error_code: str = "",
        metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_metrics = _scrub_value("metrics", metrics or {})
        clean_err = _scrub_value("error", str(error_code or ""))
        meta = self.get_instance_meta()
        ts = _utc_iso()
        event_id = f"ev-{uuid.uuid4().hex[:16]}"
        row_payload = {
            "event_id": event_id,
            "ts": ts,
            "instance_id": str(meta.get("instance_id") or "unknown"),
            "app_version": self.app_version,
            "os": platform.system().lower(),
            "subsystem": str(subsystem or "app")[:48],
            "event_name": str(event_name or "event")[:64],
            "ok": bool(ok),
            "duration_ms": round(float(duration_ms), 2) if duration_ms is not None else None,
            "error_code": str(clean_err)[:96],
            "metrics": clean_metrics,
        }

        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    cur = conn.execute(
                        """
                        INSERT INTO telemetry_events (
                            event_id, ts, instance_id, app_version, os,
                            subsystem, event_name, ok, duration_ms, error_code, metrics_json, exported
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                        """,
                        (
                            row_payload["event_id"],
                            row_payload["ts"],
                            row_payload["instance_id"],
                            row_payload["app_version"],
                            row_payload["os"],
                            row_payload["subsystem"],
                            row_payload["event_name"],
                            1 if ok else 0,
                            row_payload["duration_ms"],
                            row_payload["error_code"],
                            json.dumps(clean_metrics, ensure_ascii=True),
                        ),
                    )
                    row_payload["seq"] = int(cur.lastrowid or 0)
            finally:
                conn.close()

            try:
                with self.events_jsonl_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row_payload, ensure_ascii=True) + "\n")
            except Exception:
                pass
        return row_payload

    def record_eval_run(
        self,
        run_type: str,
        *,
        cases_total: int,
        passed_count: int,
        failed_count: int,
        passed: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        clean_details = _scrub_value("details", details or {})
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO eval_snapshots (
                            ts, run_type, cases_total, passed_count, failed_count, passed, details_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            _utc_iso(),
                            str(run_type or "runtime")[:48],
                            int(cases_total),
                            int(passed_count),
                            int(failed_count),
                            1 if passed else 0,
                            json.dumps(clean_details, ensure_ascii=True),
                        ),
                    )
            finally:
                conn.close()
        self.record(
            "evals",
            f"eval_run_{run_type}",
            ok=passed,
            metrics={
                "cases_total": cases_total,
                "passed_count": passed_count,
                "failed_count": failed_count,
            },
        )

    def get_summary(self) -> dict[str, Any]:
        meta = self.get_instance_meta()
        with self._lock:
            conn = self._connect()
            try:
                totals = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS total_events,
                        COALESCE(SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END), 0) AS error_events,
                        COALESCE(SUM(CASE WHEN exported = 0 THEN 1 ELSE 0 END), 0) AS unexported_events
                    FROM telemetry_events
                    """
                ).fetchone()
                by_sub = conn.execute(
                    """
                    SELECT subsystem, COUNT(*) AS count,
                           COALESCE(SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END), 0) AS errors,
                           ROUND(AVG(duration_ms), 2) AS avg_duration_ms
                    FROM telemetry_events
                    GROUP BY subsystem
                    ORDER BY count DESC
                    """
                ).fetchall()
                recent_evals = conn.execute(
                    """
                    SELECT ts, run_type, cases_total, passed_count, failed_count, passed
                    FROM eval_snapshots
                    ORDER BY id DESC
                    LIMIT 5
                    """
                ).fetchall()
            finally:
                conn.close()

        return {
            "ok": True,
            "dev_dir": str(self.dev_root),
            "instance": meta,
            "totals": dict(totals) if totals else {"total_events": 0, "error_events": 0, "unexported_events": 0},
            "by_subsystem": [dict(r) for r in by_sub],
            "recent_evals": [dict(r) for r in recent_evals],
        }

    def export_pending_batch(self, *, limit: int = 200) -> dict[str, Any]:
        meta = self.get_instance_meta()
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT seq, event_id, ts, instance_id, app_version, os,
                           subsystem, event_name, ok, duration_ms, error_code, metrics_json
                    FROM telemetry_events
                    WHERE exported = 0
                    ORDER BY seq ASC
                    LIMIT ?
                    """,
                    (max(1, min(1000, int(limit))),),
                ).fetchall()
            finally:
                conn.close()

        events = []
        for r in rows:
            item = dict(r)
            item["ok"] = bool(item.get("ok"))
            try:
                item["metrics"] = json.loads(item.pop("metrics_json") or "{}")
            except Exception:
                item["metrics"] = {}
            events.append(item)

        max_seq = max((int(e["seq"]) for e in events), default=0)
        return {
            "ok": True,
            "schema_version": 1,
            "instance_id": meta.get("instance_id"),
            "app_version": self.app_version,
            "max_seq": max_seq,
            "count": len(events),
            "events": events,
        }

    def mark_exported_through(self, max_seq: int) -> dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    cur = conn.execute(
                        "UPDATE telemetry_events SET exported = 1 WHERE exported = 0 AND seq <= ?",
                        (int(max_seq),),
                    )
                    updated = int(cur.rowcount or 0)
            finally:
                conn.close()
        return {"ok": True, "marked_exported": updated, "through_seq": int(max_seq)}

    def set_hosted_sync(self, *, enabled: bool, endpoint: str = "") -> dict[str, Any]:
        ep = endpoint.strip()
        if enabled and ep and not (ep.startswith("https://") or ep.startswith("http://127.0.0.1") or ep.startswith("http://localhost")):
            raise ValueError("Hosted telemetry endpoint must use https:// (or localhost for testing).")
        with self._lock:
            meta = self.get_instance_meta()
            meta["hosted_sync_enabled"] = bool(enabled)
            if ep or not enabled:
                meta["hosted_endpoint"] = ep
            meta["updated_at"] = _utc_iso()
            self.instance_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        return {"ok": True, "instance": meta}
