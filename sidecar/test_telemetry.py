#!/usr/bin/env python3
"""Tests for per-instance local browser telemetry (`sidecar/satz_telemetry.py`)."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIDECAR_DIR = REPO_ROOT / "sidecar"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))

from satz_models import SatzSidecarRuntime, make_sidecar_server  # noqa: E402
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

    def test_hosted_sync_uploader_and_http_endpoints(self) -> None:
        received: list[dict] = []
        fail_next = {"flag": False}

        class _Collector(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length > 0 else b"{}"
                if fail_next["flag"]:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b'{"ok":false}')
                    return
                received.append(json.loads(raw.decode("utf-8")))
                self.send_response(202)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

        collector = ThreadingHTTPServer(("127.0.0.1", 0), _Collector)
        c_port = collector.server_address[1]
        c_thread = threading.Thread(target=collector.serve_forever, daemon=True)
        c_thread.start()

        with tempfile.TemporaryDirectory() as tmpd:
            sgs_root = REPO_ROOT.parent / "sgs"
            rt = SatzSidecarRuntime(sgs_root=sgs_root, store_path=Path(tmpd) / "planck_store.sqlite")
            rt.mail.pipeline.stop_worker()
            server = make_sidecar_server(rt, host="127.0.0.1", port=0, auth_token="tel-tok")
            s_port = server.server_address[1]
            s_thread = threading.Thread(target=server.serve_forever, daemon=True)
            s_thread.start()

            def _req(path: str, payload: dict | None = None):
                body = json.dumps(payload).encode("utf-8") if payload is not None else None
                req = urllib.request.Request(
                    f"http://127.0.0.1:{s_port}{path}",
                    data=body,
                    method="POST" if body is not None else "GET",
                    headers={
                        "X-Satz-Token": "tel-tok",
                        **({"Content-Type": "application/json"} if body is not None else {}),
                    },
                )
                try:
                    with urllib.request.urlopen(req, timeout=10) as r:
                        return r.status, json.loads(r.read().decode("utf-8"))
                except urllib.error.HTTPError as he:
                    return he.code, json.loads(he.read().decode("utf-8"))

            try:
                # 1. Opt-out default rejects / skips upload
                st_skip, res_skip = _req("/telemetry/sync", {})
                self.assertEqual(st_skip, 400)
                self.assertTrue(res_skip["skipped"])
                self.assertEqual(len(received), 0)

                # 2. Record scrubbed frontend event + enable opt-in hosted sync
                _req(
                    "/telemetry/event",
                    {
                        "subsystem": "frontend",
                        "event_name": "tab_open",
                        "metrics": {"api_key": "sk-secret", "email": "alice@example.com"},
                    },
                )
                st_cfg, res_cfg = _req(
                    "/telemetry/config",
                    {
                        "hosted_sync_enabled": True,
                        "hosted_endpoint": f"http://127.0.0.1:{c_port}/v1/ingest",
                    },
                )
                self.assertEqual(st_cfg, 200)
                self.assertTrue(res_cfg["instance"]["hosted_sync_enabled"])

                # 3. Flush batch advances export cursor and strips PII before wire send
                st_sync, res_sync = _req("/telemetry/sync", {"limit": 50})
                self.assertEqual(st_sync, 200)
                self.assertTrue(res_sync["ok"])
                self.assertGreaterEqual(res_sync["uploaded"], 2)
                self.assertEqual(res_sync["remaining"], 0)
                wire_dump = json.dumps(received)
                self.assertNotIn("sk-secret", wire_dump)
                self.assertNotIn("alice@example.com", wire_dump)

                st_sum, res_sum = _req("/telemetry/summary")
                self.assertEqual(st_sum, 200)
                self.assertEqual(res_sum["totals"]["unexported_events"], 0)
                self.assertTrue(res_sum["instance"].get("last_sync_at"))

                # 4. Collector 500 error preserves unexported event
                fail_next["flag"] = True
                _req("/telemetry/event", {"subsystem": "evals", "event_name": "retry_check"})
                st_err, res_err = _req("/telemetry/sync", {})
                self.assertEqual(st_err, 400)
                self.assertFalse(res_err["ok"])
                _, res_sum2 = _req("/telemetry/summary")
                self.assertEqual(res_sum2["totals"]["unexported_events"], 1)
                self.assertIn("500", res_sum2["instance"].get("last_sync_error", ""))
            finally:
                server.shutdown()
                server.server_close()
                rt.close()
                self.assertIsNone(rt.mail._conn)
                collector.shutdown()
                collector.server_close()
                collector.server_close()


if __name__ == "__main__":
    unittest.main()
