#!/usr/bin/env python3
"""Tests for local model packaging: shipped Planck, missing Gemma handling, local linking, and HF downloader."""
from __future__ import annotations

import http.server
import io
import json
import shutil
import socketserver
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

SIDECAR_DIR = Path(__file__).resolve().parent
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))

from satz_models import SatzSidecarRuntime, make_sidecar_server


def _post_json(base_url: str, path: str, payload: dict, token: str = "") -> tuple[int, dict]:
    import urllib.error
    import urllib.request

    data = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["X-Satz-Token"] = token
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers=hdrs,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as he:
        return he.code, json.loads(he.read().decode("utf-8"))


def _get_json(base_url: str, path: str, token: str = "") -> tuple[int, dict]:
    import urllib.request

    hdrs = {"X-Satz-Token": token} if token else {}
    req = urllib.request.Request(f"{base_url}{path}", headers=hdrs, method="GET")
    with urllib.request.urlopen(req, timeout=10.0) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


class TestLocalModelsPackaging(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="satz_test_lm_"))
        self.missing_sgs = self.temp_dir / "nonexistent_sgs"
        self.store_path = self.temp_dir / "planck_store.sqlite"
        self.rt = SatzSidecarRuntime(sgs_root=self.missing_sgs, store_path=self.store_path)
        self.rt.mail.pipeline.stop_worker()

    def tearDown(self) -> None:
        try:
            self.rt.close()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_shipped_planck_chunks_under_github_limit_and_standalone_ready(self) -> None:
        planck_dir = SIDECAR_DIR / "models" / "planck"
        self.assertTrue((planck_dir / "tokenizer.model").is_file())
        self.assertTrue((planck_dir / "xreader_planck" / "manifest.json").is_file())
        self.assertTrue((planck_dir / "planck13" / "manifest.json").is_file())
        max_bytes = 90 * 1024 * 1024
        for p in planck_dir.rglob("*"):
            if p.is_file():
                self.assertLessEqual(
                    p.stat().st_size,
                    max_bytes,
                    f"Shipped model artifact exceeds 90 MB GitHub limit: {p}",
                )

        doc = self.rt.get_doctor()
        by_role = {r["role"]: r for r in doc["roles"]}
        self.assertEqual(by_role["chat"]["state"], "missing")
        self.assertEqual(by_role["web_answer"]["state"], "ready")
        self.assertEqual(by_role["reader_planck"]["state"], "ready")
        self.assertEqual(by_role["reader_planck"]["source"], "shipped")
        self.assertEqual(by_role["brain_encoder"]["state"], "ready")
        self.assertEqual(by_role["brain_encoder"]["source"], "shipped")
        self.assertIn("semantic (planck13)", doc["brain_ranking"])

        health = self.rt.get_health()
        ids = [m["id"] for m in health["models"]]
        self.assertEqual(ids[:4], ["gemma-4-e4b", "planck3 (web)", "hertz (reader)", "planck (reader)"])
        by_id = {m["id"]: m for m in health["models"]}
        self.assertEqual(by_id["planck3 (web)"]["state"], "not_loaded")
        self.assertEqual(by_id["planck (reader)"]["state"], "not_loaded")

        # Load answerer & run reader fallback (hertz missing -> shipped planck) with no sgs directory
        ans = self.rt.ensure_answerer()
        self.assertIsNotNone(ans)
        read_res = self.rt.run_read(
            "hertz (reader)",
            "Who won the award in 2024?",
            [
                {
                    "id": "src-1",
                    "url": "https://example.org/award",
                    "title": "Award",
                    "text": "In 2024, Ada Lovelace Institute won the open benchmark award for local models.",
                }
            ],
        )
        self.assertIn("answer", read_res)
        self.assertTrue(bool(read_res["answer"].strip()))

        # Load Brain Planck 1.3 encoder directly from shipped shards
        enc = self.rt.brain._get_encoder()
        self.assertIsNotNone(enc)
        self.assertEqual(getattr(enc, "name", "planck"), "planck")
        vecs = enc.encode(["local browser search engine", "strawberry pie recipe"])
        self.assertEqual(vecs.shape[0], 2)
        self.assertGreater(vecs.shape[1], 100)

    def test_missing_gemma_skips_preload_and_falls_back_gracefully(self) -> None:
        self.rt.start_gemma_preload()
        time.sleep(0.25)
        errs = [e for e in self.rt.get_errors() if e.get("where") == "gemma_preload"]
        self.assertEqual(errs, [])

        # Chat without any local LLM or cloud key raises an actionable Settings error
        with self.assertRaises(RuntimeError) as ctx:
            list(
                self.rt.stream_chat(
                    model_id="gemma-4-e4b",
                    messages=[{"role": "user", "content": "hello"}],
                    sources=[],
                    web_enabled=False,
                )
            )
        self.assertIn("Settings -> Models", str(ctx.exception))

        # Settings origin falls back cleanly to deterministic Settings cards instead of failing
        evs = list(
            self.rt.stream_chat(
                model_id="gemma-4-e4b",
                messages=[{"role": "user", "content": "configure my gemini api key"}],
                sources=[],
                web_enabled=False,
                origin="settings",
                conversation_id="conv-settings",
            )
        )
        joined = "".join(str(e.get("delta") or "") for e in evs)
        self.assertTrue(
            any(e.get("ui_cards") for e in evs) or "Settings" in joined,
            f"Expected Settings UI card or note, got: {evs}",
        )

        # When a cloud provider key + model is configured, effective_chat & stream_chat use it
        with self.rt.store_lock:
            self.rt.store.db.execute(
                "INSERT OR REPLACE INTO satz_meta (key, value) VALUES (?, ?)",
                ("cloud_api_key_gemini", "AIzaSyFakeKeyForUnitTest1234"),
            )
            self.rt.store.db.execute(
                "INSERT OR REPLACE INTO satz_meta (key, value) VALUES (?, ?)",
                (
                    "cloud_models_gemini",
                    json.dumps([{"id": "gemini:gemini-3-flash-preview", "slug": "gemini-3-flash-preview", "label": "Gemini 3 Flash", "provider": "gemini"}]),
                ),
            )
            self.rt.store.db.commit()

        cfg = self.rt.get_model_management_config()
        self.assertEqual(cfg["roles"]["chat"], "gemma-4-e4b")
        self.assertEqual(cfg["roles"]["effective_chat"], "gemini:gemini-3-flash-preview")

        with mock.patch("satz_web_harness.stream_cloud_chat") as m_cloud:
            m_cloud.return_value = iter([{"delta": "Cloud reply ok"}, {"__full_raw": "Cloud reply ok"}])
            evs_cloud = list(
                self.rt.stream_chat(
                    model_id="gemma-4-e4b",
                    messages=[{"role": "user", "content": "hello"}],
                    sources=[],
                    web_enabled=False,
                )
            )
        self.assertTrue(any(e.get("phase") == "fallback" for e in evs_cloud))
        self.assertTrue(any("Cloud reply ok" in str(e.get("delta") or "") for e in evs_cloud))

    def test_http_point_local_model_token_and_remove(self) -> None:
        srv = make_sidecar_server(self.rt, host="127.0.0.1", port=0)
        port = srv.server_address[1]
        tok = srv.auth_token
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        base = f"http://127.0.0.1:{port}"
        try:
            # Bad directory rejected
            bad_dir = self.temp_dir / "empty_folder"
            bad_dir.mkdir(parents=True)
            st, res_bad = _post_json(
                base,
                "/models/local/add",
                {"role_slot": "chat_llm", "path": str(bad_dir)},
                token=tok,
            )
            self.assertEqual(st, 400)
            self.assertFalse(res_bad["ok"])

            # Valid HF folder linked and set active
            good_dir = self.temp_dir / "Qwen2.5-1.5B-Instruct"
            good_dir.mkdir(parents=True)
            (good_dir / "config.json").write_text('{"model_type": "qwen2"}', encoding="utf-8")
            (good_dir / "model.safetensors").write_bytes(b"weights")
            st, res_ok = _post_json(
                base,
                "/models/local/add",
                {"role_slot": "chat_llm", "path": str(good_dir), "set_active": True},
                token=tok,
            )
            self.assertEqual(st, 200)
            self.assertTrue(res_ok["ok"])
            mid = res_ok["model_id"]
            self.assertEqual(mid, "local:Qwen2.5-1.5B-Instruct")
            self.assertEqual(res_ok["roles"]["chat"], mid)
            self.assertEqual(self.rt.local_models.first_ready_local_llm_id(), mid)

            # Health lists the custom LLM
            _, h = _get_json(base, "/health", token=tok)
            self.assertIn(mid, [m["id"] for m in h["models"]])

            # Save & clear HF token
            st, res_tok = _post_json(base, "/models/local/token", {"token": "hf_abc123456789xyz"}, token=tok)
            self.assertEqual(st, 200)
            self.assertTrue(res_tok["hf_token_configured"])
            st, res_clr = _post_json(base, "/models/local/token", {"clear": True}, token=tok)
            self.assertEqual(st, 200)
            self.assertFalse(res_clr["hf_token_configured"])

            # Remove custom LLM restores default role
            st, res_rm = _post_json(base, "/models/local/remove", {"model_id": mid}, token=tok)
            self.assertEqual(st, 200)
            self.assertTrue(res_rm["ok"])
            self.assertEqual(res_rm["roles"]["chat"], "gemma-4-e4b")
        finally:
            srv.shutdown()
            srv.server_close()

    def test_huggingface_search_inspect_download_and_cancel(self) -> None:
        file_blobs = {
            "/demo/Tiny-LLM/resolve/main/config.json": b'{"architectures": ["Qwen2ForCausalLM"]}',
            "/demo/Tiny-LLM/resolve/main/tokenizer.json": b'{"version": "1.0"}',
            "/demo/Tiny-LLM/resolve/main/model.safetensors": b"0123456789abcdef" * 4096,
        }
        slow_release = threading.Event()

        class FakeHFHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def do_GET(self):
                if self.path == "/slow/model.safetensors":
                    self.send_response(200)
                    self.send_header("Content-Length", str(65536))
                    self.end_headers()
                    for _ in range(8):
                        self.wfile.write(b"x" * 1024)
                        self.wfile.flush()
                        if slow_release.wait(0.05):
                            break
                    return
                body = file_blobs.get(self.path)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        hf_srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), FakeHFHandler)
        hf_port = hf_srv.server_address[1]
        hf_th = threading.Thread(target=hf_srv.serve_forever, daemon=True)
        hf_th.start()

        real_urlopen = sys.modules["urllib.request"].urlopen

        class FakeOpener:
            def open(self, req, timeout=15.0):
                return patched_urlopen(req, timeout=timeout)

        def patched_urlopen(req, timeout=15.0):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if url.startswith("https://huggingface.co/api/models?"):
                payload = json.dumps(
                    [
                        {
                            "id": "demo/Tiny-LLM",
                            "downloads": 5000,
                            "likes": 99,
                            "gated": False,
                            "pipeline_tag": "text-generation",
                        }
                    ]
                ).encode("utf-8")
                resp = io.BytesIO(payload)
                resp.status = 200
                resp.__enter__ = lambda s=resp: s
                resp.__exit__ = lambda *a: None
                return resp
            if url.startswith("https://huggingface.co/api/models/demo/Tiny-LLM"):
                payload = json.dumps(
                    {
                        "id": "demo/Tiny-LLM",
                        "gated": False,
                        "pipeline_tag": "text-generation",
                        "siblings": [
                            {"rfilename": "config.json", "size": len(file_blobs["/demo/Tiny-LLM/resolve/main/config.json"])},
                            {"rfilename": "tokenizer.json", "size": len(file_blobs["/demo/Tiny-LLM/resolve/main/tokenizer.json"])},
                            {"rfilename": "model.safetensors", "size": len(file_blobs["/demo/Tiny-LLM/resolve/main/model.safetensors"])},
                        ],
                    }
                ).encode("utf-8")
                resp = io.BytesIO(payload)
                resp.status = 200
                resp.__enter__ = lambda s=resp: s
                resp.__exit__ = lambda *a: None
                return resp
            if url.startswith("https://huggingface.co/api/models/demo/Slow-LLM"):
                payload = json.dumps(
                    {
                        "id": "demo/Slow-LLM",
                        "gated": False,
                        "siblings": [
                            {"rfilename": "config.json", "size": 2},
                            {"rfilename": "model.safetensors", "size": 65536},
                        ],
                    }
                ).encode("utf-8")
                resp = io.BytesIO(payload)
                resp.status = 200
                resp.__enter__ = lambda s=resp: s
                resp.__exit__ = lambda *a: None
                return resp
            if url.startswith("https://huggingface.co/demo/Tiny-LLM/resolve/main/"):
                local_url = url.replace("https://huggingface.co", f"http://127.0.0.1:{hf_port}")
                return real_urlopen(local_url, timeout=timeout)
            if url.startswith("https://huggingface.co/demo/Slow-LLM/resolve/main/"):
                if url.endswith("config.json"):
                    resp = io.BytesIO(b"{}")
                    resp.status = 200
                    resp.__enter__ = lambda s=resp: s
                    resp.__exit__ = lambda *a: None
                    return resp
                return real_urlopen(f"http://127.0.0.1:{hf_port}/slow/model.safetensors", timeout=timeout)
            return real_urlopen(req, timeout=timeout)

        try:
            with mock.patch("satz_local_models.urllib.request.urlopen", side_effect=patched_urlopen), mock.patch(
                "satz_local_models.urllib.request.build_opener", return_value=FakeOpener()
            ):
                s_res = self.rt.local_models.search_hf_models("Tiny-LLM")
                self.assertTrue(s_res["ok"])
                self.assertEqual(s_res["results"][0]["repo_id"], "demo/Tiny-LLM")

                dl_res = self.rt.local_models.start_hf_download(repo_id="demo/Tiny-LLM", use_as_chat=True)
                self.assertTrue(dl_res["ok"])
                dl_id = dl_res["download"]["download_id"]
                deadline = time.time() + 10.0
                final_job = None
                while time.time() < deadline:
                    jobs = {j["download_id"]: j for j in self.rt.local_models.list_hf_downloads()}
                    final_job = jobs.get(dl_id)
                    if final_job and final_job["state"] in ("completed", "error", "cancelled"):
                        break
                    time.sleep(0.05)
                self.assertIsNotNone(final_job)
                self.assertEqual(final_job["state"], "completed", f"Unexpected download state: {final_job}")
                self.assertEqual(final_job["pct"], 100.0)
                self.assertEqual(final_job["model_id"], "local:demo/Tiny-LLM")
                self.assertEqual(
                    self.rt.get_model_management_config()["roles"]["chat"],
                    "local:demo/Tiny-LLM",
                )

                # Test cancelling an in-flight download
                slow_dl = self.rt.local_models.start_hf_download(repo_id="demo/Slow-LLM", use_as_chat=False)
                self.assertTrue(slow_dl["ok"])
                slow_id = slow_dl["download"]["download_id"]
                time.sleep(0.08)
                c_res = self.rt.local_models.cancel_hf_download(slow_id)
                self.assertTrue(c_res["ok"])
                slow_release.set()
                time.sleep(0.15)
                jobs2 = {j["download_id"]: j for j in self.rt.local_models.list_hf_downloads()}
                self.assertEqual(jobs2[slow_id]["state"], "cancelled")
        finally:
            slow_release.set()
            hf_srv.shutdown()
            hf_srv.server_close()

    def test_run_answer_standalone_without_sgs_root(self) -> None:
        self.assertFalse(self.rt.sgs_root.exists())
        fake_turn = mock.MagicMock()
        fake_turn.question = "What is Satz?"
        fake_turn.result = {
            "answer_text": "Satz is a local-first browser.",
            "value": "local-first browser",
            "tier": "high",
            "explain": {"band_label": "high", "confidence10": 8.7, "sources": []},
            "depth": {"sources": []},
        }
        fake_session = mock.MagicMock()
        fake_session.ask.return_value = fake_turn
        with mock.patch.object(self.rt, "ensure_answerer", return_value=mock.MagicMock()), \
             mock.patch.object(self.rt, "_get_or_create_answer_session", return_value=fake_session):
            res = self.rt.run_answer("What is Satz?", session_id="onboard-demo")
        self.assertEqual(res["answer"], "Satz is a local-first browser.")
        self.assertEqual(res["confidence10"], 8.7)


if __name__ == "__main__":
    unittest.main()
