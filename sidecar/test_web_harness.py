#!/usr/bin/env python3
"""
Tests for Cloud & Chat Web Search Harness (`satz_web_harness.py`):
- Follow-up & explicit web search intent detection (`"can you do a web search for that then?"`)
- Anaphoric topic resolution from conversation history
- Search-howto noise filtering (`support.google.com/websearch`, `wikihow.com`) & snippet resilience on blocked fetches
- Multi-provider native tool-calling loops: Gemini (including `thoughtSignature` preservation & `thought` filtering),
  Anthropic (`tool_use` / `tool_result`), OpenAI & Mistral (`tool_calls` / `role: tool`)
- HTTP 400 unsupported-tools deterministic fallback
- Synchronization of `hydrated_sources`, `source_stats`, `cited_sources` (page previews), and `check_citations`
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

SIDECAR_DIR = Path(__file__).resolve().parent
SGS_ROOT = SIDECAR_DIR.parent.parent / "sgs"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))
if str(SGS_ROOT) not in sys.path:
    sys.path.insert(0, str(SGS_ROOT))

from satz_models import SatzSidecarRuntime
from satz_web_harness import (
    WebSearchSessionHarness,
    is_explicit_web_search_request,
    resolve_web_search_query,
)


class _FakeHttpResp:
    def __init__(self, body_obj: dict):
        self._raw = json.dumps(body_obj).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class TestCloudWebSearchHarness(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="satz_test_web_harness_"))
        store_path = self.temp_dir / "planck_store.sqlite"
        self.rt = SatzSidecarRuntime(sgs_root=SGS_ROOT, store_path=store_path)
        self.rt.mail.pipeline.stop_worker()
        self.rt.passwords.create_profile("Alice Web", "123456")
        self.rt._refresh_active_profile_brain()

    def tearDown(self) -> None:
        try:
            self.rt.close()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_explicit_intent_and_anaphoric_query_resolution(self) -> None:
        prior = [
            {"role": "user", "content": "What are the stocks that are predicted to move today (17/11/2027)"},
            {
                "role": "assistant",
                "content": "I don't have real-time financial market data for today in your open tabs.",
            },
        ]
        self.assertTrue(is_explicit_web_search_request("can you do a web search for that then?", prior))
        self.assertTrue(is_explicit_web_search_request("yes, please do", prior))
        self.assertFalse(is_explicit_web_search_request("summarize my latest email", prior))

        resolved = resolve_web_search_query("can you do a web search for that then?", prior)
        self.assertIn("stocks", resolved.lower())
        self.assertIn("17/11/2027", resolved)
        self.assertNotIn("that then", resolved.lower())
        self.assertNotIn("web search", resolved.lower())

        direct_q = resolve_web_search_query("search the web for NVIDIA Q3 earnings results", prior)
        self.assertEqual(direct_q, "NVIDIA Q3 earnings results")

    def test_noise_filter_and_snippet_resilience_on_blocked_fetch(self) -> None:
        def fake_search(query: str):
            return [
                {
                    "url": "https://support.google.com/websearch/answer/134479",
                    "title": "How to search on Google",
                    "snippet": "Step 1 go to google.com",
                    "domain": "support.google.com",
                },
                {
                    "url": "https://www.wikihow.com/Search-the-Internet",
                    "title": "How to Search the Internet (with Pictures)",
                    "snippet": "Open a browser...",
                    "domain": "wikihow.com",
                },
                {
                    "url": "https://finance.yahoo.com/news/nvda-movers-101.html",
                    "title": "Stocks to Watch Today: NVDA, AMD, TSLA",
                    "snippet": "Nvidia rose 4.2% premarket on strong AI server orders while AMD gained 2.8%.",
                    "domain": "finance.yahoo.com",
                },
                {
                    "url": "https://www.bloomberg.com/markets/stocks-moving-today",
                    "title": "European & US Stock Movers Today",
                    "snippet": "Tesla slipped 1.5% ahead of delivery figures; ASML climbed 3.1%.",
                    "domain": "bloomberg.com",
                },
            ]

        def fake_fetch(url: str):
            if "finance.yahoo.com" in url:
                return {
                    "url": url,
                    "status": 200,
                    "html": "<html><head><title>Stocks to Watch Today</title></head><body><article><p>Nvidia rose 4.2% premarket on strong AI server orders while AMD gained 2.8% on Tuesday.</p></article></body></html>",
                }
            return {
                "url": url,
                "status": 403,
                "html": "<html><body>Access Denied - You don't have permission to access this page.</body></html>",
            }

        combined: list = []
        hydrated: list = []
        used_ids: list = []
        cited: list = []
        stats: list = []
        harness = WebSearchSessionHarness(
            self.rt,
            combined_sources=combined,
            hydrated_sources=hydrated,
            used_source_ids=used_ids,
            cited_web_sources=cited,
            source_stats_list=stats,
        )
        with mock.patch.object(self.rt.web, "search", side_effect=fake_search), mock.patch.object(
            self.rt.web, "fetch", side_effect=fake_fetch
        ):
            res = harness.execute_web_search("stocks predicted to move today", max_results=5)

        self.assertTrue(res["ok"])
        domains = [r["domain"] for r in res["results"]]
        self.assertNotIn("support.google.com", domains)
        self.assertNotIn("wikihow.com", domains)
        self.assertEqual(domains, ["finance.yahoo.com", "bloomberg.com"])
        self.assertEqual(res["results"][0]["cite_tag"], "[1]")
        self.assertEqual(res["results"][0]["capture_mode"], "fetch")
        self.assertEqual(res["results"][1]["cite_tag"], "[2]")
        self.assertEqual(res["results"][1]["capture_mode"], "snippet")
        self.assertIn("ASML climbed 3.1%", hydrated[1]["full_text"])
        self.assertNotIn("Access Denied", hydrated[1]["full_text"])

    def test_gemini_tool_loop_thought_signature_and_followup_stream_chat(self) -> None:
        recorded_payloads: list[dict] = []

        def fake_search(query: str):
            return [
                {
                    "url": "https://finance.yahoo.com/news/movers-2027.html",
                    "title": "Premarket Movers: Nvidia and ASML",
                    "snippet": "Nvidia gained 4.5% and ASML gained 3.1% following guidance updates.",
                    "domain": "finance.yahoo.com",
                },
                {
                    "url": "https://www.reuters.com/markets/us/stock-movers-today/",
                    "title": "US Stock Movers",
                    "snippet": "Microsoft rose 1.9% after cloud contract news.",
                    "domain": "reuters.com",
                },
            ]

        def fake_fetch(url: str):
            if "reuters.com" in url:
                return {
                    "url": url,
                    "status": 200,
                    "html": "<html><body><article><p>Microsoft rose 1.9% to $490 after announcing new cloud capacity deals in Frankfurt.</p></article></body></html>",
                }
            return {
                "url": url,
                "status": 200,
                "html": "<html><body><article><p>Nvidia gained 4.5% premarket and ASML gained 3.1% following upgraded revenue guidance.</p></article></body></html>",
            }

        call_idx = {"n": 0}

        def fake_urlopen(req, timeout=20.0):
            body = json.loads(req.data.decode("utf-8"))
            recorded_payloads.append(body)
            call_idx["n"] += 1
            if call_idx["n"] == 1:
                # Model emits internal thought + web_search functionCall with thoughtSignature
                return _FakeHttpResp(
                    {
                        "candidates": [
                            {
                                "content": {
                                    "role": "model",
                                    "parts": [
                                        {"text": "hidden internal chain of thought", "thought": True},
                                        {
                                            "functionCall": {
                                                "name": "web_search",
                                                "args": {"query": "stocks predicted to move today 17/11/2027"},
                                            },
                                            "thoughtSignature": "gem-sig-9988",
                                        },
                                    ],
                                }
                            }
                        ]
                    }
                )
            if call_idx["n"] == 2:
                # Model then fetches Reuters page for full detail
                return _FakeHttpResp(
                    {
                        "candidates": [
                            {
                                "content": {
                                    "role": "model",
                                    "parts": [
                                        {
                                            "functionCall": {
                                                "name": "fetch_webpage",
                                                "args": {"url": "https://www.reuters.com/markets/us/stock-movers-today/"},
                                            }
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                )
            return _FakeHttpResp(
                {
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [
                                    {
                                        "text": (
                                            "Nvidia gained 4.5% and ASML gained 3.1% premarket [1]. "
                                            "Microsoft rose 1.9% to $490 after cloud capacity deals [2]."
                                        )
                                    }
                                ],
                            }
                        }
                    ]
                }
            )

        messages = [
            {"role": "user", "content": "What are the stocks that are predicted to move today (17/11/2027)"},
            {"role": "assistant", "content": "I don't have real-time market data in your active tabs."},
            {"role": "user", "content": "can you do a web search for that then?"},
        ]

        with mock.patch.object(self.rt, "_resolve_provider_api_key", return_value=("fake-gem-key", "vault")), \
             mock.patch.object(self.rt.web, "search", side_effect=fake_search), \
             mock.patch.object(self.rt.web, "fetch", side_effect=fake_fetch), \
             mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            events = list(
                self.rt.stream_chat(
                    messages=messages,
                    sources=[],
                    web_enabled=False,
                    model_id="gemini:gemini-4-hydrogen (cloud)",
                )
            )

        done_ev = [e for e in events if e.get("done")][-1]
        full_answer = "".join(e.get("delta", "") for e in events)
        self.assertIn("Nvidia", full_answer)
        self.assertNotIn("hidden internal chain of thought", full_answer)
        self.assertEqual(done_ev["citations_flagged"], 0, f"Unexpected flagged citations: {done_ev}")
        self.assertGreaterEqual(done_ev["citations_ok"], 2)
        cited_urls = [c["url"] for c in done_ev.get("cited_sources") or []]
        self.assertIn("https://finance.yahoo.com/news/movers-2027.html", cited_urls)
        self.assertIn("https://www.reuters.com/markets/us/stock-movers-today/", cited_urls)

        # Verify tools declaration and thoughtSignature preservation on Turn 2 payload
        self.assertIn("tools", recorded_payloads[0])
        second_contents_json = json.dumps(recorded_payloads[1]["contents"])
        self.assertIn("gem-sig-9988", second_contents_json)

    def test_anthropic_openai_mistral_and_400_tools_fallback(self) -> None:
        def fake_search(query: str):
            return [
                {
                    "url": "https://example.org/weather-berlin",
                    "title": "Berlin Weather Forecast",
                    "snippet": "Berlin high 9 C with light rain today.",
                    "domain": "example.org",
                }
            ]

        def fake_fetch(url: str):
            return {"url": url, "status": 403, "html": ""}

        # 1) Anthropic tool_use -> tool_result
        anth_calls = {"n": 0}

        def fake_anth_urlopen(req, timeout=20.0):
            anth_calls["n"] += 1
            if anth_calls["n"] == 1:
                return _FakeHttpResp(
                    {
                        "stop_reason": "tool_use",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_1",
                                "name": "web_search",
                                "input": {"query": "Berlin weather forecast"},
                            }
                        ],
                    }
                )
            return _FakeHttpResp(
                {"content": [{"type": "text", "text": "Berlin is expected to reach 9 C with light rain [1]."}]}
            )

        with mock.patch.object(self.rt, "_resolve_provider_api_key", return_value=("fake-anth", "vault")), \
             mock.patch.object(self.rt.web, "search", side_effect=fake_search), \
             mock.patch.object(self.rt.web, "fetch", side_effect=fake_fetch), \
             mock.patch("urllib.request.urlopen", side_effect=fake_anth_urlopen):
            ev_anth = list(
                self.rt.stream_chat(
                    messages=[{"role": "user", "content": "What is the weather in Berlin?"}],
                    sources=[],
                    web_enabled=True,
                    model_id="anthropic:claude-sonnet-4-5 (cloud)",
                )
            )
        done_anth = [e for e in ev_anth if e.get("done")][-1]
        self.assertEqual(done_anth["citations_ok"], 1)
        self.assertEqual(done_anth["citations_flagged"], 0)

        # 2) Mistral OpenAI-compatible tool_calls -> tool message
        mis_calls = {"n": 0}

        def fake_mis_urlopen(req, timeout=20.0):
            mis_calls["n"] += 1
            if mis_calls["n"] == 1:
                return _FakeHttpResp(
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "call_m1",
                                            "type": "function",
                                            "function": {
                                                "name": "web_search",
                                                "arguments": '{"query": "Berlin weather"}',
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                )
            return _FakeHttpResp(
                {"choices": [{"message": {"role": "assistant", "content": "Berlin is 9 C with light rain [1]."}}]}
            )

        with mock.patch.object(self.rt, "_resolve_provider_api_key", return_value=("fake-mis", "vault")), \
             mock.patch.object(self.rt.web, "search", side_effect=fake_search), \
             mock.patch.object(self.rt.web, "fetch", side_effect=fake_fetch), \
             mock.patch("urllib.request.urlopen", side_effect=fake_mis_urlopen):
            ev_mis = list(
                self.rt.stream_chat(
                    messages=[{"role": "user", "content": "Berlin weather?"}],
                    sources=[],
                    web_enabled=True,
                    model_id="mistral:mistral-large-latest (cloud)",
                )
            )
        done_mis = [e for e in ev_mis if e.get("done")][-1]
        self.assertEqual(done_mis["citations_ok"], 1)

        # 3) Gemini HTTP 400 rejecting tools -> falls back to deterministic pre-search + plain generateContent
        gem_400_calls = {"n": 0}

        def fake_gem_400_urlopen(req, timeout=20.0):
            gem_400_calls["n"] += 1
            body = json.loads(req.data.decode("utf-8"))
            if "tools" in body:
                err_fp = io.BytesIO(b'{"error": {"message": "Function calling tool declaration is not supported on this model"}}')
                raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, err_fp)
            return _FakeHttpResp(
                {
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [{"text": "Berlin forecast shows 9 C and light rain [1]."}],
                            }
                        }
                    ]
                }
            )

        with mock.patch.object(self.rt, "_resolve_provider_api_key", return_value=("fake-gem", "vault")), \
             mock.patch.object(self.rt.web, "search", side_effect=fake_search), \
             mock.patch.object(self.rt.web, "fetch", side_effect=fake_fetch), \
             mock.patch("urllib.request.urlopen", side_effect=fake_gem_400_urlopen):
            ev_fb = list(
                self.rt.stream_chat(
                    messages=[{"role": "user", "content": "Berlin weather today?"}],
                    sources=[],
                    web_enabled=True,
                    model_id="gemini:gemma-custom-endpoint (cloud)",
                )
            )
        done_fb = [e for e in ev_fb if e.get("done")][-1]
        self.assertEqual(done_fb["citations_ok"], 1)
        self.assertEqual(done_fb["citations_flagged"], 0)

    def test_settings_role_chat_persists_in_health_and_clears_on_key_delete(self) -> None:
        with mock.patch.object(
            self.rt,
            "_discover_provider_models",
            return_value=[{"id": "gemini:gemini-4-hydrogen (cloud)", "label": "Gemini 4 Hydrogen"}],
        ):
            self.rt.update_model_management_config(
                {
                    "provider_id": "gemini",
                    "api_key": "AIzaSyFakeKey1234567890",
                    "role_chat": "gemini:gemini-4-hydrogen (cloud)",
                }
            )
            health = self.rt.get_health()
            self.assertEqual(health["model_config"]["roles"]["chat"], "gemini:gemini-4-hydrogen (cloud)")
        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}, clear=False):
            cleared = self.rt.update_model_management_config({"provider_id": "gemini", "clear_key": True})
        self.assertEqual(cleared["roles"]["chat"], "gemma-4-e4b")


if __name__ == "__main__":
    unittest.main()
