#!/usr/bin/env python3
"""
Tests for Extensible Action Provider Playbook & Dynamic Profile Registry:
- Built-in 8 seeded categories + custom category CRUD & deletion protection
- Smart inference (`POST /providers/infer`) from domains, presets, and pasted search URLs
- URL template safety validation (rejects javascript:, file:, loopback/private/metadata SSRF, dotless hosts)
- Per-profile isolation (`store.sqlite` & encrypted `vault.enc`), HTTP 403 when locked, zero secret leakage
- Multi-backend `search_api` execution (`kagi`, `brave`, `nominatim`, `wikipedia_api`) & failover without `os.environ`
- Agent harness tools (`get_default_providers`, `propose_comparer` category fallback,
  confirmed `propose_set_default_provider`, `[web: off]` host pinning, local Gemma `<tool_call>`)
- Dynamic `BehaviorMiner.mine_provider_suggestions` + accept/dismiss resolution
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

SIDECAR_DIR = Path(__file__).resolve().parent
SGS_ROOT = SIDECAR_DIR.parent.parent / "sgs"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))
if str(SGS_ROOT) not in sys.path:
    sys.path.insert(0, str(SGS_ROOT))

from satz_models import SatzSidecarRuntime, make_sidecar_server
from satz_providers import format_provider_search_url, validate_url_template
from satz_web_harness import WebSearchSessionHarness


class _FakeHttpResp:
    def __init__(self, body_obj: dict | list):
        self._raw = json.dumps(body_obj).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _FakeTextResp:
    def __init__(self, html: str, url: str = ""):
        self._raw = html.encode("utf-8")
        self._url = url
        self.headers = {"Content-Type": "text/html; charset=utf-8"}

    def geturl(self) -> str:
        return self._url

    def read(self, *_args) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class TestActionProvidersRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="satz_test_providers_"))
        store_path = self.temp_dir / "planck_store.sqlite"
        self.rt = SatzSidecarRuntime(sgs_root=SGS_ROOT, store_path=store_path)
        self.rt.mail.pipeline.stop_worker()
        self.rt.passwords.create_profile("Alice Providers", "123456")
        self.rt._refresh_active_profile_brain()
        self.auth_token = "test-providers-token"
        self.httpd = make_sidecar_server(
            self.rt,
            host="127.0.0.1",
            port=0,
            auth_token=self.auth_token,
        )
        self.port = self.httpd.server_address[1]
        self.srv_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.srv_thread.start()

    def tearDown(self) -> None:
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:
            pass
        try:
            self.rt.close()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _new_harness(self, **kwargs) -> WebSearchSessionHarness:
        return WebSearchSessionHarness(
            self.rt,
            combined_sources=kwargs.pop("combined_sources", []),
            hydrated_sources=kwargs.pop("hydrated_sources", []),
            used_source_ids=kwargs.pop("used_source_ids", []),
            cited_web_sources=kwargs.pop("cited_web_sources", []),
            source_stats_list=kwargs.pop("source_stats_list", []),
            **kwargs,
        )

    def _http_json(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {
            "X-Satz-Token": self.auth_token,
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_seeded_categories_and_custom_category_crud(self) -> None:
        status, reg = self._http_json("GET", "/providers")
        self.assertEqual(status, 200)
        self.assertTrue(reg["ok"])
        self.assertTrue(reg["unlocked"])
        cat_ids = {c["category_id"] for c in reg["categories"]}
        self.assertEqual(
            cat_ids,
            {
                "search.general",
                "search.knowledge",
                "search.travel",
                "search.accommodation",
                "maps.navigation",
                "commerce.tech",
                "commerce.clothing",
                "commerce.food",
            },
        )
        # Built-in categories cannot be deleted
        st_del_builtin, res_del_builtin = self._http_json(
            "POST", "/providers/category/delete", {"category_id": "commerce.tech"}
        )
        self.assertEqual(st_del_builtin, 400)
        self.assertFalse(res_del_builtin["ok"])

        # Custom category create -> rename -> delete
        st_add, res_add = self._http_json(
            "POST",
            "/providers/category/upsert",
            {"label": "Home Electronics", "parent_group": "commerce", "description": "Hardware stores"},
        )
        self.assertEqual(st_add, 200)
        self.assertTrue(res_add["ok"])
        custom_id = res_add["category_id"]
        self.assertTrue(any(c["category_id"] == custom_id and not c["is_builtin"] for c in res_add["categories"]))

        st_upd, res_upd = self._http_json(
            "POST",
            "/providers/category/upsert",
            {"category_id": custom_id, "label": "Smart Home Gear", "parent_group": "commerce"},
        )
        self.assertEqual(st_upd, 200)
        self.assertTrue(
            any(c["category_id"] == custom_id and c["label"] == "Smart Home Gear" for c in res_upd["categories"])
        )

        st_del, res_del = self._http_json(
            "POST", "/providers/category/delete", {"category_id": custom_id}
        )
        self.assertEqual(st_del, 200)
        self.assertFalse(any(c["category_id"] == custom_id for c in res_del["categories"]))

    def test_url_template_validation_and_smart_infer(self) -> None:
        # Reject dangerous / invalid URLs
        for bad in [
            "javascript:alert(1)//{query}",
            "file:///etc/passwd?q={query}",
            "http://127.0.0.1:8080/search?q={query}",
            "http://localhost:3000/search?q={query}",
            "http://169.254.169.254/latest?q={query}",
            "https://[::1]/search?q={query}",
            "not-a-url",
        ]:
            with self.assertRaises(ValueError, msg=f"Expected rejection for {bad}"):
                validate_url_template(bad)

        clean_tpl = validate_url_template("https://geizhals.de/?fs={query}")
        self.assertEqual(clean_tpl, "https://geizhals.de/?fs={query}")
        self.assertEqual(
            format_provider_search_url("https://geizhals.de/?fs={query}", "ThinkPad T14"),
            "https://geizhals.de/?fs=ThinkPad+T14",
        )

        # Save credential in Vault before inferring to confirm auto-linking without leaking secret
        self.rt.passwords.upsert_service_credential(
            "GEIZHALS",
            username="alice@example.com",
            password="geizhals-vault-password-999",
            url="https://geizhals.de",
        )
        st, inferred = self._http_json(
            "POST",
            "/providers/infer",
            {"input": "https://geizhals.de/?fs=thinkpad+t14+gen5", "category_id": "commerce.tech"},
        )
        self.assertEqual(st, 200)
        self.assertTrue(inferred["ok"])
        self.assertEqual(inferred["url_template"], "https://geizhals.de/?fs={query}")
        self.assertEqual(inferred["mode"], "web_account")
        self.assertTrue(inferred["auth_ready"])
        self.assertNotIn("geizhals-vault-password-999", json.dumps(inferred))

        # Domain-only preset inference
        st_kagi, inf_kagi = self._http_json(
            "POST",
            "/providers/infer",
            {"input": "kagi.com", "category_id": "search.general"},
        )
        self.assertEqual(st_kagi, 200)
        self.assertEqual(inf_kagi["mode"], "search_api")
        self.assertEqual(inf_kagi["api_driver"], "kagi")
        self.assertIn("kagi.com/search?q={query}", inf_kagi["url_template"])

        # Arbitrary unknown domain fallback
        st_unk, inf_unk = self._http_json(
            "POST",
            "/providers/infer",
            {"input": "example-boutique.de", "category_id": "commerce.clothing"},
        )
        self.assertEqual(st_unk, 200)
        self.assertEqual(inf_unk["domains"], ["example-boutique.de"])
        self.assertEqual(inf_unk["url_template"], "https://example-boutique.de")

    def test_provider_crud_reorder_vault_masking_and_profile_isolation(self) -> None:
        # Upsert two providers in commerce.tech with secret credentials saved only to vault.enc
        st1, res1 = self._http_json(
            "POST",
            "/providers/upsert",
            {
                "category_id": "commerce.tech",
                "display_name": "Geizhals",
                "domains": ["geizhals.de"],
                "url_template": "https://geizhals.de/?fs={query}",
                "mode": "web_account",
                "credentials": {
                    "username": "alice.geizhals@example.com",
                    "password": "SECRET_PASSWORD_ALICE",
                },
            },
        )
        self.assertEqual(st1, 200, res1)
        p1_id = next(p["id"] for p in res1["providers_by_category"]["commerce.tech"] if p["display_name"] == "Geizhals")

        st2, res2 = self._http_json(
            "POST",
            "/providers/upsert",
            {
                "category_id": "commerce.tech",
                "display_name": "Cyberport",
                "domains": ["cyberport.de"],
                "url_template": "https://www.cyberport.de/tools/search-results.html?q={query}",
                "mode": "web_account",
                "credentials": {
                    "api_key": "SECRET_CYBERPORT_TOKEN",
                },
            },
        )
        self.assertEqual(st2, 200, res2)
        p2_id = next(p["id"] for p in res2["providers_by_category"]["commerce.tech"] if p["display_name"] == "Cyberport")

        # Reorder #1 and #2 so Cyberport becomes primary
        st_re, res_re = self._http_json(
            "POST",
            "/providers/reorder",
            {"category_id": "commerce.tech", "ordered_ids": [p2_id, p1_id]},
        )
        self.assertEqual(st_re, 200)
        ordered = [p["id"] for p in res_re["providers_by_category"]["commerce.tech"]]
        self.assertEqual(ordered[:2], [p2_id, p1_id])

        # Secrets MUST NOT appear in HTTP responses, prompt hint, or sqlite tables
        serialized_http = json.dumps(res_re)
        self.assertNotIn("SECRET_PASSWORD_ALICE", serialized_http)
        self.assertNotIn("SECRET_CYBERPORT_TOKEN", serialized_http)
        prompt_hint = self.rt.providers.get_prompt_routing_hint()
        self.assertIn("cyberport.de", prompt_hint)
        self.assertNotIn("SECRET_PASSWORD_ALICE", prompt_hint)
        self.assertNotIn("SECRET_CYBERPORT_TOKEN", prompt_hint)

        with self.rt.store_lock:
            rows_dump = json.dumps(
                [dict(r) for r in self.rt.store.db.execute("SELECT * FROM satz_provider_entries").fetchall()]
            )
        self.assertNotIn("SECRET_PASSWORD_ALICE", rows_dump)
        self.assertNotIn("SECRET_CYBERPORT_TOKEN", rows_dump)

        # Provider test endpoint (web_account)
        st_tst, res_tst = self._http_json("POST", "/providers/test", {"provider_id": p1_id})
        self.assertEqual(st_tst, 200)
        self.assertTrue(res_tst["ok"])
        self.assertEqual(res_tst["auth_status"], "login")
        self.assertNotIn("SECRET_PASSWORD_ALICE", json.dumps(res_tst))

        # Delete Geizhals cleanly
        st_del, res_del = self._http_json("POST", "/providers/delete", {"provider_id": p1_id})
        self.assertEqual(st_del, 200)
        self.assertEqual([p["id"] for p in res_del["providers_by_category"]["commerce.tech"]], [p2_id])

        # Switch to Profile Bob -> Alice's entries & secrets are isolated
        self.rt.passwords.create_profile("Bob Isolated", "654321")
        self.rt._refresh_active_profile_brain()
        st_bob, reg_bob = self._http_json("GET", "/providers")
        self.assertEqual(st_bob, 200)
        self.assertEqual(reg_bob["providers_by_category"].get("commerce.tech", []), [])

        # Lock profile -> GET /providers reveals no profile data; write endpoints return 403
        self.rt.passwords.lock_profile()
        self.rt._refresh_active_profile_brain()
        st_locked_get, reg_locked = self._http_json("GET", "/providers")
        self.assertEqual(st_locked_get, 200)
        self.assertFalse(reg_locked["unlocked"])
        self.assertEqual(reg_locked["categories"], [])
        self.assertEqual(reg_locked["providers_by_category"], {})
        self.assertEqual(self.rt.providers.get_prompt_routing_hint(), "")

        st_locked_post, err_post = self._http_json(
            "POST",
            "/providers/upsert",
            {"category_id": "search.general", "display_name": "Kagi", "domains": ["kagi.com"]},
        )
        self.assertEqual(st_locked_post, 403)
        self.assertFalse(err_post["ok"])

        st_locked_cat, err_cat = self._http_json(
            "POST",
            "/providers/category/upsert",
            {"label": "Locked Cat", "parent_group": "custom"},
        )
        self.assertEqual(st_locked_cat, 403)
        self.assertFalse(err_cat["ok"])

    def test_search_api_drivers_failover_and_zero_env_leakage(self) -> None:
        # Store Kagi & Brave keys in Alice's encrypted vault ONLY (clear os.environ)
        for env_k in ("BRAVE_API_KEY", "KAGI_API_KEY", "SERPER_API_KEY"):
            os.environ.pop(env_k, None)

        self.rt.providers.upsert_provider(
            category_id="search.general",
            provider_slug="kagi",
            display_name="Kagi Search",
            domains=["kagi.com"],
            url_template="https://kagi.com/search?q={query}",
            mode="search_api",
            api_driver="kagi",
            priority=1,
            credentials={"api_key": "vault-kagi-secret-111"},
        )
        self.rt.providers.upsert_provider(
            category_id="search.general",
            provider_slug="brave",
            display_name="Brave Search",
            domains=["search.brave.com"],
            url_template="https://search.brave.com/search?q={query}",
            mode="search_api",
            api_driver="brave",
            priority=2,
            credentials={"api_key": "vault-brave-secret-222"},
        )
        self.rt.providers.upsert_provider(
            category_id="maps.navigation",
            provider_slug="openstreetmap",
            display_name="OpenStreetMap Nominatim",
            domains=["openstreetmap.org"],
            url_template="https://www.openstreetmap.org/search?query={query}",
            mode="search_api",
            api_driver="nominatim",
            priority=1,
        )
        self.rt.providers.upsert_provider(
            category_id="search.knowledge",
            provider_slug="wikipedia",
            display_name="Wikipedia",
            domains=["en.wikipedia.org"],
            url_template="https://en.wikipedia.org/w/index.php?search={query}",
            mode="search_api",
            api_driver="wikipedia_api",
            priority=1,
        )

        harness = self._new_harness(allow_web_tools=True)
        seen_calls: list[tuple[str, dict]] = []

        def fake_urlopen(req, timeout=15):
            url = req.full_url if isinstance(req, urllib.request.Request) else str(req)
            hdrs = {k.lower(): v for k, v in getattr(req, "headers", {}).items()}
            seen_calls.append((url, hdrs))
            if "kagi.com/api/v0/search" in url:
                # Simulate #1 Kagi transient 503 failure -> fails over to #2 Brave
                raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)
            if "api.search.brave.com" in url:
                self.assertEqual(hdrs.get("x-subscription-token"), "vault-brave-secret-222")
                return _FakeHttpResp(
                    {
                        "web": {
                            "results": [
                                {
                                    "url": "https://travel.example/adapter",
                                    "title": "Best EU Travel Adapter",
                                    "description": "Type C and GaN PD 65W specs",
                                }
                            ]
                        }
                    }
                )
            if "nominatim.openstreetmap.org" in url:
                return _FakeHttpResp(
                    [
                        {
                            "osm_type": "node",
                            "osm_id": 12345,
                            "display_name": "Munchen Hauptbahnhof, Bayern, Germany",
                            "lat": "48.1402",
                            "lon": "11.5583",
                            "type": "station",
                        }
                    ]
                )
            if "en.wikipedia.org/w/api.php" in url:
                return _FakeHttpResp(
                    {
                        "query": {
                            "search": [
                                {
                                    "title": "Planck constant",
                                    "snippet": "Fundamental <span>quantum</span> constant",
                                }
                            ]
                        }
                    }
                )
            # Top-result auto-fetch URLs (travel.example, openstreetmap.org, wikipedia page)
            return _FakeTextResp("<html><body>Fetched snippet detail.</body></html>", url=url)

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res_gen = harness.execute_web_search(
                query="best travel adapter",
                category="search.general",
            )
            self.assertTrue(res_gen["ok"], res_gen)
            self.assertEqual(res_gen["search_backend"], "brave")
            self.assertTrue(any("kagi" in n.lower() for n in res_gen.get("failover_notes", [])))
            self.assertEqual(res_gen["results"][0]["url"], "https://travel.example/adapter")

            res_map = harness.execute_web_search(
                query="Munich Central Station",
                category="maps.navigation",
            )
            self.assertTrue(res_map["ok"], res_map)
            self.assertEqual(res_map["search_backend"], "nominatim")
            self.assertIn("48.1402", res_map["results"][0]["snippet"])

            res_wiki = harness.execute_web_search(
                query="Planck constant",
                category="search.knowledge",
            )
            self.assertTrue(res_wiki["ok"], res_wiki)
            self.assertEqual(res_wiki["search_backend"], "wikipedia_api")
            self.assertIn("en.wikipedia.org/wiki/Planck_constant", res_wiki["results"][0]["url"])

        # Secrets MUST never enter os.environ
        self.assertIsNone(os.environ.get("KAGI_API_KEY"))
        self.assertIsNone(os.environ.get("BRAVE_API_KEY"))
        self.assertTrue(any("kagi.com/api/v0/search" in u for u, _ in seen_calls))
        self.assertTrue(any("api.search.brave.com" in u for u, _ in seen_calls))

    def test_harness_tools_web_off_pinning_confirmed_set_default_and_local_gemma(self) -> None:
        self.rt.providers.upsert_provider(
            category_id="commerce.tech",
            provider_slug="geizhals",
            display_name="Geizhals",
            domains=["geizhals.de"],
            url_template="https://geizhals.de/?fs={query}",
            mode="web_account",
        )
        self.rt.providers.upsert_provider(
            category_id="search.travel",
            provider_slug="db_bahn",
            display_name="Deutsche Bahn",
            domains=["bahn.de"],
            url_template="https://www.bahn.de/buchung/fahrplan/suche#sts=true&so={query}",
            mode="web_account",
        )

        # 1. get_default_providers + propose_comparer category URL fallback + web_off pinning
        cid = "conv-providers-harness"
        self.rt.ingest_page(
            conversation_id=cid,
            source_id="src-gh",
            url="https://geizhals.de/?fs=ThinkPad+T14",
            title="Geizhals Search",
            html="<html><body>ThinkPad T14 EUR 1199</body></html>",
            visible_text="ThinkPad T14 EUR 1199",
        )
        h_on = self._new_harness(
            conversation_id=cid,
            combined_sources=[
                {"id": "src-gh", "url": "https://geizhals.de/?fs=ThinkPad+T14", "title": "Geizhals", "domain": "geizhals.de", "is_open_tab": True},
            ],
            allow_web_tools=True,
        )
        res_defs = h_on.execute_get_default_providers(category="commerce.tech")
        self.assertTrue(res_defs["ok"], res_defs)
        self.assertEqual(res_defs["providers"][0]["display_name"], "Geizhals")

        comp_res = h_on.execute_propose_comparer(urls=[], goal="ThinkPad T14", category="commerce.tech")
        self.assertTrue(comp_res["ok"], comp_res)
        self.assertEqual(comp_res["status"], "waiting_confirm")
        task_comp = next(t for t in h_on.prepared_tasks if t["id"] == comp_res["task_id"])
        self.assertEqual(task_comp["steps"][-1]["action_payload"]["urls"], ["https://geizhals.de/?fs=ThinkPad+T14"])

        # [web: off] removes web_search from tool spec and blocks unpinned configured provider domains
        h_off = self._new_harness(
            conversation_id=cid,
            combined_sources=[
                {"id": "src-gh", "url": "https://geizhals.de/?fs=ThinkPad+T14", "title": "Geizhals", "domain": "geizhals.de", "is_open_tab": True},
            ],
            allow_web_tools=False,
        )
        off_tool_names = {t["name"] for t in h_off._active_tools_spec(allow_web_tools=False)}
        self.assertNotIn("web_search", off_tool_names)
        self.assertIn("get_default_providers", off_tool_names)
        blocked_nav = h_off.execute_open_and_read_url("https://www.bahn.de/buchung/fahrplan/suche")
        self.assertFalse(blocked_nav["ok"])
        self.assertIn("web: off", blocked_nav["error"].lower())

        # 2. propose_set_default_provider confirmation gate -> unconfirmed fails -> HTTP confirm + execute -> replay fails
        prop = h_on.execute_propose_set_default_provider(
            category_id="commerce.tech",
            domain_or_name="cyberport.de",
            url_template="https://www.cyberport.de/tools/search-results.html?q={query}",
            priority=1,
        )
        self.assertTrue(prop["ok"], prop)
        self.assertEqual(prop["status"], "waiting_confirm")
        tid = prop["task_id"]
        task_row = next(t for t in h_on.prepared_tasks if t["id"] == tid)
        step_row = task_row["steps"][-1]
        step_id = step_row["id"]

        # Unconfirmed attempt rejected
        st_unconf, res_unconf = self._http_json(
            "POST", "/providers/set_default", {"task_id": tid, "step_id": step_id}
        )
        self.assertEqual(st_unconf, 400)
        self.assertFalse(res_unconf["ok"])

        confirm_token = step_row["confirm_token"]
        self.assertTrue(self.rt.confirm_task_step(tid, step_id, confirm_token)["ok"])

        st_exec, res_exec = self._http_json(
            "POST", "/providers/set_default", {"task_id": tid, "step_id": step_id}
        )
        self.assertEqual(st_exec, 200, res_exec)
        self.assertTrue(res_exec["ok"])
        self.assertEqual(
            res_exec["providers_by_category"]["commerce.tech"][0]["domains"],
            ["cyberport.de"],
        )
        # Single-use token: second execution fails
        st_replay, res_replay = self._http_json(
            "POST", "/providers/set_default", {"task_id": tid, "step_id": step_id}
        )
        self.assertEqual(st_replay, 400)
        self.assertFalse(res_replay["ok"])

        # 3. Local Gemma <tool_call> roundtrip for get_default_providers + prompt routing hint check
        round_idx = {"n": 0}
        seen_msgs_per_round: list[list[dict]] = []

        class FakeInputs(dict):
            def __init__(self):
                super().__init__()
                import torch

                self["input_ids"] = torch.zeros((1, 10), dtype=torch.long)

            def to(self, device):
                return self

        class FakeGemmaTok:
            def apply_chat_template(self, msgs, **kwargs):
                seen_msgs_per_round.append([dict(m) for m in msgs])
                return FakeInputs()

            def decode(self, token_ids, skip_special_tokens=True):
                return ""

        class FakeGemmaModel:
            device = "cpu"

            def generate(self, **kwargs):
                streamer = kwargs.get("streamer")
                r = round_idx["n"]
                round_idx["n"] += 1
                if r == 0:
                    pieces = [
                        "<tool_call>",
                        '{"name": "get_default_providers", "arguments": {"category": "search.travel"}}',
                        "</tool_call>",
                    ]
                else:
                    pieces = ["Your default travel provider is Deutsche Bahn."]
                for p in pieces:
                    streamer.text_queue.put(p)
                streamer.end()

        orig_ensure = self.rt.ensure_gemma
        orig_tok = self.rt.gemma_tok
        orig_model = self.rt.gemma_model
        self.rt.gemma_tok = FakeGemmaTok()
        self.rt.gemma_model = FakeGemmaModel()
        self.rt.ensure_gemma = lambda: (self.rt.gemma_tok, self.rt.gemma_model)
        try:
            events = list(
                self.rt.stream_chat(
                    messages=[{"role": "user", "content": "What travel provider am I using?"}],
                    sources=[],
                    web_enabled=False,
                    model_id="gemma-4-e4b",
                )
            )
        finally:
            self.rt.ensure_gemma = orig_ensure
            self.rt.gemma_tok = orig_tok
            self.rt.gemma_model = orig_model

        deltas = "".join(e.get("delta", "") for e in events)
        self.assertIn("Deutsche Bahn", deltas)
        self.assertNotIn("<tool_call>", deltas)
        self.assertEqual(len(seen_msgs_per_round), 2)
        self.assertIn("bahn.de", seen_msgs_per_round[0][0]["content"])

    def test_behavior_miner_suggestions_and_accept_dismiss_resolution(self) -> None:
        # Log repeated shopping visits to zalando.de and skyscanner.net
        for i in range(4):
            self.rt.behavior.log_event(
                "tab_capture",
                domain="zalando.de",
                url=f"https://www.zalando.de/katalog/?q=jacket+{i}",
                query="compare coats",
            )
            self.rt.behavior.log_event(
                "tab_capture",
                domain="skyscanner.net",
                url=f"https://www.skyscanner.net/transport/flights?q=ber+{i}",
                query="flight to berlin",
            )

        res_mine = self.rt.behavior.mine_provider_suggestions(min_interval_secs=0.0)
        self.assertIsInstance(res_mine, list)
        st, reg = self._http_json("GET", "/providers")
        self.assertEqual(st, 200)
        sug_by_dom = {s["domain"]: s for s in reg["suggestions"]}
        self.assertIn("zalando.de", sug_by_dom)
        self.assertEqual(sug_by_dom["zalando.de"]["category_id"], "commerce.clothing")
        self.assertIn("skyscanner.net", sug_by_dom)
        self.assertEqual(sug_by_dom["skyscanner.net"]["category_id"], "search.travel")

        # Accept zalando.de -> promoted to commerce.clothing default providers
        st_acc, res_acc = self._http_json(
            "POST",
            "/providers/suggestion/resolve",
            {"suggestion_id": sug_by_dom["zalando.de"]["suggestion_id"], "action": "accept"},
        )
        self.assertEqual(st_acc, 200, res_acc)
        self.assertTrue(res_acc["ok"])
        clothing_domains = [
            d
            for p in res_acc["providers_by_category"].get("commerce.clothing", [])
            for d in p.get("domains", [])
        ]
        self.assertIn("zalando.de", clothing_domains)
        self.assertNotIn("zalando.de", [s["domain"] for s in res_acc["suggestions"]])

        # Dismiss skyscanner.net -> stays out of search.travel and leaves pending suggestions
        st_dis, res_dis = self._http_json(
            "POST",
            "/providers/suggestion/resolve",
            {"suggestion_id": sug_by_dom["skyscanner.net"]["suggestion_id"], "action": "dismiss"},
        )
        self.assertEqual(st_dis, 200, res_dis)
        self.assertTrue(res_dis["ok"])
        self.assertEqual(res_dis["providers_by_category"].get("search.travel", []), [])
        self.assertNotIn("skyscanner.net", [s["domain"] for s in res_dis["suggestions"]])


if __name__ == "__main__":
    unittest.main()
