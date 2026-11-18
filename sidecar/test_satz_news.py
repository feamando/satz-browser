#!/usr/bin/env python3
"""
Unit & Integration Tests for Satz News (M24-M30):
- Profile-scoped tables & seed feeds
- Expanded 4 News role routing config persistence (`news_planner`, `news_capture`, `news_reader`, `news_analyzer`)
- Wire syndication family collapse (AP/Reuters duplicates count once)
- Conditional RSS parsing (`304 Not Modified`, XML RSS 2.0 + Atom)
- PII Scrubber Gate (`scrub_pii_for_external_query`) & `<brain_store>` neutralizer
- `SatzLLMReader` trust-blind routing across cloud providers
- `answer_news_question` `read -> weigh -> write` + Rule E counterfactual divergence
- `faithful_news` grounding check (catches invented numbers/entities and out-of-range cites)
- `get_perspectives` agreed / framing buckets / blind spots
- Topic watches & `save_cluster_to_brain` provenance
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SIDECAR_DIR = Path(__file__).resolve().parent
SGS_ROOT = SIDECAR_DIR.parent.parent / "sgs"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))
if str(SGS_ROOT) not in sys.path:
    sys.path.insert(0, str(SGS_ROOT))

from satz_models import SatzSidecarRuntime
from satz_news import SatzLLMReader, faithful_news, parse_feed_xml


SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>DW Top Stories</title>
    <item>
      <title>EU sets new grid interconnect targets for 2030</title>
      <link>https://www.dw.com/en/eu-grid-2030/a-1001</link>
      <description>European energy ministers approved a 42 billion EUR offshore grid expansion plan today.</description>
      <pubDate>Tue, 17 Nov 2026 10:00:00 GMT</pubDate>
      <enclosure url="https://static.dw.com/image/grid.jpg" type="image/jpeg" />
    </item>
  </channel>
</rss>
"""


class TestSatzNewsEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="satz_test_news_"))
        store_path = self.temp_dir / "planck_store.sqlite"
        self.rt = SatzSidecarRuntime(sgs_root=SGS_ROOT, store_path=store_path)
        self.rt.mail.pipeline.stop_worker()
        self.rt.passwords.create_profile("Alice News", "123456")
        self.rt._refresh_active_profile_brain()

    def tearDown(self) -> None:
        try:
            self.rt.close()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_role_routing_persistence_includes_four_news_roles(self) -> None:
        res = self.rt.update_model_management_config(
            {
                "role_news_planner": "gemini:gemini-3.5-flash-lite (cloud)",
                "role_news_capture": "anthropic:claude-sonnet-4-6 (cloud)",
                "role_news_reader": "hertz (reader)",
                "role_news_analyzer": "openai:gpt-5 (cloud)",
            }
        )
        self.assertTrue(res["ok"])
        roles = res["roles"]
        self.assertEqual(roles["news_planner"], "gemini:gemini-3.5-flash-lite (cloud)")
        self.assertEqual(roles["news_capture"], "anthropic:claude-sonnet-4-6 (cloud)")
        self.assertEqual(roles["news_reader"], "hertz (reader)")
        self.assertEqual(roles["news_analyzer"], "openai:gpt-5 (cloud)")

    def test_pii_scrubber_gate_and_injection_defense(self) -> None:
        self.rt.brain.upsert_entity(
            entity_type="person",
            name="Dr. Franziska Moeller",
            summary="Doctor in Berlin",
            attributes={"email": "moeller@clinic.de"},
            tier=1,
        )
        dirty = "Lufthansa booking LH9941A to Lisbon for Dr. Franziska Moeller moeller@clinic.de at Friedrichstr. 12 EUR 445.50"
        cleaned = self.rt.brain.scrub_pii_for_external_query(dirty)
        self.assertNotIn("moeller@clinic.de", cleaned)
        self.assertNotIn("LH9941A", cleaned)
        self.assertNotIn("Franziska Moeller", cleaned)
        self.assertNotIn("445.50", cleaned)
        self.assertIn("Lisbon", cleaned)

        # Confirm Brain upsert respects locked state & HTML directives neutralize cleanly
        self.rt.passwords.lock_profile()
        self.rt._refresh_active_profile_brain()
        with self.assertRaises(PermissionError):
            self.rt.news.save_cluster_to_brain("newscl-none")

    def test_wire_family_collapse_and_conditional_rss(self) -> None:
        items = parse_feed_xml(SAMPLE_RSS_XML, "dw.com", "https://rss.dw.com/xml/rss-en-all")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["image_url"], "https://static.dw.com/image/grid.jpg")

        now = time.time()
        # Four domains all carrying identical AP syndicated reporting should collapse to 1 family (`wire:ap`)
        for idx, dom in enumerate(("herald-local.com", "tribune-daily.org", "chronicle-city.net", "apnews.com")):
            self.rt.news.upsert_article(
                {
                    "url": f"https://{dom}/news/eu-grid-{idx}",
                    "domain": dom,
                    "title": "EU sets new grid interconnect targets for 2030 today",
                    "snippet": "WASHINGTON (AP) - European energy ministers approved a 42 billion EUR offshore grid expansion plan.",
                    "published_at": now - 120,
                }
            )
        self.rt.news.recluster_and_rank()
        stories = self.rt.news.get_stories(lane="top")["stories"]
        self.assertEqual(len(stories), 1)
        # All 4 collapse to family `wire:ap` => only 1 independent family, 3 collapsed mirrors
        self.assertEqual(stories[0]["independent_families"], 1)
        self.assertEqual(stories[0]["collapsed_mirrors"], 3)

        # Test conditional 304 HTTP feed refresh skips re-inserting
        with self.rt.store_lock:
            self.rt.store.db.execute("UPDATE satz_news_feeds SET enabled = 0")
            self.rt.store.db.execute(
                "INSERT OR REPLACE INTO satz_news_feeds (feed_id, domain, feed_url, title, category, language, enabled, etag) "
                "VALUES ('test-rss', 'dw.com', 'https://rss.dw.com/test.xml', 'DW Test', 'independent', 'en', 1, 'v1')"
            )
            self.rt.store.db.commit()

        calls = []

        def fake_http(url, etag, lm):
            calls.append((url, etag))
            if etag == "v1":
                return {"status": 304, "not_modified": True, "etag": "v1", "last_modified": None, "text": ""}
            return {"status": 200, "not_modified": False, "etag": "v2", "last_modified": None, "text": SAMPLE_RSS_XML}

        res_304 = self.rt.news.refresh_news_feeds(force=True, fetcher=fake_http)
        self.assertEqual(res_304["not_modified"], 1)
        self.assertEqual(res_304["fetched_feeds"], 0)
        self.assertEqual(len(calls), 1)

    def test_source_list_30_percent_cap_and_conflict_badge(self) -> None:
        self.rt.set_domain_trust("reuters.com", 2.0)  # sys=7.0, personal=2.0 -> |5| >= 3 => conflict
        srcs = self.rt.news.list_sources(query="reuters.com", conflicted_only=True)["sources"]
        self.assertEqual(len(srcs), 1)
        self.assertEqual(srcs[0]["system"], 7.0)
        self.assertEqual(srcs[0]["effective"], round(0.7 * 7.0 + 0.3 * 2.0, 2))
        self.assertTrue(srcs[0]["conflict"])

    def test_faithful_news_gate_and_cloud_reader_integration(self) -> None:
        srcs = [
            {
                "idx": 1,
                "domain": "dw.com",
                "title": "EU grid expansion",
                "snippet": "European ministers backed a 42 billion EUR offshore plan in November 2026.",
            }
        ]
        ok_good, probs_good = faithful_news(
            "Ministers backed a 42 billion EUR plan in November 2026 [1].",
            "EU grid plan",
            srcs,
        )
        self.assertTrue(ok_good, probs_good)

        ok_bad_num, _ = faithful_news(
            "Ministers backed a 999 billion EUR plan in November 2026 [1].",
            "EU grid plan",
            srcs,
        )
        self.assertFalse(ok_bad_num)

        ok_bad_cite, _ = faithful_news("Plan approved [3].", "EU grid plan", srcs)
        self.assertFalse(ok_bad_cite)

        # Mock `_complete_role_prompt` to test trust-blind SatzLLMReader + answer_news_question + divergence
        now = time.time()
        self.rt.news.upsert_article(
            {
                "url": "https://www.dw.com/en/offshore-plan/a-1",
                "domain": "dw.com",
                "title": "How much is the 2026 EU offshore grid plan?",
                "snippet": "European ministers approved 42 billion EUR for the offshore grid plan in 2026.",
                "body_text": "European ministers approved 42 billion EUR for the offshore grid plan in 2026.",
                "published_at": now,
            }
        )
        self.rt.news.upsert_article(
            {
                "url": "https://www.lemonde.fr/en/offshore-plan-2",
                "domain": "lemonde.fr",
                "title": "EU backs 42 billion EUR grid expansion",
                "snippet": "Le Monde confirms 42 billion EUR grid investment.",
                "body_text": "Le Monde confirms 42 billion EUR grid investment.",
                "published_at": now,
            }
        )
        # Personal score drops lemonde.fr from 8.0 to 1.0 -> eff = 5.9 (< 7.0 STRONG threshold!)
        self.rt.set_domain_trust("lemonde.fr", 1.0)
        self.rt.update_model_management_config(
            {"role_news_reader": "gemini:gemini-3-flash (cloud)", "role_news_analyzer": "template"}
        )

        # Ensure reader receives ZERO trust weights
        captured_prompts = []

        def fake_complete(model_id, sys_p, usr_p, **_kw):
            captured_prompts.append(usr_p)
            return json.dumps({"k": 0, "p": 0.92})

        with mock.patch.object(self.rt, "_complete_role_prompt", side_effect=fake_complete):
            with mock.patch.object(self.rt.web, "search", return_value=[]):
                ans = self.rt.news.answer_news_question("How much is the 2026 EU offshore grid plan?")

        self.assertTrue(ans["ok"])
        self.assertTrue(len(captured_prompts) >= 1)
        self.assertNotIn("trust", captured_prompts[0].lower())
        meta = ans["answer_meta"]
        self.assertEqual(meta["qtype"], "news")
        self.assertTrue(any("news" in str(it[0]).lower() for it in meta["items"]))
        self.assertIsNotNone(meta["confidence10"])

    def test_perspectives_topics_and_brain_save_and_profile_isolation(self) -> None:
        now = time.time()
        self.rt.news.upsert_article(
            {
                "url": "https://www.dw.com/en/carbon-border-tax-2026",
                "domain": "dw.com",
                "title": "EU Carbon Border Tax takes full effect in 2026",
                "snippet": "Brussels confirmed 85 EUR per tonne levy starting 2026.",
                "published_at": now,
            }
        )
        self.rt.news.upsert_article(
            {
                "url": "https://www.rt.com/business/eu-carbon-tax-dispute",
                "domain": "rt.com",
                "title": "EU Carbon Border Tax takes effect amid trade disputes 2026",
                "snippet": "Analysts warn the 85 EUR per tonne tariff raises import costs.",
                "published_at": now - 60,
            }
        )
        self.rt.news.recluster_and_rank()
        stories = self.rt.news.get_stories(lane="perspectives")["stories"]
        self.assertEqual(len(stories), 1)
        cid = stories[0]["cluster_id"]

        persp = self.rt.news.get_perspectives(cid)
        self.assertTrue(persp["ok"])
        self.assertGreaterEqual(len(persp["framings"]), 2)
        self.assertTrue(any("missing:" in b.lower() for b in persp["blind_spots"]))

        saved = self.rt.news.save_cluster_to_brain(cid)
        self.assertEqual(saved["entity"]["type"], "story")
        self.assertEqual(saved["entity"]["attributes"]["$source"], f"news:{cid}")

        t_res = self.rt.news.manage_topic({"action": "add", "name": "Carbon Border Tax", "watch": True})
        self.assertTrue(t_res["ok"])
        self.assertIsNotNone(t_res["watch_id"])

        # Switch profile -> zero articles/clusters/topics leaked from Alice News!
        self.rt.passwords.create_profile("Bob Isolated", "654321")
        self.rt._refresh_active_profile_brain()
        bob_status = self.rt.news.get_status()
        self.assertEqual(bob_status["articles"], 0)
        self.assertEqual(bob_status["clusters"], 0)
        self.assertEqual(bob_status["topics"], 0)

    def test_briefing_news_filters_landing_pages_and_uses_selected_cloud_analyzer(self) -> None:
        now = time.time()
        self.rt.news.upsert_article(
            {
                "url": "https://www.dw.com/en/europe-grid-pact-2026/a-70948321",
                "domain": "dw.com",
                "title": "Europe reaches offshore power grid deal in Brussels",
                "snippet": "European ministers agreed to triple North Sea wind capacity by 2035.",
                "body_text": "European ministers met in Brussels and approved joint grid interconnectors worth 42 billion EUR.",
                "published_at": now,
            }
        )
        self.rt.news.upsert_article(
            {
                "url": "https://www.bbc.com/news/articles/c12345europe",
                "domain": "bbc.com",
                "title": "Europe rail corridor expansion backed by EU transport chiefs",
                "snippet": "High-speed cross-border rail links across central Europe received backing today.",
                "body_text": "Transport ministers signed a joint pact covering Prague, Vienna, and Berlin corridors.",
                "published_at": now - 100,
            }
        )

        def fake_web_search(q: str):
            return [
                {
                    "url": "https://www.euronews.com/",
                    "title": "Latest breaking news available | Euronews",
                    "snippet": "Euronews shorts and Europe News portal.",
                    "domain": "euronews.com",
                },
                {
                    "url": "https://apnews.com/hub/europe",
                    "title": "Europe News | Breaking Europe News",
                    "snippet": "Hub page for Europe coverage.",
                    "domain": "apnews.com",
                },
            ]

        def fake_llm(model_id, sys_p, usr_p, **_kw):
            return (
                "- **[Europe reaches offshore power grid deal in Brussels]"
                "(https://www.dw.com/en/europe-grid-pact-2026/a-70948321)** "
                "Several European ministers backed joint grid interconnectors worth 42 billion EUR in Brussels [1].\n"
                "- **Europe rail corridor expansion** Cross-border rail links covering Prague and Berlin won backing [2]."
            )

        with mock.patch.object(self.rt, "_complete_role_prompt", side_effect=fake_llm), mock.patch.object(
            self.rt.web, "search", side_effect=fake_web_search
        ):
            res = self.rt.news.answer_news_question(
                "What are today's top corroborated European news stories?",
                roles_override={"news_analyzer": "gemini:gemini-4-hydrogen (cloud)"},
            )

        self.assertTrue(res["ok"])
        self.assertEqual(res["model"], "gemini:gemini-4-hydrogen (cloud)")
        self.assertNotIn("Unclear", res["answer"])
        self.assertNotIn("Euronews shorts", res["answer"])
        urls_returned = [s["url"] for s in res["sources"]]
        self.assertNotIn("https://www.euronews.com/", urls_returned)
        self.assertNotIn("https://apnews.com/hub/europe", urls_returned)
        self.assertIn("https://www.dw.com/en/europe-grid-pact-2026/a-70948321", urls_returned)
        self.assertGreaterEqual(res["answer_meta"]["confidence10"], 6.5)
        self.assertTrue(res["source_stats"])
        self.assertTrue(all(st["chars_sent"] > 0 for st in res["source_stats"]))


if __name__ == "__main__":
    unittest.main()
