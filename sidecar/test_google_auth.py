#!/usr/bin/env python3
"""
Unit & Integration Tests for Google OAuth 2.0 (Browser Tab Loopback + PKCE + Encrypted Vault + Gmail XOAUTH2).
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SIDECAR_DIR = Path(__file__).resolve().parent
SGS_ROOT = SIDECAR_DIR.parent.parent / "sgs"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))
if str(SGS_ROOT) not in sys.path:
    sys.path.insert(0, str(SGS_ROOT))

from satz_google_auth import parse_google_client_secret_json
from satz_models import SatzSidecarRuntime


SAMPLE_CLIENT_JSON = json.dumps(
    {
        "installed": {
            "client_id": "1234567890-abcdefg.apps.googleusercontent.com",
            "project_id": "satz-demo",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_secret": "GOCSPX-super-secret-value-999",
            "redirect_uris": ["http://localhost"],
        }
    }
)


class _FakeOAuthIMAP:
    def __init__(self, reject_first_token: str = ""):
        self.authed_mechs: list[tuple[str, bytes]] = []
        self.reject_first_token = reject_first_token
        self.logged_out = False

    def authenticate(self, mechanism: str, authobject):
        raw_bytes = authobject(b"")
        self.authed_mechs.append((mechanism, raw_bytes))
        decoded = raw_bytes.decode("utf-8", errors="replace")
        if self.reject_first_token and f"Bearer {self.reject_first_token}" in decoded:
            raise RuntimeError("Invalid credentials (XOAUTH2 expired)")
        return ("OK", [b"Success"])

    def select(self, folder: str, readonly: bool = True):
        return ("OK", [b"1"])

    def list(self):
        return ("OK", [b'(\\HasNoChildren) "/" "INBOX"'])

    def response(self, code: str):
        return (code, [b"1"])

    def uid(self, cmd: str, *args):
        if cmd == "SEARCH":
            return ("OK", [b""])
        return ("OK", [])

    def logout(self):
        self.logged_out = True


class _FakeOAuthSMTP:
    def __init__(self):
        self.authed: list[tuple[str, str]] = []
        self.sent: list[tuple[str, list[str]]] = []

    def auth(self, mechanism: str, authobject, *, initial_response_ok: bool = True):
        payload = authobject()
        self.authed.append((mechanism, payload))
        return (235, b"2.7.0 Accepted")

    def send_message(self, msg, from_addr: str = "", to_addrs=None):
        self.sent.append((from_addr, list(to_addrs or [])))

    def quit(self):
        pass


class TestGoogleOAuthAndXOAuth2(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="satz_test_goauth_"))
        store_path = self.temp_dir / "planck_store.sqlite"
        self.rt = SatzSidecarRuntime(sgs_root=SGS_ROOT, store_path=store_path)
        self.rt.mail.pipeline.stop_worker()
        self.rt.passwords.create_profile("OAuth User", "123456")
        self.rt._refresh_active_profile_brain()

    def tearDown(self) -> None:
        try:
            self.rt.close()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_client_secret_json_parse_loopback_pkce_refresh_and_xoauth2(self) -> None:
        cid, csec, _ = parse_google_client_secret_json(SAMPLE_CLIENT_JSON)
        self.assertEqual(cid, "1234567890-abcdefg.apps.googleusercontent.com")
        self.assertEqual(csec, "GOCSPX-super-secret-value-999")

        token_requests: list[dict[str, str]] = []
        refresh_counter = {"n": 0}

        def fake_token_req(url: str, form: dict[str, str]):
            token_requests.append(dict(form))
            if form.get("grant_type") == "authorization_code":
                return {
                    "access_token": "ya29.initial-token-1",
                    "refresh_token": "1//refresh-token-xyz",
                    "expires_in": 3600,
                    "scope": "openid email profile https://mail.google.com/",
                    "token_type": "Bearer",
                }
            if form.get("grant_type") == "refresh_token":
                refresh_counter["n"] += 1
                return {
                    "access_token": f"ya29.refreshed-token-{refresh_counter['n']}",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                }
            raise AssertionError(f"Unexpected grant_type: {form}")

        def fake_userinfo(tok: str):
            return {"email": "nikita@gmail.com", "name": "Nikita G"}

        self.rt.google_auth._token_requester = fake_token_req
        self.rt.google_auth._userinfo_requester = fake_userinfo

        # Start browser-tab login flow from pasted client_secret JSON
        start = self.rt.google_auth.start_login(
            client_secret_json=SAMPLE_CLIENT_JSON,
            connect_gmail=True,
        )
        self.assertTrue(start["ok"])
        self.assertIn("accounts.google.com/o/oauth2/v2/auth", start["auth_url"])
        parsed_auth = urllib.parse.urlsplit(start["auth_url"])
        qs = dict(urllib.parse.parse_qsl(parsed_auth.query))
        self.assertEqual(qs["code_challenge_method"], "S256")
        self.assertEqual(qs["access_type"], "offline")
        redirect_uri = qs["redirect_uri"]
        self.assertTrue(redirect_uri.startswith("http://127.0.0.1:"))

        # 1. Wrong CSRF state gets rejected cleanly over loopback callback
        bad_cb = f"{redirect_uri}?code=auth-code-123&state=wrong-state"
        try:
            urllib.request.urlopen(bad_cb, timeout=5.0)
            self.fail("Expected HTTP 400 for bad OAuth state")
        except urllib.error.HTTPError as he:
            self.assertEqual(he.code, 400)

        # Restart a fresh loopback session and complete callback as browser tab would
        start2 = self.rt.google_auth.start_login(connect_gmail=True)
        qs2 = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(start2["auth_url"]).query))
        good_cb = f"{qs2['redirect_uri']}?{urllib.parse.urlencode({'code': 'auth-code-456', 'state': qs2['state']})}"
        with urllib.request.urlopen(good_cb, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            html_body = resp.read().decode("utf-8")
            self.assertIn("Signed in as nikita@gmail.com", html_body)

        # Verify PKCE challenge matches stored code_verifier and secrets stay masked in status
        self.assertEqual(len(token_requests), 1)
        expected_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(token_requests[0]["code_verifier"].encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        self.assertEqual(qs2["code_challenge"], expected_challenge)

        st = self.rt.google_auth.get_status(session_id=start2["session_id"])
        self.assertTrue(st["signed_in"])
        self.assertEqual(st["email"], "nikita@gmail.com")
        self.assertNotIn("GOCSPX", json.dumps(st))
        self.assertNotIn("ya29.", json.dumps(st))
        self.assertEqual(st["session"]["status"], "authorized")
        self.assertTrue(st["session"]["gmail_connected"])

        # Gmail account was automatically linked with auth_type='oauth2'
        accts = self.rt.mail.list_accounts()["accounts"]
        self.assertEqual(len(accts), 1)
        self.assertEqual(accts[0]["email"], "nikita@gmail.com")
        self.assertEqual(accts[0]["auth_type"], "oauth2")
        aid = accts[0]["id"]

        # Verify XOAUTH2 across test_account, IMAP sync (including expired-token auto-refresh), and SMTP send
        fake_imaps: list[_FakeOAuthIMAP] = []
        fake_smtps: list[_FakeOAuthSMTP] = []

        def fake_imap_factory(host, port, sec):
            im = _FakeOAuthIMAP(reject_first_token="ya29.initial-token-1")
            fake_imaps.append(im)
            return im

        def fake_smtp_factory(host, port, sec):
            sm = _FakeOAuthSMTP()
            fake_smtps.append(sm)
            return sm

        self.rt.mail.imap_factory = fake_imap_factory
        self.rt.mail.smtp_factory = fake_smtp_factory

        test_res = self.rt.mail.test_account({"account_id": aid})
        self.assertTrue(test_res["ok"])
        self.assertEqual(test_res["auth_type"], "oauth2")
        self.assertGreaterEqual(refresh_counter["n"], 1)
        self.assertEqual(fake_imaps[-1].authed_mechs[-1][0], "XOAUTH2")
        self.assertIn(b"user=nikita@gmail.com\x01auth=Bearer ya29.refreshed-token-1\x01\x01", fake_imaps[-1].authed_mechs[-1][1])
        self.assertEqual(fake_smtps[-1].authed[0][0], "XOAUTH2")
        self.assertIn("user=nikita@gmail.com\x01auth=Bearer ya29.refreshed-token-1\x01\x01", fake_smtps[-1].authed[0][1])

        # Also test manual forced token expiry triggers automatic refresh on get_valid_access_token
        self.rt.passwords.update_vault_entries({"GOOGLE_OAUTH_EXPIRY": str(time.time() - 120.0)})
        tok2 = self.rt.google_auth.get_valid_access_token()
        self.assertEqual(tok2, "ya29.refreshed-token-2")

        # Prepare + immediate send via XOAUTH2 SMTP
        prep = self.rt.mail.prepare_send(
            {
                "account_id": aid,
                "to": ["friend@example.com"],
                "subject": "Hello OAuth",
                "body": "Sent using Google XOAUTH2.",
            }
        )
        send_res = self.rt.mail.confirm_and_queue_send(prep["outbox_id"], prep["confirm_token"], immediate_for_test=True)
        self.assertTrue(send_res["ok"])
        self.assertEqual(fake_smtps[-1].authed[0][0], "XOAUTH2")

        # Profile isolation: creating or locking profile clears Google OAuth visibility
        self.rt.passwords.create_profile("Second User", "654321")
        self.rt._refresh_active_profile_brain()
        st_other = self.rt.google_auth.get_status()
        self.assertFalse(st_other["signed_in"])
        self.assertFalse(st_other["configured"])


if __name__ == "__main__":
    unittest.main()
