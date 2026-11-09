from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path

SIDECAR_DIR = Path(__file__).resolve().parent
REPO_ROOT = SIDECAR_DIR.parent
SGS_ROOT = REPO_ROOT.parent / "sgs"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))
if str(SGS_ROOT) not in sys.path:
    sys.path.insert(0, str(SGS_ROOT))

from satz_mail_pipeline import SatzMailPipeline
from satz_models import SatzSidecarRuntime


class TestM19MailColdStart(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="satz_test_m19_"))
        self.store_path = self.tmp / "planck_store.sqlite"
        self.rt = SatzSidecarRuntime(sgs_root=SGS_ROOT, store_path=self.store_path)
        self.rt.mail.pipeline.stop_worker()
        self.rt.passwords.create_profile("demo", "123456")

        with self.rt.mail.db_lock:
            conn = self.rt.mail._ensure_connection()
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

    def tearDown(self):
        try:
            self.rt.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

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

    def test_m19_fixture_12_cold_start_promos_zalando_code_orders_and_new_badge(self):
        fixture_path = REPO_ROOT / "docs" / "smoke" / "mail_fixture" / "fixture_12.json"
        items = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(len(items), 12)

        # Verify none of the 12 fixture messages rely on List-Unsubscribe
        for it in items:
            headers_low = {k.lower(): v for k, v in (it.get("headers") or {}).items()}
            self.assertNotIn("list-unsubscribe", headers_low)

        stored_ids: dict[str, str] = {}
        for idx, it in enumerate(items, start=1):
            raw_b = self._fixture_entry_to_raw_bytes(it)
            mid = self.rt.mail._store_parsed_raw_email(
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
            assert mid is not None
            stored_ids[it["id"]] = mid
            self.rt.mail.pipeline.process_single_message(mid)

        # 1. Check lane counts: 3 inbox, 4 pings, 2 orders, 3 promos (0 personal emails misfiled)
        inbox_lane = self.rt.mail.get_lane("inbox")
        pings_lane = self.rt.mail.get_lane("pings")
        orders_lane = self.rt.mail.get_lane("orders")
        promos_lane = self.rt.mail.get_lane("promos")

        self.assertEqual(inbox_lane["counts"]["inbox_unread"], 3)
        self.assertEqual(inbox_lane["counts"]["pings"], 4)
        self.assertEqual(inbox_lane["counts"]["orders"], 2)
        self.assertEqual(inbox_lane["counts"]["promos"], 3)
        self.assertEqual(len(inbox_lane["rows"]), 3)
        self.assertEqual(len(pings_lane["rows"]), 4)
        self.assertEqual(len(orders_lane["rows"]), 2)
        self.assertEqual(len(promos_lane["rows"]), 3)

        # 2. Check cold-start onboarding header status (`classifier: learning · 12 / 50 labels`)
        self.assertEqual(
            promos_lane["classifier"]["status_text"],
            "classifier: learning · 12 / 50 labels",
        )
        self.assertGreaterEqual(len(promos_lane["onboarding_candidates"]), 10)

        # 3. Check `ZALANDO25AUTUMN` with expiry on the Zalando promo card and `[codes (1)]` on zalando.de
        zalando_promo_card = next(
            (r for r in promos_lane["rows"] if "zalando" in str(r.get("company", "")).lower()),
            None,
        )
        self.assertIsNotNone(zalando_promo_card)
        assert zalando_promo_card is not None
        self.assertEqual(len(zalando_promo_card["active_codes"]), 1)
        self.assertEqual(zalando_promo_card["active_codes"][0]["code"], "ZALANDO25AUTUMN")
        self.assertEqual(zalando_promo_card["active_codes"][0]["expiry"], "2026-12-31")

        zalando_codes = self.rt.mail.get_active_codes_for_domain("www.zalando.de")
        self.assertEqual(len(zalando_codes), 1)
        self.assertEqual(zalando_codes[0]["code"], "ZALANDO25AUTUMN")
        self.assertEqual(zalando_codes[0]["expiry"], "2026-12-31")

        # 4. Check Order card has `status: shipped`, `tracking_number`, `tracking_url`, and `total`
        zalando_order_card = next(
            (r for r in orders_lane["rows"] if r.get("order_number") == "104099887712"),
            None,
        )
        self.assertIsNotNone(zalando_order_card)
        assert zalando_order_card is not None
        self.assertEqual(zalando_order_card["status"], "shipped")
        self.assertEqual(zalando_order_card["tracking_number"], "00340434161094012345")
        self.assertIn("dhl.de", zalando_order_card["tracking_url"])
        self.assertEqual(zalando_order_card["total"], "EUR 129.95")

        # Arrival of delivery update advances order card status from `shipped` -> `delivered`
        raw_delivered = (
            b"Message-ID: <zalando-delivered-099@dhl.de>\r\n"
            b"From: DHL Paket <noreply@dhl.de>\r\n"
            b"To: nikita@satz.local\r\n"
            b"Subject: Delivered: Your Zalando order #104099887712\r\n"
            b"Date: Wed, 04 Nov 2026 14:00:00 +0000\r\n\r\n"
            b"Your Zalando order #104099887712 (tracking number: 00340434161094012345) was delivered today.\r\n"
        )
        mid_deliv = self.rt.mail._store_parsed_raw_email(
            "acct-demo", "INBOX", "inbox", 2001, "", raw_delivered, 0, 0, 0
        )
        assert mid_deliv is not None
        self.rt.mail.pipeline.process_single_message(mid_deliv)

        orders_lane_after = self.rt.mail.get_lane("orders")
        zalando_order_after = next(
            (r for r in orders_lane_after["rows"] if r.get("order_number") == "104099887712"),
            None,
        )
        assert zalando_order_after is not None
        self.assertEqual(zalando_order_after["status"], "delivered")
        self.assertEqual(zalando_order_after["tracking_number"], "00340434161094012345")
        self.assertEqual(zalando_order_after["total"], "EUR 129.95")

        # 5. Send gate `[new]` badge when replying to a sender who has never received mail from this account
        jama_mid = stored_ids["fix-07-jama-roadmap"]
        prep_reply = self.rt.mail.prepare_send(
            {
                "account_id": "acct-demo",
                "to": ["jama.musse@hellofresh.com"],
                "subject": "Re: Q4 OTP capability review & Thursday product sync",
                "body": "Hi Jama,\n\nMetrics are finalized.\n\nBest,\nNikita",
                "reply_to_message_id": jama_mid,
            }
        )
        self.assertTrue(prep_reply["ok"])
        self.assertIn("jama.musse@hellofresh.com", prep_reply["new_recipients"])
        self.assertIn("jama.musse@hellofresh.com [new]", prep_reply["confirm_line"])

    def test_m19_gemma_logit_confidence_and_relabel_reruns_extraction_and_brain(self):
        # 1. Gemma logit confidence: high confidence (>= 0.75) vs low confidence (< 0.75 -> fallback to `email`)
        lbl_high, conf_high, raw_high = SatzMailPipeline.compute_gemma_label_from_logits(
            {"email": 0.1, "ping": 0.2, "information": 0.1, "promotion": 3.5}
        )
        self.assertEqual(lbl_high, "promotion")
        self.assertEqual(raw_high, "promotion")
        self.assertGreaterEqual(conf_high, 0.75)

        lbl_low, conf_low, raw_low = SatzMailPipeline.compute_gemma_label_from_logits(
            {"email": 1.0, "ping": 1.1, "information": 1.2, "promotion": 1.3}
        )
        self.assertEqual(raw_low, "promotion")
        self.assertLess(conf_low, 0.75)
        self.assertEqual(lbl_low, "email", "Below 0.75 confidence must fall back to 'email'")

        # 2. Relabel re-runs extraction and Brain linking
        # Force initial classification to `email` via gemma_label_fn returning low-confidence logits
        self.rt.mail.pipeline.gemma_label_fn = lambda *_args: {
            "email": 1.0,
            "ping": 1.0,
            "information": 1.0,
            "promotion": 1.2,
        }
        raw_otto = (
            b"Message-ID: <otto-relabel-1@otto.de>\r\n"
            b"From: Otto <kontakt@otto.de>\r\n"
            b"To: nikita@satz.local\r\n"
            b"Subject: Winter voucher inside\r\n"
            b"Date: Wed, 04 Nov 2026 15:00:00 +0000\r\n\r\n"
            b"Save 30% off winter coats at otto.de with code: OTTOWINTER30 valid until 2026-12-20.\r\n"
        )
        mid_otto = self.rt.mail._store_parsed_raw_email(
            "acct-demo", "INBOX", "inbox", 3001, "", raw_otto, 0, 0, 0
        )
        assert mid_otto is not None
        initial_res = self.rt.mail.pipeline.process_single_message(mid_otto)
        assert initial_res is not None
        self.assertEqual(initial_res["label"], "email")
        self.assertEqual(initial_res["extracts"], {})
        self.assertEqual(self.rt.mail.get_active_codes_for_domain("otto.de"), [])

        # Now relabel to `promotion` -> extraction and Brain linking must re-run automatically
        relabel_res = self.rt.mail.pipeline.record_user_correction(mid_otto, "promotion")
        self.assertTrue(relabel_res["ok"])
        self.assertEqual(relabel_res["old_label"], "email")
        self.assertEqual(relabel_res["new_label"], "promotion")
        self.assertEqual(relabel_res["extracts"].get("voucher_code"), "OTTOWINTER30")
        self.assertEqual(relabel_res["extracts"].get("expiry"), "2026-12-20")

        otto_codes = self.rt.mail.get_active_codes_for_domain("otto.de")
        self.assertEqual(len(otto_codes), 1)
        self.assertEqual(otto_codes[0]["code"], "OTTOWINTER30")
        self.assertIn("otto-promo-ottowinter30", self.rt.brain.get_cached_brain_md())


if __name__ == "__main__":
    unittest.main()
