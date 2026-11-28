#!/usr/bin/env python3
"""Unit & integration tests for app-wide Satz UI localization (`satz_i18n.py`)."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

SIDECAR_DIR = Path(__file__).resolve().parent
SGS_ROOT = SIDECAR_DIR.parent.parent / "sgs"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))
if str(SGS_ROOT) not in sys.path:
    sys.path.insert(0, str(SGS_ROOT))

from satz_google_auth import _render_callback_html
from satz_i18n import (
    compute_source_hash,
    normalize_lang_spec,
    parse_ts_catalog_file,
)
from satz_models import SatzSidecarRuntime, make_sidecar_server


MINI_CATALOG = {
    "common.close": {"text": "Close", "hint": "button label"},
    "mail.sync_now": {"text": "Sync now"},
    "mail.synced_age": {"text": "Synced {age}"},
    "rail.src_count": {"text": "{count} src"},
    "start.item_count": {"text": "{count} items", "one": "{count} item"},
}


class TestSatzI18n(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="satz_test_i18n_"))
        store_path = self.temp_dir / "planck_store.sqlite"
        self.rt = SatzSidecarRuntime(sgs_root=SGS_ROOT, store_path=store_path)
        self.rt.mail.pipeline.stop_worker()

    def tearDown(self) -> None:
        try:
            self.rt.close()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_lang_normalization_and_rtl(self) -> None:
        self.assertEqual(normalize_lang_spec("German"), {"lang": "de", "label": "Deutsch", "dir": "ltr"})
        self.assertEqual(normalize_lang_spec("Arabic"), {"lang": "ar", "label": "العربية", "dir": "rtl"})
        self.assertEqual(normalize_lang_spec("he"), {"lang": "he", "label": "עברית", "dir": "rtl"})
        self.assertEqual(normalize_lang_spec("pt-BR"), {"lang": "pt-br", "label": "Português (BR)", "dir": "ltr"})
        self.assertEqual(normalize_lang_spec("Pirate"), {"lang": "pirate", "label": "Pirate", "dir": "ltr"})

    def test_ts_catalog_parses_full_repo_catalog(self) -> None:
        ts_path = SIDECAR_DIR.parent / "src" / "i18n" / "catalog.ts"
        cat = parse_ts_catalog_file(ts_path)
        self.assertGreater(len(cat), 900)
        self.assertEqual(cat["common.close"]["text"], "Close")
        self.assertEqual(cat["mail.status_synced_n"]["one"], "Synced {count} new message.")

    def test_model_resolution_uses_default_chat_role_with_guard(self) -> None:
        # Default starts at gemma-4-e4b (local)
        info_local = self.rt.i18n.resolve_translation_model()
        self.assertEqual(info_local["model_id"], "gemma-4-e4b")
        self.assertTrue(info_local["local_only"])

        # Switch chat role to cloud model
        self.rt.update_model_management_config({"role_chat": "gemini:gemini-4-hydrogen (cloud)"})
        info_cloud = self.rt.i18n.resolve_translation_model()
        self.assertEqual(info_cloud["model_id"], "gemini:gemini-4-hydrogen (cloud)")
        self.assertFalse(info_cloud["local_only"])
        self.assertEqual(info_cloud["host"], "generativelanguage.googleapis.com")

        # Non-generative role value safely falls back to gemma-4-e4b
        self.rt.update_model_management_config({"role_chat": "planck3 (web)"})
        info_guard = self.rt.i18n.resolve_translation_model()
        self.assertEqual(info_guard["model_id"], "gemma-4-e4b")
        self.assertTrue(info_guard["local_only"])

    def test_batch_translation_placeholder_retry_and_fallback(self) -> None:
        calls: list[dict] = []

        def fake_complete(model_id: str, sys_p: str, user_p: str, temperature: float = 0.1, max_tokens: int = 2400) -> str:
            idx = user_p.find("{")
            req_map = json.loads(user_p[idx:])
            calls.append({"model_id": model_id, "keys": list(req_map.keys()), "retry": any("fix_note" in v for v in req_map.values())})
            if not calls[-1]["retry"]:
                # First pass: drop {age} placeholder on mail.synced_age, include an em-dash on common.close
                return json.dumps(
                    {
                        "common.close": {"text": "Schließen\u2014jetzt"},
                        "mail.sync_now": {"text": "Jetzt synchronisieren"},
                        "mail.synced_age": {"text": "Synchronisiert {zeit}"},
                        "rail.src_count": {"text": "{count} Quelle"},
                        "start.item_count": {"text": "{count} Elemente", "one": "{count} Element"},
                    }
                )
            # Retry fixes mail.synced_age properly
            return json.dumps({"mail.synced_age": {"text": "Vor {age} synchronisiert"}})

        with mock.patch.object(self.rt, "_complete_role_prompt", side_effect=fake_complete):
            res = self.rt.i18n.translate_sync("German", catalog=MINI_CATALOG, batch_size=10)

        self.assertTrue(res["ok"])
        self.assertEqual(res["lang"], "de")
        self.assertEqual(res["translated_now"], 5)
        self.assertEqual(res["skipped_or_failed"], 0)
        # Em dash normalized to '-'
        self.assertEqual(res["entries"]["common.close"]["text"], "Schließen-jetzt")
        # Retried key succeeded on second pass
        self.assertEqual(res["entries"]["mail.synced_age"]["text"], "Vor {age} synchronisiert")
        self.assertTrue(len(calls) == 2 and calls[1]["retry"])

        # Corrupt retry leaves key out cleanly rather than corrupting placeholders
        def always_bad(model_id: str, sys_p: str, user_p: str, **_kw) -> str:
            return json.dumps({"mail.synced_age": {"text": "Missing placeholder"}})

        with mock.patch.object(self.rt, "_complete_role_prompt", side_effect=always_bad):
            res_bad = self.rt.i18n.translate_sync("fr", catalog={"mail.synced_age": MINI_CATALOG["mail.synced_age"]})
        self.assertTrue(res_bad["ok"])
        self.assertEqual(res_bad["skipped_or_failed"], 1)
        self.assertNotIn("mail.synced_age", res_bad["entries"])

    def test_custom_override_preserved_and_app_wide_across_profiles(self) -> None:
        # 1. Seed a German pack while profile is still locked
        with mock.patch.object(
            self.rt,
            "_complete_role_prompt",
            return_value=json.dumps(
                {
                    "common.close": {"text": "Schließen"},
                    "mail.sync_now": {"text": "Sync jetzt"},
                    "mail.synced_age": {"text": "Vor {age}"},
                    "rail.src_count": {"text": "{count} Q."},
                    "start.item_count": {"text": "{count} Einträge", "one": "{count} Eintrag"},
                }
            ),
        ):
            self.rt.i18n.translate_sync("de", catalog=MINI_CATALOG)

        # 2. Add a custom manual override
        ov = self.rt.i18n.override_entry("de", "mail.sync_now", "Abrufen", catalog=MINI_CATALOG)
        self.assertTrue(ov["ok"])
        self.assertTrue(ov["entry"]["custom"])

        # 3. Simulate canonical English key change + missing key: override stays protected!
        updated_cat = {
            **MINI_CATALOG,
            "common.close": {"text": "Close window"},
            "common.new_key": {"text": "New action"},
        }
        status_pre = self.rt.i18n.get_status(lang="de", catalog=updated_cat)
        self.assertEqual(status_pre["active_locale"], "de")
        self.assertEqual(status_pre["target"]["missing"], 1)
        self.assertEqual(status_pre["target"]["stale"], 1)
        self.assertEqual(status_pre["target"]["custom_count"], 1)

        with mock.patch.object(
            self.rt,
            "_complete_role_prompt",
            return_value=json.dumps(
                {
                    "common.close": {"text": "Fenster schließen"},
                    "common.new_key": {"text": "Neue Aktion"},
                }
            ),
        ):
            res2 = self.rt.i18n.translate_sync("de", catalog=updated_cat, only_missing=True)

        self.assertTrue(res2["ok"])
        self.assertEqual(res2["translated_now"], 2)
        self.assertEqual(res2["entries"]["mail.sync_now"]["text"], "Abrufen")
        self.assertTrue(res2["entries"]["mail.sync_now"]["custom"])
        self.assertEqual(res2["entries"]["common.close"]["text"], "Fenster schließen")

        # 4. Create & lock a user profile -> app-wide i18n remains untouched and in German
        prof_res = self.rt.passwords.create_profile("Work", "123456")
        self.assertTrue(prof_res.get("unlocked"))
        self.assertEqual((prof_res.get("active_profile") or {}).get("name"), "Work")
        self.assertEqual(self.rt.i18n.get_status(catalog=updated_cat)["active_locale"], "de")
        self.rt.passwords.lock_profile()
        self.assertEqual(self.rt.i18n.get_status(catalog=updated_cat)["active_locale"], "de")
        self.assertEqual(self.rt.i18n.i18n_dir, (self.temp_dir / "i18n").resolve())

    def test_oauth_callback_html_uses_active_locale_and_rtl(self) -> None:
        self.rt.i18n.import_pack(
            {
                "lang": "ar",
                "label": "العربية",
                "dir": "rtl",
                "entries": {
                    "oauth.cb_title": {"text": "مصادقة جوجل · Satz"},
                    "oauth.cb_connected": {"text": "تم الاتصال"},
                    "oauth.cb_failed": {"text": "فشل المصادقة"},
                    "oauth.cb_hint": {"text": "تم حفظ الرموز بأمان."},
                },
            },
            activate=True,
        )
        cb_copy = self.rt.i18n.format_oauth_callback_copy(True, "Signed in", "Done")
        html_bytes = _render_callback_html(
            True,
            cb_copy["headline"],
            cb_copy["detail"],
            lang=cb_copy["lang"],
            direction=cb_copy["dir"],
            page_title=cb_copy["title"],
            badge_text=cb_copy["badge"],
            hint_text=cb_copy["hint"],
        )
        html_str = html_bytes.decode("utf-8")
        self.assertIn('lang="ar" dir="rtl"', html_str)
        self.assertIn("تم الاتصال", html_str)

    def test_http_endpoints_sse_background_export_import_and_cancel(self) -> None:
        token = "test-i18n-token"
        server = make_sidecar_server(self.rt, host="127.0.0.1", port=0, auth_token=token)
        port = int(server.server_address[1])
        srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
        srv_thread.start()
        try:
            def _req(path: str, data: dict | None = None, method: str = "GET") -> tuple[int, str]:
                body = json.dumps(data).encode("utf-8") if data is not None else None
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}{path}",
                    data=body,
                    method=method,
                    headers={
                        "X-Satz-Token": token,
                        **({"Content-Type": "application/json"} if body is not None else {}),
                    },
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return resp.status, resp.read().decode("utf-8")

            def fake_complete(_m: str, _s: str, user_p: str, **_kw) -> str:
                req_map = json.loads(user_p[user_p.find("{") :])
                return json.dumps({k: {"text": f"ES:{v['text']}", **({"one": f"ES1:{v['one']}"} if "one" in v else {})} for k, v in req_map.items()})

            with mock.patch.object(self.rt, "_complete_role_prompt", side_effect=fake_complete):
                # SSE stream translate
                code, raw_sse = _req(
                    "/i18n/translate",
                    {"lang": "es", "catalog": MINI_CATALOG, "stream": True, "activate": True},
                    method="POST",
                )
                self.assertEqual(code, 200)
                self.assertIn('"phase": "start"', raw_sse)
                self.assertIn('"phase": "batch"', raw_sse)
                self.assertIn('"phase": "done"', raw_sse)

                # Bundle + status check
                code_b, raw_b = _req("/i18n/bundle?lang=es")
                self.assertEqual(code_b, 200)
                bundle = json.loads(raw_b)
                self.assertEqual(bundle["entries"]["common.close"]["text"], "ES:Close")
                self.assertEqual(compute_source_hash(MINI_CATALOG["common.close"]), bundle["entries"]["common.close"]["source_hash"])

                # Export & import
                code_ex, raw_ex = _req("/i18n/export?lang=es")
                self.assertEqual(code_ex, 200)
                pack = json.loads(raw_ex)["pack"]
                pack["lang"] = "it"
                pack["label"] = "Italiano"
                code_im, raw_im = _req("/i18n/import", {"pack": pack, "activate": False}, method="POST")
                self.assertEqual(code_im, 200)
                self.assertEqual(json.loads(raw_im)["lang"], "it")

                # Switch-only to en then back to es with extra key triggers background sync
                code_sw, raw_sw = _req(
                    "/i18n/translate",
                    {
                        "lang": "es",
                        "switch_only": True,
                        "sync_missing": True,
                        "catalog": {**MINI_CATALOG, "common.extra": {"text": "Extra"}},
                    },
                    method="POST",
                )
                self.assertEqual(code_sw, 200)
                sw_obj = json.loads(raw_sw)
                self.assertEqual(sw_obj["active_locale"], "es")
                self.assertTrue(sw_obj["background_job"]["started"])
                # Allow daemon thread to finish mocked batch before exiting patch scope
                if self.rt.i18n._bg_thread is not None:
                    self.rt.i18n._bg_thread.join(timeout=5)
                es_after = self.rt.i18n.get_bundle("es")["entries"]
                self.assertEqual(es_after["common.extra"]["text"], "ES:Extra")

                # Cancel endpoint returns ok
                code_c, raw_c = _req("/i18n/cancel", {"lang": "es"}, method="POST")
                self.assertEqual(code_c, 200)
                self.assertTrue(json.loads(raw_c)["ok"])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
