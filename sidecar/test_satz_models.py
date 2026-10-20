"""
Unit and integration tests for Satz v0.3 sidecar (M5, M6, M7):
- Health endpoint and non-factual reader guard (M5)
- Context assembly budgets: 6,000 chars per open tab, 24,000 chars total, checked source filtering (M6)
- Ingest worker, digest, knowledge summary, pause_learning, and forget_conversation (M7)
"""

import tempfile
import unittest
from pathlib import Path

from satz_models import SatzSidecarRuntime, is_factual_question


class TestSatzSidecar(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="satz_sidecar_test_"))
        self.store_path = self.tmp / "planck_store.sqlite"
        self.runtime = SatzSidecarRuntime(
            sgs_root=Path(__file__).resolve().parent.parent.parent / "sgs",
            store_path=self.store_path,
        )

    def test_m5_health_and_non_factual_reader_guard(self):
        health = self.runtime.get_health()
        self.assertTrue(health["online"])
        model_ids = [m["id"] for m in health["models"]]
        self.assertEqual(
            model_ids,
            ["gemma-4-e4b", "planck3 (web)", "hertz (reader)", "planck (reader)"],
        )
        self.assertFalse(is_factual_question("hello how are you"))
        self.assertTrue(is_factual_question("What is the capital of Australia?"))
        guard = self.runtime.run_read("hertz (reader)", "hello how are you", [])
        self.assertEqual(
            guard["answer"],
            "hertz reads facts from sources; switch to gemma for chat",
        )

    def test_m6_context_assembly_budgets_and_checked_sources(self):
        long_open_text = "A" * 9000
        closed_text = (
            "Greenland mineral tariff negotiations reached a new stage in Copenhagen. "
            "Lawmakers debated whether the export levy should be five percent or zero percent. "
            "Environmental groups requested an extended review before any mining license is granted. "
            "Unrelated footer text about weather."
        )
        sources = [
            {
                "id": "src-open-1",
                "url": "https://dw.com/greenland",
                "title": "DW Greenland",
                "domain": "dw.com",
                "is_open_tab": True,
                "text": long_open_text,
            },
            {
                "id": "src-closed-2",
                "url": "https://reuters.com/greenland",
                "title": "Reuters Greenland",
                "domain": "reuters.com",
                "is_open_tab": False,
                "text": closed_text,
            },
        ]
        ctx, used_ids = self.runtime.assemble_chat_context(
            "What is the Greenland mineral export levy?",
            sources,
        )
        self.assertEqual(used_ids, ["src-open-1", "src-closed-2"])
        self.assertIn("[1] dw.com", ctx)
        self.assertIn("[2] reuters.com", ctx)
        # Open tab is capped at 6,000 chars of body text
        self.assertLessEqual(ctx.count("A"), 6000)
        self.assertLessEqual(len(ctx), 24000)

        # Unchecking src-open-1 removes it from used_ids
        _, used_ids_after = self.runtime.assemble_chat_context(
            "What is the Greenland mineral export levy?",
            [sources[1]],
        )
        self.assertEqual(used_ids_after, ["src-closed-2"])

    def test_m7_ingest_digest_pause_and_forget(self):
        conv_id = "conv-m7-unit"
        res = self.runtime.ingest_page(
            conversation_id=conv_id,
            source_id="src-m7-1",
            url="https://www.dw.com/en/arctic-rail",
            title="Arctic shipping corridor and Greenland ports",
            html="<html><body><article><p>Greenland port authorities announced a new Arctic shipping corridor connecting Nuuk and Reykjavik in 2026.</p><p>Cargo volume rose by 18 percent across North Atlantic terminals.</p></article></body></html>",
            dwell_seconds=30.0,
        )
        self.assertTrue(res["ok"])
        self.assertTrue(res["queued"])
        self.runtime.ingest_queue.join()

        kb = self.runtime.get_knowledge_summary()
        self.assertGreaterEqual(len(kb["passages"]), 1)
        self.assertGreaterEqual(len(kb["top_domains"]), 1)

        digest = self.runtime.get_digest()
        self.assertGreaterEqual(len(digest["items"]), 1)

        # Pause learning prevents queue growth
        self.runtime.set_pause_learning(True)
        res_paused = self.runtime.ingest_page(
            conversation_id="conv-paused",
            source_id="src-paused",
            url="https://www.bbc.com/news/test",
            title="Paused page",
            html="<html><body><p>Should not be queued into the knowledge base while pause_learning is enabled.</p></body></html>",
        )
        self.assertFalse(res_paused["queued"])
        self.assertEqual(res_paused["queue_len"], 0)
        self.runtime.set_pause_learning(False)

        # Forget removes conversation passages
        forget = self.runtime.forget_conversation(conv_id)
        self.assertTrue(forget["ok"])
        self.assertGreater(forget["deleted"], 0)
        self.assertEqual(forget["passages_after"], 0)


if __name__ == "__main__":
    unittest.main()
