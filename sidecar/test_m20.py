"""Unit and integration tests for Milestone M20 (A Brain You Can Use)."""

from __future__ import annotations

from email.message import EmailMessage
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

SIDECAR_DIR = Path(__file__).resolve().parent
REPO_ROOT = SIDECAR_DIR.parent
SGS_ROOT = REPO_ROOT.parent / "sgs"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))
if str(SGS_ROOT) not in sys.path:
    sys.path.insert(0, str(SGS_ROOT))

from satz_models import SatzSidecarRuntime


class TestM20BrainYouCanUse(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="satz_test_m20_"))
        self.store_path = self.temp_dir / "planck_store.sqlite"
        self.runtime = SatzSidecarRuntime(sgs_root=SGS_ROOT, store_path=self.store_path)
        self.runtime.mail.pipeline.stop_worker()
        self.runtime.passwords.create_profile("nikita", "123456")

        with self.runtime.mail.db_lock:
            conn = self.runtime.mail._ensure_connection()
            conn.execute(
                """
                INSERT OR REPLACE INTO accounts (
                    id, label, email, protocol, in_host, in_port, in_security,
                    smtp_host, smtp_port, smtp_security, vault_prefix, sync_days
                ) VALUES (
                    'acct-demo', 'Demo Mail', 'nikita@satz.local', 'imap',
                    '127.0.0.1', 1993, 'none', '127.0.0.1', 1587, 'none', 'DEMO', 30
                )
                """
            )
            conn.commit()

    def tearDown(self) -> None:
        try:
            self.runtime.close()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @staticmethod
    def _fixture_entry_to_raw_bytes(entry: dict) -> bytes:
        msg = EmailMessage()
        msg["Message-ID"] = entry["message_id"]
        msg["From"] = f"{entry['from_name']} <{entry['from_addr']}>"
        msg["To"] = entry.get("to_addrs", "nikita@satz.local")
        msg["Subject"] = entry["subject"]
        for hk, hv in (entry.get("headers") or {}).items():
            if hk.lower() not in ("from", "to", "subject", "message-id"):
                msg[hk] = hv
        msg.set_content(entry["text"])
        return msg.as_bytes()

    def _load_fixture_12(self) -> None:
        fixture_path = REPO_ROOT / "docs" / "smoke" / "mail_fixture" / "fixture_12.json"
        items = json.loads(fixture_path.read_text(encoding="utf-8"))
        for idx, it in enumerate(items, start=1):
            raw_b = self._fixture_entry_to_raw_bytes(it)
            mid = self.runtime.mail._store_parsed_raw_email(
                account_id="acct-demo",
                folder_name="INBOX",
                role="inbox",
                uid=int(it.get("uid") or idx),
                pop_uidl="",
                raw_bytes=raw_b,
                seen=0,
                answered=0,
                flagged=0,
            )
            if mid:
                self.runtime.mail.pipeline.process_single_message(mid)

    def test_m20_domain_trust_30_percent_hard_cap_and_conflict(self) -> None:
        """Verify domain trust sliders enforce 0.7 * system + 0.3 * personal hard cap and reset."""
        # System score for reuters.com is 7.0
        res = self.runtime.set_domain_trust("reuters.com", 0.0)
        self.assertTrue(res["ok"])
        self.assertAlmostEqual(float(res["system"]), 7.0, places=2)
        self.assertAlmostEqual(float(res["personal"]), 0.0, places=2)
        # 0.7 * 7.0 + 0.3 * 0.0 = 4.9
        self.assertAlmostEqual(float(res["effective"]), 4.9, places=2)
        self.assertTrue(bool(res["conflict"]))

        # Setting personal = 10.0 on system = 2.0 (rt.com) -> 0.7 * 2.0 + 0.3 * 10.0 = 4.4
        res_rt = self.runtime.set_domain_trust("rt.com", 10.0)
        self.assertTrue(res_rt["ok"])
        self.assertAlmostEqual(float(res_rt["system"]), 2.0, places=2)
        self.assertAlmostEqual(float(res_rt["personal"]), 10.0, places=2)
        self.assertAlmostEqual(float(res_rt["effective"]), 4.4, places=2)

        # Reset personal override
        res_reset = self.runtime.set_domain_trust("reuters.com", None)
        self.assertTrue(res_reset["ok"])
        self.assertIsNone(res_reset["personal"])
        self.assertAlmostEqual(float(res_reset["effective"]), 7.0, places=2)

    def test_m20_this_week_timeline_and_unified_brain_search(self) -> None:
        """Verify 'this week' timeline includes read pages + received mail, and search_brain queries all 3."""
        self._load_fixture_12()

        # Index a read page into the knowledge store
        self.runtime.ingest_page(
            conversation_id="conv-m20-1",
            source_id="src-zalando-policy",
            url="https://www.zalando.de/faq/shipping",
            title="Zalando Shipping Policy",
            html="<html><body><p>Zalando standard delivery via DHL takes 2 to 4 business days within Germany. Order #104099887712 is covered by free returns within 100 days.</p></body></html>",
            visible_text=(
                "Zalando standard delivery via DHL takes 2 to 4 business days within Germany. "
                "Order #104099887712 is covered by free returns within 100 days."
            ),
        )
        self.runtime.ingest_queue.join()

        # Check get_knowledge_summary() contains 'this_week' with both 'read' and 'received'
        summary = self.runtime.get_knowledge_summary()
        this_week = summary.get("this_week", [])
        kinds = {item.get("kind") for item in this_week}
        self.assertIn("read", kinds)
        self.assertIn("received", kinds)

        # Check unified Brain search for 'zalando' returns entities, passages, and mail
        search_res = self.runtime.search_brain("zalando", limit=20)
        self.assertTrue(search_res["ok"])
        self.assertGreaterEqual(len(search_res["entities"]), 1)
        self.assertGreaterEqual(len(search_res["passages"]), 1)
        self.assertGreaterEqual(len(search_res["mail"]), 1)

        # Test [forget] cascade deletion on an entity
        slug = search_res["entities"][0]["slug"]
        deleted = self.runtime.delete_brain_entity(slug)
        self.assertTrue(deleted)
        after_entities = [e["slug"] for e in self.runtime.brain.get_brain_summary().get("entities", [])]
        self.assertNotIn(slug, after_entities)

    def test_m20_no_tab_zalando_order_query_cites_b1_from_brain(self) -> None:
        """Gate: Ask 'when does my Zalando order arrive?' with no tabs open -> answers from Brain citing [B1]."""
        self._load_fixture_12()

        captured_prompts: list[str] = []

        class FakeGemmaTok:
            def apply_chat_template(self, msgs, **kwargs):
                class FakeInputs(dict):
                    def __init__(self, prompt_text: str):
                        super().__init__()
                        import torch

                        self["input_ids"] = torch.zeros((1, 8), dtype=torch.long)
                        self.prompt_text = prompt_text

                    def to(self, device):
                        return self

                full_prompt = "\n".join(str(m.get("content") or "") for m in msgs)
                captured_prompts.append(full_prompt)
                return FakeInputs(full_prompt)

            def decode(self, token_ids, skip_special_tokens=True):
                return ""

        class FakeGemmaModel:
            device = "cpu"

            def generate(self, **kwargs):
                streamer = kwargs.get("streamer")
                if streamer is not None:
                    streamer.text_queue.put(
                        "Your Zalando order #104099887712 shipped via DHL (tracking 00340434161094012345) and is estimated for delivery on 2026-11-12 [B1]."
                    )
                    streamer.end()

        orig_ensure_gemma = self.runtime.ensure_gemma
        self.runtime.gemma_tok = FakeGemmaTok()
        self.runtime.gemma_model = FakeGemmaModel()
        self.runtime.ensure_gemma = lambda: (self.runtime.gemma_tok, self.runtime.gemma_model)

        try:
            events = list(
                self.runtime.stream_chat(
                    messages=[{"role": "user", "content": "when does my Zalando order arrive?"}],
                    sources=[],
                    web_enabled=False,
                    conversation_summary="",
                    mail_enabled=False,
                )
            )
        finally:
            self.runtime.ensure_gemma = orig_ensure_gemma
            self.runtime.gemma_tok = None
            self.runtime.gemma_model = None

        self.assertEqual(len(captured_prompts), 1)
        self.assertIn("[B1] (order) Zalando Order 104099887712", captured_prompts[0])
        self.assertIn("2026-11-12", captured_prompts[0])

        done_events = [e for e in events if e.get("done") is True]
        self.assertEqual(len(done_events), 1)
        done = done_events[0]

        brain_sources = done.get("brain_sources", [])
        self.assertGreaterEqual(len(brain_sources), 1)
        self.assertEqual(brain_sources[0]["citation"], "B1")
        self.assertIn("Zalando", brain_sources[0]["name"])

        answer_text = done.get("annotated_text") or done.get("text") or ""
        self.assertIn("[B1]", answer_text)
        self.assertIn("2026-11-12", answer_text)
        self.assertGreaterEqual(int(done.get("citations_ok", 0)), 1)
        self.assertEqual(int(done.get("citations_flagged", 0)), 0)


if __name__ == "__main__":
    unittest.main()
