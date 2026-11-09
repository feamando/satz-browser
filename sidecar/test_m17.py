from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIDECAR_DIR = Path(__file__).resolve().parent
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))

from satz_models import (
    STATIC_SYSTEM_PROMPT,
    STATIC_SYSTEM_PROMPT_NO_SOURCES,
    SatzSidecarRuntime,
)


class TestM17HonestSourcesAndUnlock(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="satz_test_m17_"))
        self.store_path = self.tmp / "planck_store.sqlite"
        self.rt = SatzSidecarRuntime(
            sgs_root=SIDECAR_DIR.parent.parent / "sgs",
            store_path=self.store_path,
        )

    def tearDown(self):
        try:
            self.rt.store.db.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_timeout_sources_excluded_from_citations_and_never_fetch(self):
        # 1. Ingest a timed-out tab (0 chars) and a real DOM-captured tab
        res_empty = self.rt.ingest_page(
            conversation_id="conv-m17",
            source_id="src-empty",
            url="https://mail.example.com/inbox",
            title="Private Webmail",
            html=None,
            visible_text=None,
            capture_mode="timeout",
        )
        self.assertEqual(res_empty["capture_mode"], "timeout")
        self.assertEqual(res_empty["text_chars"], 0)

        res_dom = self.rt.ingest_page(
            conversation_id="conv-m17",
            source_id="src-dw",
            url="https://www.dw.com/en/top-stories",
            title="DW Top Stories",
            html=None,
            visible_text="Germany announces new rail investment of 42 billion euros across major corridors.",
            capture_mode="dom",
        )
        self.assertEqual(res_dom["capture_mode"], "dom")
        self.assertGreater(res_dom["text_chars"], 40)

        # 2. Assemble chat context with [src-empty, src-dw]; verify web.fetch is never called for src-empty
        with mock.patch.object(self.rt.web, "fetch") as mock_fetch:
            ctx_str, used_ids, hydrated = self.rt.assemble_chat_context(
                "What did Germany announce?",
                [
                    {
                        "id": "src-empty",
                        "url": "https://mail.example.com/inbox",
                        "title": "Private Webmail",
                        "domain": "mail.example.com",
                        "is_open_tab": True,
                    },
                    {
                        "id": "src-dw",
                        "url": "https://www.dw.com/en/top-stories",
                        "title": "DW Top Stories",
                        "domain": "dw.com",
                        "is_open_tab": True,
                    },
                ],
            )
            mock_fetch.assert_not_called()

        # Empty source is excluded from used_source_ids; src-dw becomes [1]
        self.assertEqual(used_ids, ["src-dw"])
        self.assertEqual(len(hydrated), 1)
        self.assertEqual(hydrated[0]["id"], "src-dw")
        self.assertEqual(hydrated[0]["capture_mode"], "dom")
        self.assertIn("[1] (LIVE OPEN BROWSER TAB) dw.com", ctx_str)
        self.assertNotIn("mail.example.com", ctx_str)

        # 3. When all sources are empty, build_ordered_chat_messages uses STATIC_SYSTEM_PROMPT_NO_SOURCES
        ctx_empty, used_empty, hydrated_empty = self.rt.assemble_chat_context(
            "What is the capital of Portugal?",
            [
                {
                    "id": "src-empty",
                    "url": "https://mail.example.com/inbox",
                    "title": "Private Webmail",
                    "domain": "mail.example.com",
                    "is_open_tab": True,
                }
            ],
        )
        self.assertEqual(ctx_empty, "")
        self.assertEqual(used_empty, [])
        self.assertEqual(hydrated_empty, [])
        msgs = self.rt.build_ordered_chat_messages(
            user_msg="What is the capital of Portugal?",
            brain_context="",
            context_str=ctx_empty,
            prior_messages=[],
        )
        self.assertEqual(msgs[0]["content"], STATIC_SYSTEM_PROMPT_NO_SOURCES)
        self.assertNotEqual(msgs[0]["content"], STATIC_SYSTEM_PROMPT)

    def test_keychain_touchid_unlock_roundtrip(self):
        created = self.rt.passwords.create_profile("Nikita", "123456")
        self.assertTrue(created["unlocked"])
        pid = created["active_profile_id"]
        self.assertEqual(pid, "nikita")

        # Lock profile, then unlock via keychain/Touch ID helper
        self.rt.passwords.lock_profile()
        self.assertFalse(self.rt.passwords.unlocked)

        unlocked = self.rt.passwords.unlock_with_keychain(pid)
        self.assertTrue(unlocked["unlocked"])
        self.assertEqual(unlocked["active_profile_id"], pid)


if __name__ == "__main__":
    unittest.main()
