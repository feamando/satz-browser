#!/usr/bin/env python3
"""Tests for per-instance local browser telemetry (`sidecar/satz_telemetry.py`)."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIDECAR_DIR = REPO_ROOT / "sidecar"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))

from satz_telemetry import SatzTelemetryManager  # noqa: E402


class TestSatzTelemetry(unittest.TestCase):
    def test_initializes_per_instance_dev_folder_scrubs_pii_and_tracks_export_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpd:
            app_root = Path(tmpd)
            mgr = SatzTelemetryManager(app_root, app_version="0.5.0")

            self.assertTrue((app_root / "dev" / "instance.json").is_file())
            self.assertTrue((app_root / "dev" / "analytics" / "telemetry.sqlite").is_file())
            self.assertTrue((app_root / "dev" / "evals").is_dir())
            meta = mgr.get_instance_meta()
            self.assertFalse(meta["hosted_sync_enabled"])

            mgr.record(
                "chat_harness",
                "completion",
                ok=True,
                duration_ms=412.5,
                metrics={
                    "prompt": "my secret email nikita@example.com",
                    "api_key": "sk-secret123",
                    "model": "qwen2.5",
                },
            )
            mgr.record_eval_run("deterministic", cases_total=5, passed_count=4, failed_count=1, passed=False)

            batch = mgr.export_pending_batch(limit=10)
            self.assertEqual(batch["count"], 2)
            first_metrics = batch["events"][0]["metrics"]
            self.assertEqual(first_metrics["prompt"], "[redacted]")
            self.assertEqual(first_metrics["api_key"], "[redacted]")
            self.assertEqual(first_metrics["model"], "qwen2.5")

            ack = mgr.mark_exported_through(batch["max_seq"])
            self.assertEqual(ack["marked_exported"], 2)
            self.assertEqual(mgr.export_pending_batch()["count"], 0)

            summary = mgr.get_summary()
            self.assertEqual(summary["totals"]["total_events"], 2)
            self.assertEqual(summary["totals"]["error_events"], 1)
            self.assertEqual(summary["recent_evals"][0]["failed_count"], 1)

            # Confirm SQLite uses DELETE journal mode cleanly without WAL lock files
            conn = sqlite3.connect(str(mgr.db_path))
            try:
                mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
                self.assertNotEqual(mode, "wal")
            finally:
                conn.close()

    def test_rejects_insecure_hosted_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpd:
            mgr = SatzTelemetryManager(Path(tmpd))
            with self.assertRaises(ValueError):
                mgr.set_hosted_sync(enabled=True, endpoint="http://example.com/ingest")
            cfg = mgr.set_hosted_sync(enabled=True, endpoint="https://telemetry.satz.example/v1/ingest")
            self.assertTrue(cfg["instance"]["hosted_sync_enabled"])


if __name__ == "__main__":
    unittest.main()
