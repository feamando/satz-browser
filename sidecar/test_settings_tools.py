#!/usr/bin/env python3
"""Unit & integration tests for S1/S2: Satz ToolRegistry, secret-free staging & Settings tools."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import types
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
from satz_tools import REGISTRY as SATZ_TOOL_REGISTRY
from satz_tools.fallback import maybe_fallback_settings_cards
from satz_tools.settings_staging import (
    clear_ephemeral_settings_state,
    execute_confirm_gate,
    stage_settings_file,
)
from satz_web_harness import (
    WebSearchSessionHarness,
    build_cloud_web_system_addendum,
    build_local_tool_system_addendum,
)

SAMPLE_CLIENT_JSON = json.dumps(
    {
        "installed": {
            "client_id": "1048291048-demoapp.apps.googleusercontent.com",
            "project_id": "satz-demo-project",
            "client_secret": "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9",
            "redirect_uris": ["http://localhost"],
        }
    }
)

SAMPLE_ENV = """
# API keys
GEMINI_API_KEY=AIzaSyTestSecretKeyNeverEchoed123456
OPENAI_API_KEY=sk-proj-OpenAISecretNeverEchoed7890
CUSTOM_TOKEN=supersecretvalue98765
"""


class TestSettingsToolsAndRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="satz_test_settools_"))
        store_path = self.temp_dir / "planck_store.sqlite"
        self.rt = SatzSidecarRuntime(sgs_root=SGS_ROOT, store_path=store_path)
        self.rt.mail.pipeline.stop_worker()

    def tearDown(self) -> None:
        try:
            self.rt.close()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_harness(self, *, origin: str = "settings", staged_files=None) -> WebSearchSessionHarness:
        return WebSearchSessionHarness(
            self.rt,
            combined_sources=[],
            hydrated_sources=[],
            used_source_ids=[],
            cited_web_sources=[],
            source_stats_list=[],
            conversation_id="conv-settings" if origin == "settings" else "conv-chat-1",
            conversation_origin=origin,
            staged_files=staged_files,
        )

    def test_stage_files_never_expose_raw_secrets_and_wipe_on_lock(self) -> None:
        res_json = stage_settings_file(
            self.rt,
            filename="client_secret_123.json",
            mime="application/json",
            content_text=SAMPLE_CLIENT_JSON,
        )
        self.assertTrue(res_json["ok"])
        staged_g = res_json["staged"]
        self.assertEqual(staged_g["detected_kind"], "google_client_secret")
        self.assertNotIn("GOCSPX-ultra-secret", json.dumps(res_json))
        self.assertEqual(staged_g["safe_fields"]["project_id"], "satz-demo-project")

        res_env = stage_settings_file(
            self.rt,
            filename=".env",
            mime="text/plain",
            content_text=SAMPLE_ENV,
        )
        self.assertTrue(res_env["ok"])
        staged_e = res_env["staged"]
        self.assertEqual(staged_e["detected_kind"], "env_secrets")
        dump_env = json.dumps(res_env)
        self.assertNotIn("TestSecretKeyNeverEchoed", dump_env)
        self.assertNotIn("OpenAISecretNeverEchoed", dump_env)
        self.assertNotIn("supersecretvalue98765", dump_env)
        self.assertIn("GEMINI_API_KEY", staged_e["safe_fields"]["keys"])
        self.assertIn("gemini", staged_e["safe_fields"]["recognized_providers"])

        # Addendums for both local Gemma and Cloud must carry handles ONLY, never raw secrets
        h = self._make_harness(origin="settings", staged_files=[staged_g, staged_e])
        specs = h._active_tools_spec(allow_web_tools=False)
        local_add = build_local_tool_system_addendum(
            specs,
            allow_web_tools=False,
            conversation_origin="settings",
            staged_files=[staged_g, staged_e],
        )
        cloud_add = build_cloud_web_system_addendum(
            allow_web_tools=False,
            active_tools=specs,
            conversation_origin="settings",
            staged_files=[staged_g, staged_e],
        )
        for text in (local_add, cloud_add):
            self.assertIn(staged_g["staging_id"], text)
            self.assertNotIn("GOCSPX-", text)
            self.assertNotIn("TestSecretKeyNeverEchoed", text)
            self.assertNotIn("OpenAISecretNeverEchoed", text)

        # Wiping on profile lock/switch clears staged secrets immediately
        clear_ephemeral_settings_state(self.rt)
        insp = h._dispatch_tool_call("settings_inspect_staged_file", {"staging_id": staged_g["staging_id"]})
        self.assertFalse(insp.get("ok"))

    def test_settings_tools_strictly_blocked_outside_settings_origin(self) -> None:
        chat_h = self._make_harness(origin="chat")
        chat_specs = {t["name"] for t in chat_h._active_tools_spec(allow_web_tools=True)}
        self.assertNotIn("settings_prepare_create_profile", chat_specs)
        self.assertNotIn("settings_configure_google_oauth", chat_specs)

        blocked = chat_h._dispatch_tool_call("settings_prepare_create_profile", {"profile_name": "pwned"})
        self.assertFalse(blocked["ok"])
        self.assertIn("restricted to the Settings workspace", blocked["error"])
        self.assertEqual(chat_h.ui_cards, [])

    def test_profile_google_oauth_and_env_single_use_confirm_gates(self) -> None:
        h = self._make_harness(origin="settings")

        # 1. Profile creation card never sees PIN
        res_prof = h._dispatch_tool_call("settings_prepare_create_profile", {"profile_name": "ngorshkov"})
        self.assertTrue(res_prof["ok"])
        self.assertEqual(len(h.ui_cards), 1)
        self.assertEqual(h.ui_cards[0]["kind"], "profile_create_card")
        self.assertEqual(h.ui_cards[0]["data"]["profile_name"], "ngorshkov")

        # 2. Actually create + unlock profile (out-of-band), then test Google JSON staging -> vault.enc
        self.rt.passwords.create_profile("ngorshkov", "135790")
        self.rt._refresh_active_profile_brain()

        st_g = stage_settings_file(
            self.rt,
            filename="client_secret.json",
            content_text=SAMPLE_CLIENT_JSON,
        )["staged"]
        h2 = self._make_harness(origin="settings", staged_files=[st_g])
        cfg_res = h2._dispatch_tool_call(
            "settings_configure_google_oauth",
            {"staging_id": st_g["staging_id"], "scopes_preset": "gmail"},
        )
        self.assertTrue(cfg_res["ok"])
        self.assertTrue(cfg_res["configured"])
        self.assertEqual(h2.ui_cards[-1]["kind"], "google_oauth_connect_card")
        self.assertTrue(self.rt.google_auth.get_status()["configured"])

        # Disconnect requires single-use confirm_token
        disc_res = h2._dispatch_tool_call(
            "settings_refresh_or_disconnect_google",
            {"action": "disconnect", "clear_client_config": True},
        )
        self.assertTrue(disc_res["confirm_required"])
        tok_disc = h2.ui_cards[-1]["confirm_token"]
        self.assertTrue(tok_disc)
        exec_disc = execute_confirm_gate(self.rt, confirm_token=tok_disc)
        self.assertTrue(exec_disc["ok"])
        self.assertFalse(self.rt.google_auth.get_status()["configured"])
        # Replay must fail cleanly
        replay_disc = execute_confirm_gate(self.rt, confirm_token=tok_disc)
        self.assertFalse(replay_disc["ok"])

        # 3. Staged .env import gate -> vault.enc + masked model check (never returns stored_key)
        st_e = stage_settings_file(self.rt, filename=".env", content_text=SAMPLE_ENV)["staged"]
        h3 = self._make_harness(origin="settings", staged_files=[st_e])
        env_res = h3._dispatch_tool_call(
            "settings_stage_api_key_or_env",
            {"staging_id": st_e["staging_id"]},
        )
        self.assertTrue(env_res["confirm_required"])
        tok_env = h3.ui_cards[-1]["confirm_token"]
        exec_env = execute_confirm_gate(self.rt, confirm_token=tok_env)
        self.assertTrue(exec_env["ok"])
        cred_map = self.rt.passwords.get_unlocked_credentials_map()
        self.assertEqual(cred_map.get("GEMINI_API_KEY"), "AIzaSyTestSecretKeyNeverEchoed123456")

        roles_dump = json.dumps(h3._dispatch_tool_call("settings_get_model_roles", {}))
        self.assertNotIn("TestSecretKeyNeverEchoed", roles_dump)
        self.assertNotIn("stored_key", roles_dump)

        # Redacted args are stripped if a hallucinating model tries passing api_key directly
        manual_card = h3._dispatch_tool_call(
            "settings_stage_api_key_or_env",
            {"provider_id": "openai", "api_key": "sk-proj-SHOULD_BE_STRIPPED"},
        )
        self.assertTrue(manual_card["ok"])
        self.assertEqual(h3.ui_cards[-1]["kind"], "vault_secret_input_card")

        # Role update + mail + provider inference + delete gate
        role_upd = h3._dispatch_tool_call(
            "settings_set_model_roles",
            {"chat_model": "gemini:gemini-3-flash-preview"},
        )
        self.assertTrue(role_upd["ok"])
        self.assertEqual(role_upd["roles"]["chat"], "gemini:gemini-3-flash-preview")

        mail_prep = h3._dispatch_tool_call(
            "settings_prepare_add_mail_account",
            {"email": "work@gmail.com"},
        )
        self.assertTrue(mail_prep["ok"])
        self.assertEqual(h3.ui_cards[-1]["kind"], "mail_account_card")

        prov_prep = h3._dispatch_tool_call(
            "settings_infer_and_prepare_provider",
            {"url_or_name": "booking.com"},
        )
        self.assertTrue(prov_prep["ok"])
        self.assertEqual(h3.ui_cards[-1]["kind"], "provider_preview_card")

    def test_deterministic_fallback_emits_cards_when_small_model_skips_tools(self) -> None:
        self.rt.passwords.create_profile("nikita", "123456")
        self.rt._refresh_active_profile_brain()

        st_g = stage_settings_file(
            self.rt,
            filename="client_secret.json",
            content_text=SAMPLE_CLIENT_JSON,
        )["staged"]
        h = self._make_harness(origin="settings", staged_files=[st_g])
        cards = maybe_fallback_settings_cards(
            self.rt,
            h,
            user_msg="please connect google with this secrets file",
            staged_files=[st_g],
        )
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["kind"], "google_oauth_connect_card")

        h_prof = self._make_harness(origin="settings")
        cards_p = maybe_fallback_settings_cards(
            self.rt,
            h_prof,
            user_msg="let's create a work profile called ngorshkov",
        )
        self.assertEqual(len(cards_p), 1)
        self.assertEqual(cards_p[0]["kind"], "profile_create_card")
        self.assertEqual(cards_p[0]["data"]["profile_name"], "ngorshkov")

    def test_http_stage_file_local_gemma_cloud_gemini_and_openai_tool_loops(self) -> None:
        self.rt.passwords.create_profile("http_tester", "246810")
        self.rt._refresh_active_profile_brain()

        httpd = make_sidecar_server(self.rt, host="127.0.0.1", port=0, auth_token="tok-settings-test")
        port = httpd.server_address[1]
        th = threading.Thread(target=httpd.serve_forever, daemon=True)
        th.start()

        def _http_post_json(path: str, body: dict) -> tuple[int, dict]:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}",
                data=json.dumps(body).encode("utf-8"),
                headers={"X-Satz-Token": "tok-settings-test", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return resp.status, json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as he:
                return he.code, json.loads(he.read().decode("utf-8"))

        def _http_post_sse(path: str, body: dict) -> list[dict]:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}",
                data=json.dumps(body).encode("utf-8"),
                headers={"X-Satz-Token": "tok-settings-test", "Content-Type": "application/json"},
                method="POST",
            )
            events: list[dict] = []
            with urllib.request.urlopen(req, timeout=15) as resp:
                for raw_line in resp.read().decode("utf-8").splitlines():
                    if raw_line.startswith("data:"):
                        events.append(json.loads(raw_line[5:].strip()))
            return events

        try:
            # 1. Stage client_secret.json via HTTP (must NEVER return client_secret)
            code, st_res = _http_post_json(
                "/settings/stage_file",
                {"filename": "client_secret_http.json", "mime": "application/json", "content_text": SAMPLE_CLIENT_JSON},
            )
            self.assertEqual(code, 200)
            self.assertTrue(st_res["ok"])
            staged = st_res["staged"]
            self.assertNotIn("GOCSPX-ultra-secret", json.dumps(st_res))

            # 2. Local Gemma SSE chat on origin="settings" configures Google OAuth cleanly
            import numpy  # noqa: F401
            import torch

            round_g = {"n": 0}

            class _FakeInputs(dict):
                def __init__(self) -> None:
                    super().__init__()
                    self["input_ids"] = torch.zeros((1, 8), dtype=torch.long)

                def to(self, _dev):
                    return self

            class _FakeTok:
                def apply_chat_template(self, chat_m, **kw):
                    return _FakeInputs()

                def decode(self, ids, skip_special_tokens=True):
                    return ""

            class _FakeStreamer:
                def __init__(self, tok, skip_prompt=True, skip_special_tokens=True):
                    self._q: list[str | None] = []
                    self._ev = threading.Event()

                def feed(self, pcs: list[str]):
                    self._q.extend(pcs)
                    self._q.append(None)
                    self._ev.set()

                def __iter__(self):
                    self._ev.wait(timeout=2.0)
                    for p in self._q:
                        if p is None:
                            break
                        yield p

            class _FakeModel:
                device = "cpu"

                def generate(self, **kw):
                    st_obj = kw.get("streamer")
                    r = round_g["n"]
                    round_g["n"] += 1
                    if r == 0:
                        tc = json.dumps(
                            {
                                "name": "settings_configure_google_oauth",
                                "arguments": {"staging_id": staged["staging_id"], "scopes_preset": "gmail"},
                            }
                        )
                        st_obj.feed([f"<tool_call>{tc}</tool_call>"])
                    else:
                        st_obj.feed(["Saved your Google OAuth client into vault.enc. Click Open Google sign-in below."])

            fake_tf = types.ModuleType("transformers")
            fake_tf.TextIteratorStreamer = _FakeStreamer  # type: ignore[attr-defined]
            fake_tf.AutoProcessor = mock.MagicMock()  # type: ignore[attr-defined]

            with mock.patch.dict(sys.modules, {"transformers": fake_tf}), \
                 mock.patch.object(self.rt, "ensure_gemma", return_value=(_FakeTok(), _FakeModel())):
                gemma_evs = _http_post_sse(
                    "/chat",
                    {
                        "model": "gemma-4-e4b",
                        "origin": "settings",
                        "conversation_id": "conv-settings",
                        "staged_files": [staged],
                        "messages": [{"role": "user", "content": "Add this google secrets file"}],
                        "sources": [],
                    },
                )
            done_g = [e for e in gemma_evs if e.get("done")][-1]
            self.assertEqual(done_g["effective_model"], "gemma-4-e4b")
            self.assertIn("settings_configure_google_oauth", done_g["tools_used"])
            self.assertEqual(done_g["ui_cards"][0]["kind"], "google_oauth_connect_card")
            self.assertTrue(self.rt.google_auth.get_status()["configured"])

            # 3. Cloud Gemini tool call creates profile card over HTTP /chat
            gem_round = {"n": 0}

            class _FakeHttpResp:
                def __init__(self, obj: dict) -> None:
                    self._b = json.dumps(obj).encode("utf-8")

                def read(self) -> bytes:
                    return self._b

                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return False

            orig_urlopen = urllib.request.urlopen

            def _fake_gem_urlopen(req, timeout=28.0):
                url_str = req.full_url if hasattr(req, "full_url") else str(req)
                if url_str.startswith("http://127.0.0.1"):
                    return orig_urlopen(req, timeout=timeout)
                body = json.loads(req.data.decode("utf-8"))
                # Verify only Settings tools are declared (zero unrelated web tools when web=off)
                decls = [fd["name"] for t in (body.get("tools") or []) for fd in (t.get("functionDeclarations") or [])]
                self.assertIn("settings_prepare_create_profile", decls)
                self.assertNotIn("web_search", decls)
                r = gem_round["n"]
                gem_round["n"] += 1
                if r == 0:
                    return _FakeHttpResp(
                        {
                            "candidates": [
                                {
                                    "content": {
                                        "role": "model",
                                        "parts": [
                                            {
                                                "functionCall": {
                                                    "name": "settings_prepare_create_profile",
                                                    "args": {"profile_name": "ngorshkov"},
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
                                    "parts": [{"text": "Set a 6-digit PIN inside the Create profile card below."}],
                                }
                            }
                        ]
                    }
                )

            with mock.patch.object(self.rt, "_resolve_provider_api_key", return_value=("gem-key", "vault")), \
                 mock.patch("urllib.request.urlopen", side_effect=_fake_gem_urlopen):
                cloud_evs = _http_post_sse(
                    "/chat",
                    {
                        "model": "gemini:gemini-3-flash-preview",
                        "origin": "settings",
                        "conversation_id": "conv-settings",
                        "messages": [{"role": "user", "content": "create a work profile called ngorshkov"}],
                        "sources": [],
                    },
                )
            done_c = [e for e in cloud_evs if e.get("done")][-1]
            self.assertEqual(done_c["effective_model"], "gemini:gemini-3-flash-preview")
            self.assertIn("settings_prepare_create_profile", done_c["tools_used"])
            self.assertEqual(done_c["ui_cards"][0]["kind"], "profile_create_card")

            # 4. Cloud OpenAI-compat tool loop works identically on origin="settings"
            oa_round = {"n": 0}

            def _fake_oa_urlopen(req, timeout=30.0):
                body = json.loads(req.data.decode("utf-8"))
                tool_names = [t["function"]["name"] for t in (body.get("tools") or [])]
                self.assertIn("settings_stage_api_key_or_env", tool_names)
                r = oa_round["n"]
                oa_round["n"] += 1
                if r == 0:
                    return _FakeHttpResp(
                        {
                            "choices": [
                                {
                                    "message": {
                                        "role": "assistant",
                                        "tool_calls": [
                                            {
                                                "id": "call_oa_1",
                                                "type": "function",
                                                "function": {
                                                    "name": "settings_stage_api_key_or_env",
                                                    "arguments": json.dumps({"provider_id": "openai"}),
                                                },
                                            }
                                        ],
                                    }
                                }
                            ]
                        }
                    )
                return _FakeHttpResp(
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": "Paste your OpenAI API key in the masked card below.",
                                }
                            }
                        ]
                    }
                )

            with mock.patch.object(self.rt, "_resolve_provider_api_key", return_value=("oa-key", "vault")), \
                 mock.patch("urllib.request.urlopen", side_effect=_fake_oa_urlopen):
                oa_evs = list(
                    self.rt.stream_chat(
                        [{"role": "user", "content": "add an openai api key"}],
                        [],
                        model_id="openai:gpt-4o-mini",
                        conversation_id="conv-settings",
                        origin="settings",
                    )
                )
            done_oa = [e for e in oa_evs if e.get("done")][-1]
            self.assertIn("settings_stage_api_key_or_env", done_oa["tools_used"])
            self.assertEqual(done_oa["ui_cards"][0]["kind"], "vault_secret_input_card")

            # 5. HTTP confirm_gate executes staged .env import once & blocks replay; /profile/lock clears state
            code_e, st_e = _http_post_json(
                "/settings/stage_file",
                {"filename": ".env", "mime": "text/plain", "content_text": SAMPLE_ENV},
            )
            self.assertEqual(code_e, 200)
            h_tmp = self._make_harness(origin="settings", staged_files=[st_e["staged"]])
            h_tmp._dispatch_tool_call("settings_stage_api_key_or_env", {"staging_id": st_e["staged"]["staging_id"]})
            tok_http = h_tmp.ui_cards[-1]["confirm_token"]

            g_code, g_res = _http_post_json("/settings/confirm_gate", {"confirm_token": tok_http})
            self.assertEqual(g_code, 200)
            self.assertTrue(g_res["ok"])
            r_code, r_res = _http_post_json("/settings/confirm_gate", {"confirm_token": tok_http})
            self.assertEqual(r_code, 400)
            self.assertFalse(r_res["ok"])

            lock_code, _ = _http_post_json("/profile/lock", {})
            self.assertEqual(lock_code, 200)
            self.assertEqual(self.rt._staged_files, {})
            self.assertEqual(self.rt._pending_settings_gates, {})
        finally:
            try:
                httpd.shutdown()
                httpd.server_close()
            except Exception:
                pass

    def test_settings_i18n_tools_and_fallback_cards(self) -> None:
        h = self._make_harness(origin="settings")

        # 1. Inspect initial status + search catalog keys app-wide
        st = h._dispatch_tool_call("settings_get_language_status", {"query": "common.save"})
        self.assertTrue(st["ok"])
        self.assertEqual(st["scope"], "app_wide_across_profiles")
        self.assertEqual(st["active_locale"], "en")
        self.assertTrue(st["default_model"])
        self.assertTrue(any(m["key"] == "common.save" for m in st.get("matching_keys", [])))

        # 2. Prepare language translation emits locale_translate_card with model & privacy metadata
        prep = h._dispatch_tool_call("settings_prepare_language_translation", {"language": "German"})
        self.assertTrue(prep["ok"])
        self.assertEqual(prep["lang"], "de")
        self.assertEqual(prep["dir"], "ltr")
        self.assertGreater(prep["total"], 0)
        self.assertEqual(prep["ui_card_emitted"], "locale_translate_card")
        prep_card = h.ui_cards[-1]
        self.assertEqual(prep_card["kind"], "locale_translate_card")
        self.assertEqual(prep_card["title_key"], "i18n.card_title")
        self.assertEqual(prep_card["subtitle_key"], "i18n.card_sub")
        self.assertEqual(prep_card["data"]["lang"], "de")
        self.assertIn("privacy", prep_card["data"])

        # 3. Custom override + reset protects user edits
        ov = h._dispatch_tool_call(
            "settings_set_ui_translation_override",
            {"language": "de", "key": "common.save", "translation": "Jetzt sichern"},
        )
        self.assertTrue(ov["ok"])
        self.assertTrue(ov["entry"]["custom"])
        self.assertEqual(ov["entry"]["text"], "Jetzt sichern")
        bundle = self.rt.i18n.get_bundle("de")
        self.assertEqual(bundle["entries"]["common.save"]["text"], "Jetzt sichern")

        ov_reset = h._dispatch_tool_call(
            "settings_set_ui_translation_override",
            {"language": "de", "key": "common.save", "reset": True},
        )
        self.assertTrue(ov_reset["ok"])

        # 4. Switching language triggers background sync and persists across profile creation/switching
        with mock.patch.object(
            self.rt.i18n,
            "start_background_translation",
            return_value={"ok": True, "started": True},
        ) as bg_mock:
            sw_de = h._dispatch_tool_call("settings_switch_language", {"language": "German"})
        self.assertTrue(sw_de["ok"])
        self.assertEqual(sw_de["active_locale"], "de")
        self.assertTrue(sw_de["background_sync_started"])
        self.assertTrue(bg_mock.called)
        self.assertEqual(h.ui_cards[-1]["kind"], "locale_translate_card")

        self.rt.passwords.create_profile("work_de", "135790")
        after_prof = h._dispatch_tool_call("settings_get_language_status", {})
        self.assertEqual(after_prof["active_locale"], "de")

        sw_en = h._dispatch_tool_call("settings_switch_language", {"language": "en"})
        self.assertTrue(sw_en["ok"])
        self.assertEqual(sw_en["active_locale"], "en")

        # 5. Deterministic fallback detects natural-language UI translation requests
        h_fb1 = self._make_harness(origin="settings")
        cards_de = maybe_fallback_settings_cards(
            self.rt,
            h_fb1,
            user_msg="translate interface to German",
        )
        self.assertEqual(len(cards_de), 1)
        self.assertEqual(cards_de[0]["kind"], "locale_translate_card")
        self.assertEqual(cards_de[0]["data"]["lang"], "de")

        h_fb2 = self._make_harness(origin="settings")
        cards_fr = maybe_fallback_settings_cards(
            self.rt,
            h_fb2,
            user_msg="translate the UI language to French using my default model",
        )
        self.assertEqual(len(cards_fr), 1)
        self.assertEqual(cards_fr[0]["kind"], "locale_translate_card")
        self.assertEqual(cards_fr[0]["data"]["lang"], "fr")

        h_fb3 = self._make_harness(origin="settings")
        cards_en = maybe_fallback_settings_cards(
            self.rt,
            h_fb3,
            user_msg="switch UI language to English",
        )
        self.assertEqual(len(cards_en), 1)
        self.assertEqual(cards_en[0]["kind"], "locale_translate_card")
        self.assertEqual(cards_en[0]["data"]["lang"], "en")

    def test_settings_inline_secret_staging_skips_brain_and_recovers_on_cloud_503(self) -> None:
        self.rt.passwords.create_profile("work_test", "135790")
        self.rt._refresh_active_profile_brain()

        seen_payloads: list[str] = []

        def _failing_503_urlopen(req, timeout=30.0):
            seen_payloads.append(req.data.decode("utf-8", errors="replace") if getattr(req, "data", None) else "")
            raise urllib.error.HTTPError(
                req.full_url, 503, "Service Unavailable", {}, None
            )

        with mock.patch.object(
            self.rt.brain,
            "build_model_context_with_citations",
            side_effect=AssertionError("Brain lookup must not run in Settings Chat"),
        ), mock.patch.object(
            self.rt, "_resolve_provider_api_key", return_value=("gem-key", "vault")
        ), mock.patch(
            "urllib.request.urlopen", side_effect=_failing_503_urlopen
        ):
            raw_msg = (
                "So here is the client secret for my work email. "
                f"Can we add the work email to the profile as well: {SAMPLE_CLIENT_JSON}"
            )
            evs1 = list(
                self.rt.stream_chat(
                    [{"role": "user", "content": raw_msg}],
                    [],
                    model_id="gemini:gemini-4-hydrogen",
                    conversation_id="conv-settings",
                    origin="settings",
                )
            )
            done1 = [e for e in evs1 if e.get("done")][-1]
            self.assertEqual(done1["brain_sources"], [])
            self.assertEqual(done1["ui_cards"][0]["kind"], "google_oauth_connect_card")
            self.assertTrue(self.rt.google_auth.get_status()["configured"])
            # Ensure raw client_secret never leaked into any cloud HTTP payload
            self.assertGreater(len(seen_payloads), 0)
            for payload_txt in seen_payloads:
                self.assertNotIn("GOCSPX-ultra-secret", payload_txt)
                self.assertIn("staged client_secret_pasted.json", payload_txt)

            # Second turn: "Connect a Google account" also recovers via card when Gemini 503s
            evs2 = list(
                self.rt.stream_chat(
                    [
                        {"role": "user", "content": raw_msg},
                        {"role": "user", "content": "Connect a Google account"},
                    ],
                    [],
                    model_id="gemini:gemini-4-hydrogen",
                    conversation_id="conv-settings",
                    origin="settings",
                )
            )
            done2 = [e for e in evs2 if e.get("done")][-1]
            self.assertEqual(done2["brain_sources"], [])
            self.assertEqual(done2["ui_cards"][0]["kind"], "google_oauth_connect_card")


if __name__ == "__main__":
    unittest.main()
