import http.server
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

SIDECAR_DIR = Path(__file__).resolve().parent
SGS_ROOT = SIDECAR_DIR.parent.parent / "sgs"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))
if str(SGS_ROOT) not in sys.path:
    sys.path.insert(0, str(SGS_ROOT))

from satz_models import SatzSidecarRuntime, make_sidecar_server  # noqa: E402


class TestMilestoneM22(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.base = Path(self.tmp_dir.name)
        self.store_path = self.base / "planck_store.sqlite"
        self.runtime = SatzSidecarRuntime(
            sgs_root=SGS_ROOT,
            store_path=self.store_path,
            bookmark_interval_minutes=30.0,
        )
        self.runtime.passwords.create_profile("M22User", "123456")
        self.runtime._refresh_active_profile_brain()
        self.server = make_sidecar_server(
            self.runtime,
            host="127.0.0.1",
            port=0,
            auth_token="test-m22-token",
        )
        self.port = self.server.server_address[1]
        self.srv_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.srv_thread.start()

    def tearDown(self):
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            pass
        self.runtime.close()
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def _req(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        url = f"http://127.0.0.1:{self.port}{path}"
        headers = {
            "Host": f"127.0.0.1:{self.port}",
            "X-Satz-Token": "test-m22-token",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as he:
            return he.code, json.loads(he.read().decode("utf-8"))

    def test_01_task_card_stop_and_single_use_send_gate_token(self):
        # 1. Create a task card
        code, res = self._req(
            "POST",
            "/task/create",
            {"conversation_id": "conv-task-1", "goal": "check order status", "agent": "task"},
        )
        self.assertEqual(code, 200)
        task = res["task"]
        task_id = task["id"]
        stop_token = task["stop_token"]
        self.assertEqual(task["goal"], "check order status")
        self.assertEqual(task["status"], "running")
        self.assertTrue(len(stop_token) >= 16)

        # 2. Append a regular log step and a commit/send-gate step
        code, res = self._req(
            "POST",
            "/task/step",
            {"task_id": task_id, "text": "reading order page [1]", "kind": "log"},
        )
        self.assertEqual(code, 200)

        code, res = self._req(
            "POST",
            "/task/step",
            {
                "task_id": task_id,
                "text": "submit return form",
                "kind": "send_gate",
                "action_summary": "submit return form for order #10492",
            },
        )
        self.assertEqual(code, 200)
        task_waiting = res["task"]
        self.assertEqual(task_waiting["status"], "waiting_confirm")
        gate_step = task_waiting["steps"][-1]
        self.assertEqual(gate_step["kind"], "send_gate")
        self.assertEqual(gate_step["status"], "waiting_confirm")
        confirm_token = gate_step["confirm_token"]
        self.assertTrue(len(confirm_token) >= 16)

        # 3. Wrong confirm_token is rejected
        code, bad_res = self._req(
            "POST",
            "/task/confirm",
            {"task_id": task_id, "step_id": gate_step["id"], "confirm_token": "wrong-token"},
        )
        self.assertEqual(code, 400)
        self.assertFalse(bad_res["ok"])

        # 4. Valid single-use confirm_token succeeds once, then is rejected on replay
        code, ok_res = self._req(
            "POST",
            "/task/confirm",
            {"task_id": task_id, "step_id": gate_step["id"], "confirm_token": confirm_token},
        )
        self.assertEqual(code, 200)
        self.assertTrue(ok_res["ok"])
        self.assertEqual(ok_res["task"]["status"], "running")
        self.assertEqual(ok_res["task"]["steps"][-1]["status"], "confirmed")

        code, replay_res = self._req(
            "POST",
            "/task/confirm",
            {"task_id": task_id, "step_id": gate_step["id"], "confirm_token": confirm_token},
        )
        self.assertEqual(code, 400)
        self.assertFalse(replay_res["ok"])
        self.assertIn("already used", replay_res["error"])

        # 5. Stop task with stop_token
        code, bad_stop = self._req(
            "POST",
            "/task/stop",
            {"task_id": task_id, "stop_token": "bad-stop-token"},
        )
        self.assertEqual(code, 400)

        code, ok_stop = self._req(
            "POST",
            "/task/stop",
            {"task_id": task_id, "stop_token": stop_token},
        )
        self.assertEqual(code, 200)
        self.assertEqual(ok_stop["task"]["status"], "stopped")

    def test_02_comparer_three_product_pages_zero_uncited_cells(self):
        conv_id = "conv-compare-3"
        products = [
            {
                "id": "src-boot-1",
                "url": "https://alpine-gear.example/boots/ridge-pro",
                "title": "Ridge Pro GTX Boot - Alpine Gear",
                "visible_text": (
                    "Ridge Pro GTX Boot\n"
                    "Price: EUR 189.00\n"
                    "Weight: 620 g per boot\n"
                    "Material: Full-grain leather with Gore-Tex membrane\n"
                    "Sole: Vibram Megagrip\n"
                    "In stock - free shipping in 2-3 days."
                ),
            },
            {
                "id": "src-boot-2",
                "url": "https://nordic-trail.example/footwear/fjell-lite",
                "title": "Fjell Lite Mid - Nordic Trail",
                "visible_text": (
                    "Fjell Lite Mid Hiking Boot\n"
                    "Price: EUR 149.00\n"
                    "Weight: 490 g per boot\n"
                    "Material: Ripstop nylon and waterproof membrane\n"
                    "Warranty: 2 years\n"
                    "Available - ships in 24 hours."
                ),
            },
            {
                "id": "src-boot-3",
                "url": "https://summit-craft.example/shop/k2-trek",
                "title": "K2 Trek Leather - Summit Craft",
                "visible_text": (
                    "K2 Trek Leather Boot\n"
                    "Price: EUR 219.00\n"
                    "Weight: 710 g per boot\n"
                    "Material: Waxed nubuck leather, crampon-compatible sole\n"
                    "In stock with 30-day returns."
                ),
            },
        ]

        for p in products:
            self.runtime.ingest_page(
                conversation_id=conv_id,
                source_id=p["id"],
                url=p["url"],
                title=p["title"],
                html=None,
                visible_text=p["visible_text"],
            )

        code, res = self._req(
            "POST",
            "/agent/compare",
            {
                "conversation_id": conv_id,
                "sources": [{"id": p["id"], "url": p["url"], "title": p["title"]} for p in products],
                "goal": "compare these",
            },
        )
        self.assertEqual(code, 200)
        self.assertTrue(res["ok"])
        self.assertEqual(res["uncited_cells"], 0)
        self.assertEqual(len(res["columns"]), 3)

        row_map = {r["attribute"]: r["cells"] for r in res["rows"]}
        self.assertIn("Price", row_map)
        self.assertIn("Key specs", row_map)
        self.assertIn("Source", row_map)

        # Verify prices and citations [1], [2], [3]
        self.assertIn("EUR 189.00 [1]", row_map["Price"][0])
        self.assertIn("EUR 149.00 [2]", row_map["Price"][1])
        self.assertIn("EUR 219.00 [3]", row_map["Price"][2])

        for r in res["rows"]:
            for col_idx, cell in enumerate(r["cells"], 1):
                self.assertIn(f"[{col_idx}]", cell, f"Cell '{cell}' missing [{col_idx}] citation")

        # Verify task card completed with table_md
        self.assertEqual(res["task"]["status"], "completed")
        self.assertIn("| **Price** |", res["table_md"])
        self.assertIn("| **Key specs** |", res["table_md"])
        self.assertIn("| **Source** |", res["table_md"])

    def test_03_watcher_local_price_change_fires_digest_and_badge(self):
        state_holder = {"price": "EUR 129.00"}

        class PriceHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass

            def do_GET(self):
                body = (
                    "<html><head><title>Trail Jacket - Local Shop</title></head>"
                    f"<body><h1>Trail Jacket</h1><p>Current price: {state_holder['price']}</p></body></html>"
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        fixture_srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), PriceHandler)
        fixture_port = fixture_srv.server_address[1]
        fixture_thread = threading.Thread(target=fixture_srv.serve_forever, daemon=True)
        fixture_thread.start()

        try:
            test_url = f"http://127.0.0.1:{fixture_port}/product/trail-jacket"
            conv_id = "conv-watch-price"

            # 1. Add watch on the local page
            code, add_res = self._req(
                "POST",
                "/watch/add",
                {
                    "conversation_id": conv_id,
                    "query_or_url": test_url,
                    "cadence_seconds": 60,
                    "condition": "price_change",
                    "title": "Trail Jacket",
                },
            )
            self.assertEqual(code, 200)
            self.assertTrue(add_res["ok"])
            self.assertEqual(add_res["watch"]["last_value"], "EUR 129.00")
            self.assertFalse(add_res["watch"]["badge_unread"])

            # 2. Change the price on the local server and run one watch pass
            state_holder["price"] = "EUR 99.00"
            code, check_res = self._req("POST", "/watch/check", {"force": True})
            self.assertEqual(code, 200)
            self.assertEqual(check_res["triggered"], 1)
            self.assertIn(conv_id, check_res["watch_badges"])

            # 3. Verify `For you` (/digest) contains one watch_triggered item for the price change
            code, digest_res = self._req("GET", "/digest")
            self.assertEqual(code, 200)
            watch_items = [
                it for it in digest_res["items"] if it.get("kind") == "watch_triggered"
            ]
            self.assertEqual(len(watch_items), 1)
            self.assertIn("EUR 129.00 -> EUR 99.00", watch_items[0]["title"])
            self.assertEqual(watch_items[0]["url"], test_url)

            # 4. Acknowledge the conversation watch badge
            code, ack_res = self._req("POST", "/watch/ack", {"conversation_id": conv_id})
            self.assertEqual(code, 200)
            self.assertNotIn(conv_id, ack_res["watch_badges"])
        finally:
            fixture_srv.shutdown()
            fixture_srv.server_close()


if __name__ == "__main__":
    unittest.main()
