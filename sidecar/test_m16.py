from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SIDECAR_DIR = Path(__file__).resolve().parent
REPO_ROOT = SIDECAR_DIR.parent
SGS_ROOT = REPO_ROOT.parent / "sgs"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))
if str(SGS_ROOT) not in sys.path:
    sys.path.insert(0, str(SGS_ROOT))

from satz_models import (
    SATZ_SIDECAR_VERSION,
    STATIC_SYSTEM_PROMPT,
    STATIC_SYSTEM_PROMPT_NO_SOURCES,
    SatzSidecarRuntime,
)


class TestM16PlatformParityAndDoctor(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="satz_m16_test_"))
        self.store_path = self.tmp / "planck_store.sqlite"
        self.runtime = SatzSidecarRuntime(
            sgs_root=SGS_ROOT,
            store_path=self.store_path,
            bookmark_interval_minutes=60.0,
        )

    def tearDown(self):
        try:
            self.runtime.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_version_and_health_device_and_doctor_roles(self):
        self.assertEqual(SATZ_SIDECAR_VERSION, "0.5.0")
        health = self.runtime.get_health()
        self.assertTrue(health["online"])
        self.assertEqual(health.get("version"), "0.5.0")
        gemma_entry = next(m for m in health["models"] if m["id"] == "gemma-4-e4b")
        self.assertIn(gemma_entry.get("device"), ("cuda", "mps", "cpu"))

        doctor = self.runtime.get_doctor()
        self.assertTrue(doctor["ok"])
        self.assertEqual(doctor["version"], "0.5.0")
        roles = {r["role"]: r for r in doctor["roles"]}
        self.assertEqual(
            set(roles.keys()),
            {"chat", "web_answer", "reader_hertz", "reader_planck", "brain_encoder"},
        )
        for r in roles.values():
            self.assertIn(r["state"], ("ready", "missing", "cpu_only"))
            self.assertIn(r["device"], ("cuda", "mps", "cpu"))

    def test_system_prompt_switches_when_sources_empty(self):
        msgs_empty = self.runtime.build_ordered_chat_messages(
            user_msg="give me my latest email",
            brain_context="",
            context_str="",
            prior_messages=[],
        )
        self.assertEqual(msgs_empty[0]["content"], STATIC_SYSTEM_PROMPT_NO_SOURCES)
        self.assertIn("NEVER invent, fabricate, or guess", msgs_empty[0]["content"])

        msgs_with_src = self.runtime.build_ordered_chat_messages(
            user_msg="give me my latest email",
            brain_context="",
            context_str="[1] OPEN TAB: mail.google.com\nSubject: Q4 Review",
            prior_messages=[],
        )
        self.assertEqual(msgs_with_src[0]["content"], STATIC_SYSTEM_PROMPT)

    def test_timeout_capture_mode_does_not_fallback_to_unauthenticated_fetch(self):
        fetch_called = []
        orig_fetch = self.runtime.web.fetch

        def _spy_fetch(url: str):
            fetch_called.append(url)
            return {"html": "<html><body>Should not be fetched</body></html>"}

        self.runtime.web.fetch = _spy_fetch
        try:
            res = self.runtime.ingest_page(
                conversation_id="conv-1",
                source_id="src-timeout-1",
                url="https://mail.google.com/mail/u/0/#inbox",
                title="Inbox",
                html=None,
                visible_text=None,
                capture_mode="timeout",
            )
            self.assertEqual(res["capture_mode"], "timeout")
            self.assertEqual(res["text_chars"], 0)
            self.assertEqual(fetch_called, [])
        finally:
            self.runtime.web.fetch = orig_fetch

    def test_mail_fixture_12_messages_structure(self):
        fixture_path = REPO_ROOT / "docs" / "smoke" / "mail_fixture" / "fixture_12.json"
        self.assertTrue(fixture_path.exists())
        items = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(len(items), 12)
        lanes = [it["expected_lane"] for it in items]
        self.assertEqual(lanes.count("orders"), 2)
        self.assertEqual(lanes.count("pings"), 4)
        self.assertEqual(lanes.count("promos"), 3)
        self.assertEqual(lanes.count("inbox"), 3)


if __name__ == "__main__":
    unittest.main()
