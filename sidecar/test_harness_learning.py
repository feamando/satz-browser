"""
Tests for Item 3: Learn From Implicit Corrections & Personal Style Signals
1. Email writing style learning from draft_reply vs edited sent outbox + Brain note distillation
2. Harness failure signals (Retry, Use Planck instead, Flagged citations, Manual overrides) & learned routing
3. 2-tier context compression (Index Manifest + BM25/embedding excerpts + read_source(n) tool)
"""

from __future__ import annotations

import http.client
import json
import os
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

SIDECAR_DIR = os.path.dirname(os.path.abspath(__file__))
SGS_ROOT = Path(SIDECAR_DIR).parent.parent / "sgs"
if SIDECAR_DIR not in sys.path:
    sys.path.insert(0, SIDECAR_DIR)
if str(SGS_ROOT) not in sys.path:
    sys.path.insert(0, str(SGS_ROOT))

from satz_models import SatzSidecarRuntime, check_citations, make_sidecar_server  # noqa: E402
from satz_web_harness import WebSearchSessionHarness  # noqa: E402


class _FakeStreamer:
    """Deterministic iterable replacement for transformers.TextIteratorStreamer in local Gemma tests."""

    def __init__(self, tok, **kwargs):
        self._pieces = list(tok._next_pieces())
        self._ended = False

    def __iter__(self):
        for p in self._pieces:
            if self._ended:
                break
            yield p

    def end(self):
        self._ended = True


class _FakeBatchEncoding(dict):
    def to(self, _device):
        return self


class _FakeTokenizer:
    def __init__(self, script_rounds: list[list[str]]):
        self.rounds = [list(r) for r in script_rounds]
        self.idx = 0
        self.seen_prompts: list[list[dict]] = []

    def _next_pieces(self):
        if self.idx < len(self.rounds):
            out = self.rounds[self.idx]
            self.idx += 1
            return out
        return ["done"]

    def apply_chat_template(self, msgs, **kwargs):
        self.seen_prompts.append([dict(m) for m in msgs])
        return _FakeBatchEncoding({"input_ids": [[1, 2, 3]]})


class _FakeModel:
    device = "cpu"

    def generate(self, **kwargs):
        return None


class TestHarnessLearning(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="satz_test_harness_learning_"))
        store_path = self.temp_dir / "planck_store.sqlite"
        self.runtime = SatzSidecarRuntime(
            sgs_root=SGS_ROOT,
            store_path=store_path,
        )
        self.runtime.mail.pipeline.stop_worker()
        # Create and unlock an isolated profile so Brain + Vault + Mail work end-to-end
        prof = self.runtime.passwords.create_profile("TestProfile", "123456")
        self.assertTrue(prof.get("unlocked") or prof.get("id"))
        self.runtime._refresh_active_profile_brain()
        self.runtime.passwords.save_raw_env("MAIL_TEST_USER=nikita@example.org\nMAIL_TEST_PASS=secret123")
        conn = self.runtime.mail._ensure_connection()
        with self.runtime.mail.db_lock:
            conn.execute(
                """
                INSERT OR IGNORE INTO accounts (
                    id, label, email, protocol, in_host, in_port, in_security,
                    smtp_host, smtp_port, smtp_security, vault_prefix
                ) VALUES (
                    'acct-test', 'Test', 'nikita@example.org', 'imap', 'localhost', 993, 'ssl',
                    'localhost', 587, 'starttls', 'MAIL_TEST'
                )
                """
            )
            conn.commit()
        # Speed up encoder lookup cleanly in unit tests unless needed
        self._orig_embed = self.runtime.brain._get_encoder

    def tearDown(self) -> None:
        self.runtime.brain._get_encoder = self._orig_embed
        try:
            self.runtime.close()
        except Exception:
            pass
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _insert_inbox_message(self, mid: str, from_name: str, from_addr: str, subject: str, body: str) -> None:
        conn = self.runtime.mail._ensure_connection()
        with self.runtime.mail.db_lock:
            conn.execute(
                """
                INSERT OR REPLACE INTO messages (
                    id, account_id, folder, uid, message_id, from_name, from_addr,
                    to_json, subject, snippet, body_text, date
                ) VALUES (?, 'acct-test', 'INBOX', 0, ?, ?, ?, '["nikita@example.org"]', ?, ?, ?, 1760000000.0)
                """,
                (mid, f"<{mid}@example>", from_name, from_addr, subject, body[:120], body),
            )
            conn.execute(
                "INSERT OR REPLACE INTO parts (message_id, kind, text) VALUES (?, 'new', ?)",
                (mid, body),
            )
            conn.commit()

    def _send_outbox_sync(self, outbox_id: str, confirm_token: str) -> None:
        """Executes real send-gate `confirm_and_queue_send(..., immediate_for_test=True)` with mocked SMTP."""
        fake_smtp = mock.MagicMock()
        orig_open = self.runtime.mail._open_smtp_client
        orig_auth = self.runtime.mail._smtp_authenticate
        self.runtime.mail._open_smtp_client = lambda *_a, **_kw: fake_smtp
        self.runtime.mail._smtp_authenticate = lambda *_a, **_kw: None
        try:
            res = self.runtime.mail.confirm_and_queue_send(outbox_id, confirm_token, immediate_for_test=True)
            self.assertTrue(res.get("ok"), res)
        finally:
            self.runtime.mail._open_smtp_client = orig_open
            self.runtime.mail._smtp_authenticate = orig_auth

    # ── Part 1: Outbox Edit-Diff Writing Style Learning ─────────────────

    def test_1_mail_style_learned_from_outbox_edit_diffs_and_injected(self):
        # Mock runtime._complete_role_prompt so draft_reply stays fast, recording every prompt seen
        captured_prompts: list[str] = []

        def fake_complete(model_id: str, system_prompt: str, user_prompt: str, **_kw) -> str:
            captured_prompts.append(f"{system_prompt}\n\n{user_prompt}")
            return (
                "Dear Recipient,\n\n"
                "I hope this email finds you well. Thank you for reaching out regarding this topic. "
                "We will review the proposal in full detail tomorrow afternoon and get back to you.\n\n"
                "Kind regards,\nAI Assistant"
            )

        self.runtime._complete_role_prompt = fake_complete

        # Simulate 10 real sent replies with consistent personal edits:
        # - @hellofresh.de -> German informal ("Hallo ..., ... Viele Grüße, Nikita")
        # - @partner.com   -> English crisp ("Hi ..., ... Best, Nikita")
        # - Both cut verbose "I hope this email finds you well" filler.
        samples = [
            ("m-de-1", "Anna Weber", "anna@hellofresh.de", "Hallo Anna,\n\npasst perfekt, lass uns morgen um 14 Uhr sprechen.\n\nViele Grüße,\nNikita"),
            ("m-de-2", "Jonas Becker", "jonas@hellofresh.de", "Hallo Jonas,\n\ndanke dir, schicke das Update bis 16 Uhr.\n\nViele Grüße,\nNikita"),
            ("m-de-3", "Lena Wolf", "lena@hellofresh.de", "Hallo Lena,\n\neinverstanden, bitte so freigeben.\n\nViele Grüße,\nNikita"),
            ("m-de-4", "Tim Klein", "tim@hellofresh.de", "Hallo Tim,\n\nschauen wir uns im Sync kurz an.\n\nViele Grüße,\nNikita"),
            ("m-de-5", "Mia Bauer", "mia@hellofresh.de", "Hallo Mia,\n\nklingt gut, bin dabei.\n\nViele Grüße,\nNikita"),
            ("m-en-1", "Sam Taylor", "sam@partner.com", "Hi Sam,\n\nSounds good, let us ship it tomorrow.\n\nBest,\nNikita"),
            ("m-en-2", "Chris Lee", "chris@partner.com", "Hi Chris,\n\nConfirmed on my side, thanks.\n\nBest,\nNikita"),
            ("m-en-3", "Pat Morgan", "pat@partner.com", "Hi Pat,\n\nAgreed, please proceed with v2.\n\nBest,\nNikita"),
            ("m-en-4", "Alex Diaz", "alex@partner.com", "Hi Alex,\n\nReviewed and approved.\n\nBest,\nNikita"),
            ("m-en-5", "Jordan Kim", "jordan@partner.com", "Hi Jordan,\n\nLet us meet at 10am UTC.\n\nBest,\nNikita"),
        ]

        for mid, fname, faddr, edited_body in samples:
            self._insert_inbox_message(mid, fname, faddr, f"Subject {mid}", "Can we confirm the plan for tomorrow?")
            draft_res = self.runtime.mail.draft_reply(
                {
                    "message_id": mid,
                    "to": faddr,
                    "subject": f"Re: Subject {mid}",
                    "instructions": "confirm",
                    "model": "gemma-4-e4b",
                }
            )
            self.assertTrue(draft_res.get("ok"))
            draft_id = draft_res.get("draft_id")
            self.assertTrue(draft_id)

            prep = self.runtime.mail.prepare_send(
                {
                    "account_id": "acct-test",
                    "to": faddr,
                    "subject": f"Re: Subject {mid}",
                    "body": edited_body,
                    "reply_to_message_id": mid,
                    "ai_draft_id": draft_id,
                }
            )
            self.assertTrue(prep.get("ok"), prep)
            self._send_outbox_sync(prep["outbox_id"], prep["confirm_token"])

        # After 10 sent edited replies, Brain note should be distilled automatically
        status = self.runtime.mail.get_writing_style_status()
        self.assertEqual(status["diff_count"], 10)
        self.assertTrue(status["has_note"])
        self.assertTrue(any("concise" in r.lower() or "greeting" in r.lower() or "german" in r.lower() for r in status["rules"]))

        ent = self.runtime.brain.get_entity_by_slug("email-writing-style-preferences")
        self.assertIsNotNone(ent)
        body_md = str(ent.get("body") or ent.get("content") or "")
        self.assertIn("hellofresh.de", body_md.lower())
        self.assertIn("partner.com", body_md.lower())
        self.assertIn("viele grüße", body_md.lower())

        # Now draft to a German hellofresh recipient & English partner recipient: style must inject!
        captured_prompts.clear()
        next_de = self.runtime.mail.draft_reply(
            {
                "message_id": "m-de-1",
                "to": "katharina@hellofresh.de",
                "subject": "Re: Roadmap",
                "instructions": "confirm friday",
                "model": "gemma-4-e4b",
            }
        )
        self.assertTrue(next_de.get("style_applied"))
        self.assertIn("PERSONAL WRITING STYLE", captured_prompts[-1])
        self.assertIn("German", captured_prompts[-1])

        captured_prompts.clear()
        next_en = self.runtime.mail.draft_reply(
            {
                "message_id": "m-en-1",
                "to": "taylor@partner.com",
                "subject": "Re: Contract",
                "instructions": "approve",
                "model": "gemma-4-e4b",
            }
        )
        self.assertTrue(next_en.get("style_applied"))
        self.assertIn("English", captured_prompts[-1])

    # ── Part 2: Harness Failure Signals & Learned Routing ───────────────

    def test_2_harness_failure_signals_escalate_to_cloud_planck_and_auto_context(self):
        # 2a. Fresh DB: no escalation on Command Bar
        routes_fresh = self.runtime.rank_command_bar_routes(
            "compare solar vs wind storage costs",
            web_enabled=False,
            selected_model="gemma-4-e4b",
        )
        self.assertEqual(routes_fresh[0]["kind"], "ask_model")
        self.assertFalse(routes_fresh[0].get("escalated", False))
        self.assertFalse(routes_fresh[0]["leaves_machine"])

        # 2b. Record 2 Use Planck instead failures WITHOUT cloud keys -> must escalate to planck3 (web), NOT cloud
        for _ in range(2):
            self.runtime.record_harness_signal(
                prompt="compare solar vs wind storage costs",
                model_id="gemma-4-e4b",
                source_count=3,
                chars_cut=4200,
                outcome_signal="use_planck_instead",
                web_enabled=False,
            )
        pol_planck = self.runtime.get_routing_policy()
        rule_cmp = pol_planck["by_query_type"]["comparison_research"]
        self.assertTrue(rule_cmp["escalated"])
        self.assertEqual(rule_cmp["recommended_model"], "planck3 (web)")
        self.assertTrue(rule_cmp["auto_web"])

        routes_planck = self.runtime.rank_command_bar_routes(
            "compare battery chemistries vs LFP",
            web_enabled=False,
            selected_model="gemma-4-e4b",
        )
        self.assertEqual(routes_planck[0].get("model"), "planck3 (web)")
        self.assertTrue(routes_planck[0]["leaves_machine"])
        self.assertTrue(routes_planck[0].get("auto_web"))

        # 2c. Reset and test Retry escalation when a Cloud key IS configured (OpenAI) + Mail context auto-enable
        self.runtime.reset_routing_telemetry()
        self.runtime.passwords.save_raw_env("OPENAI_API_KEY=sk-test-local-mock-key-12345")

        for _ in range(2):
            self.runtime.record_harness_signal(
                prompt="compare Q3 and Q4 product strategy docs",
                model_id="gemma-4-e4b",
                source_count=5,
                chars_cut=8500,
                outcome_signal="retry",
                web_enabled=False,
                mail_enabled=False,
            )
        pol_cloud = self.runtime.get_routing_policy()
        cmp_cloud = pol_cloud["by_query_type"]["comparison_research"]
        self.assertTrue(cmp_cloud["escalated"])
        self.assertTrue(str(cmp_cloud["recommended_model"]).startswith("openai:"))
        self.assertTrue(cmp_cloud["auto_web"])

        routes_cloud = self.runtime.rank_command_bar_routes(
            "compare Q3 vs Q4 specs",
            web_enabled=False,
            selected_model="gemma-4-e4b",
        )
        self.assertTrue(str(routes_cloud[0].get("model") or "").startswith("openai:"))
        self.assertTrue(routes_cloud[0]["leaves_machine"])
        self.assertIn("cloud", routes_cloud[0]["privacy"])

        # Repeated Retry on mail queries without mail_enabled must auto-enable mail_enabled!
        for _ in range(2):
            self.runtime.record_harness_signal(
                prompt="where is my Zalando order tracking email?",
                model_id="gemma-4-e4b",
                source_count=0,
                chars_cut=0,
                outcome_signal="retry",
                web_enabled=False,
                mail_enabled=False,
            )
        route_mail = self.runtime.resolve_chat_route(
            prompt="find my latest invoice email from DHL",
            selected_model="gemma-4-e4b",
            web_enabled=False,
            mail_enabled=False,
        )
        self.assertTrue(route_mail["mail_enabled"])
        self.assertTrue(str(route_mail["model"]).startswith("openai:"))

        # Manual override lock must prevent overriding user choice in resolve_chat_route
        route_locked = self.runtime.resolve_chat_route(
            prompt="compare Q3 vs Q4 specs",
            selected_model="gemma-4-e4b",
            user_overrode_model=True,
        )
        self.assertEqual(route_locked["model"], "gemma-4-e4b")

    # ── Part 3: 2-Tier Context Compression + read_source(n) Tool ────────

    def _build_14_heavy_sources(self) -> list[dict]:
        sources: list[dict] = []
        for idx in range(1, 14):
            filler = f"Quarterly operational log #{idx} covers European warehouse staffing and logistics routines. " * 95
            sources.append(
                {
                    "id": f"tab-src-{idx}",
                    "url": f"https://intranet.example.org/doc/{idx}",
                    "title": f"Operations Log {idx}",
                    "domain": "intranet.example.org",
                    "is_open_tab": True,
                    "text": filler,
                }
            )
        tail_body = (
            ("Background notes on Nordic expansion timeline and facility readiness. " * 60)
            + " Project Aurora final budget is 14.8 million EUR allocated across Helsinki and Stockholm hubs. "
            + ("Additional appendix governance details follow below. " * 40)
        )
        sources.append(
            {
                "id": "tab-src-14",
                "url": "https://intranet.example.org/aurora-budget",
                "title": "Project Aurora Budget",
                "domain": "intranet.example.org",
                "is_open_tab": True,
                "text": tail_body,
            }
        )
        return sources

    def test_3_two_tier_context_manifest_ranking_and_read_source(self):
        # Provide deterministic lightweight fake encoder for repeatable BM25+embedding hybrid test
        class _MiniEnc:
            def encode(self, texts, normalize_embeddings=True):
                vecs = []
                for t in texts:
                    tl = t.lower()
                    vecs.append([
                        1.0 if "aurora" in tl or "budget" in tl or "14.8" in tl else 0.05,
                        1.0 if "warehouse" in tl else 0.05,
                    ])
                return vecs

        self.runtime.brain._get_encoder = lambda: _MiniEnc()
        sources14 = self._build_14_heavy_sources()

        # 3a. Generic question: budget fills on earlier tabs, YET [14] MUST NOT be dropped!
        ctx_gen, used_ids_gen, hydrated_gen = self.runtime.assemble_chat_context(
            "Give an overview of the logs",
            sources14,
        )
        self.assertEqual(len(used_ids_gen), 14)
        self.assertIn("tab-src-14", used_ids_gen)
        self.assertIn("SOURCE INDEX MANIFEST", ctx_gen)
        self.assertIn("[14]", ctx_gen)
        self.assertLessEqual(len(ctx_gen), self.runtime.total_context_char_budget + 1500)
        self.assertEqual(hydrated_gen[13]["context_tier"], "manifest")

        # Execute read_source(14) on the manifest-only source -> expands cleanly and passes check_citations!
        harness = WebSearchSessionHarness(
            self.runtime,
            combined_sources=sources14,
            hydrated_sources=hydrated_gen,
            used_source_ids=used_ids_gen,
            cited_web_sources=[],
            source_stats_list=[
                {
                    "id": hs["id"],
                    "chars_captured": hs["chars_captured"],
                    "chars_sent": hs["chars_sent"],
                    "was_cut": hs["was_cut"],
                    "capture_mode": hs["capture_mode"],
                    "context_tier": hs["context_tier"],
                }
                for hs in hydrated_gen
            ],
        )
        # Verify read_source is exposed even when web_tools is False!
        spec_names = [t["name"] for t in harness._active_tools_spec(allow_web_tools=False, allow_actor_tools=False)]
        self.assertIn("read_source", spec_names)

        read_res = harness._dispatch_tool_call("read_source", {"n": 14, "query": "Project Aurora final budget"})
        self.assertTrue(read_res.get("ok"), read_res)
        self.assertIn("14.8 million EUR", read_res["content"])
        self.assertEqual(harness.hydrated_sources[13]["context_tier"], "expanded")
        self.assertEqual(harness.source_stats_list[13]["context_tier"], "expanded")

        cite_res = check_citations("Project Aurora final budget is 14.8 million EUR [14].", harness.hydrated_sources)
        self.assertEqual(cite_res["citations_ok"], 1)
        self.assertEqual(cite_res["citations_flagged"], 0)

        # 3b. Query specifically about Project Aurora -> BM25+embedding promotes [14] into Tier-2 excerpt immediately!
        ctx_q, used_ids_q, hydrated_q = self.runtime.assemble_chat_context(
            "What is the Project Aurora final budget in EUR?",
            sources14,
        )
        self.assertEqual(len(used_ids_q), 14)
        self.assertIn(hydrated_q[13]["context_tier"], ("full", "excerpt"))
        self.assertIn("14.8 million EUR", ctx_q)

    def test_4_local_gemma_read_source_tool_loop_end_to_end(self):
        # Force source [14] into Tier-1 manifest via neutral ranking
        self.runtime.brain._get_encoder = lambda: None
        sources14 = self._build_14_heavy_sources()
        # Rename title slightly so "Summarize open documents" won't put [14] in Tier-2 first
        sources14[13]["title"] = "Z-Appendix File 14"

        fake_tok = _FakeTokenizer(
            [
                ['<read_source>{"n": 14, "query": "Aurora budget"}</read_source>'],
                ["Project Aurora final budget is 14.8 million EUR across Helsinki and Stockholm [14]."],
            ]
        )
        fake_model = _FakeModel()

        orig_ensure = self.runtime.ensure_gemma
        self.runtime.gemma_tok = fake_tok
        self.runtime.gemma_model = fake_model
        self.runtime.ensure_gemma = lambda: (fake_tok, fake_model)

        import numpy  # noqa: F401 - keep in sys.modules across mock.patch.dict exit
        import torch  # noqa: F401 - keep in sys.modules across mock.patch.dict exit

        fake_transformers = types.ModuleType("transformers")
        fake_transformers.TextIteratorStreamer = _FakeStreamer  # type: ignore[attr-defined]
        fake_transformers.AutoProcessor = mock.MagicMock()  # type: ignore[attr-defined]

        try:
            with mock.patch.dict(sys.modules, {"transformers": fake_transformers}):
                events = list(
                    self.runtime.stream_chat(
                        messages=[{"role": "user", "content": "Give me all warehouse and appendix details."}],
                        sources=sources14,
                        web_enabled=False,
                        model_id="gemma-4-e4b",
                    )
                )
        finally:
            self.runtime.ensure_gemma = orig_ensure

        deltas = "".join(ev.get("delta", "") for ev in events)
        self.assertNotIn("<read_source", deltas)
        self.assertIn("14.8 million EUR", deltas)
        self.assertIn("[14]", deltas)

        done_ev = next(ev for ev in events if ev.get("done"))
        self.assertEqual(done_ev["citations_ok"], 1)
        self.assertEqual(done_ev["citations_flagged"], 0)
        stat14 = next(st for st in done_ev["source_stats"] if st["id"] == "tab-src-14")
        self.assertEqual(stat14["context_tier"], "expanded")

    def test_5_http_endpoints_style_and_telemetry(self):
        srv = make_sidecar_server(self.runtime, "127.0.0.1", 0, auth_token="test-tok-xyz")
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            def req_json(method: str, path: str, body: dict | None = None):
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                headers = {"X-Satz-Token": "test-tok-xyz", "Host": f"127.0.0.1:{port}"}
                raw = b""
                if body is not None:
                    raw = json.dumps(body).encode("utf-8")
                    headers["Content-Type"] = "application/json"
                conn.request(method, path, body=raw if body is not None else None, headers=headers)
                resp = conn.getresponse()
                data = json.loads(resp.read().decode("utf-8"))
                conn.close()
                return resp.status, data

            st1, res1 = req_json(
                "POST",
                "/telemetry/signal",
                {
                    "prompt": "compare vendor SLAs",
                    "model_id": "gemma-4-e4b",
                    "source_count": 4,
                    "chars_cut": 3200,
                    "outcome_signal": "retry",
                },
            )
            self.assertEqual(st1, 200)
            self.assertTrue(res1["ok"])
            self.assertEqual(res1["policy"]["total_signals"], 1)

            st2, pol_res = req_json("GET", "/routing/policy")
            self.assertEqual(st2, 200)
            self.assertEqual(pol_res["total_signals"], 1)

            st3, rst_res = req_json("POST", "/telemetry/reset", {})
            self.assertEqual(st3, 200)
            self.assertEqual(rst_res["deleted"], 1)
            self.assertEqual(rst_res["policy"]["total_signals"], 0)

            st4, sty_res = req_json("GET", "/mail/style")
            self.assertEqual(st4, 200)
            self.assertTrue(sty_res["ok"])
            self.assertIn("diff_count", sty_res)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
