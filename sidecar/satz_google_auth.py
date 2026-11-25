#!/usr/bin/env python3
"""
Google OAuth 2.0 Authentication Manager for Satz Browser.

Supports standard Google OAuth 2.0 Authorization Code + PKCE flow using a
user-supplied Client ID + Client Secret (or pasted/uploaded `client_secret_*.json`
from Google Cloud Console) and a real live Satz Browser tab for user sign-in
via an ephemeral local loopback callback (`http://127.0.0.1:<port>/oauth/google/callback`).

All credentials (`GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`,
`GOOGLE_OAUTH_ACCESS_TOKEN`, `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_OAUTH_EXPIRY`,
`GOOGLE_OAUTH_SCOPES`, `GOOGLE_OAUTH_EMAIL`, `GOOGLE_OAUTH_NAME`) are stored
exclusively inside the active profile's encrypted `vault.enc`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html as html_lib
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

GOOGLE_DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

DEFAULT_GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://mail.google.com/",
]

VAULT_PREFIX = "GOOGLE_OAUTH"


def _mask_client_id(cid: str) -> str:
    s = (cid or "").strip()
    if len(s) <= 14:
        return "*" * len(s) if s else ""
    return f"{s[:8]}...{s[-8:]}"


def parse_google_client_secret_json(raw_json: str) -> tuple[str, str, list[str]]:
    """
    Parses a Google Cloud Console downloaded `client_secret_*.json` (`installed` or `web`)
    and returns `(client_id, client_secret, redirect_uris)`.
    """
    try:
        parsed = json.loads((raw_json or "").strip())
    except Exception as exc:
        raise ValueError(f"Invalid Google client_secret JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("client_secret JSON must be an object.")

    block = parsed.get("installed") or parsed.get("web") or parsed
    if not isinstance(block, dict):
        raise ValueError("Missing 'installed' or 'web' configuration object.")

    cid = str(block.get("client_id") or "").strip()
    csec = str(block.get("client_secret") or "").strip()
    redir = [str(u).strip() for u in (block.get("redirect_uris") or []) if str(u).strip()]
    if not cid or not csec:
        raise ValueError("JSON must include both 'client_id' and 'client_secret'.")
    return cid, csec, redir


def _render_callback_html(
    ok: bool,
    headline: str,
    detail: str,
    *,
    lang: str = "en",
    direction: str = "ltr",
    page_title: str = "Google Auth · Satz",
    badge_text: str | None = None,
    hint_text: str | None = None,
) -> bytes:
    accent = "#8b7cff" if ok else "#ef6b6b"
    pill_txt = badge_text or ("Connected" if ok else "Authorization Failed")
    hint = hint_text or "Tokens are saved inside your encrypted Satz profile vault. You can close this tab now (Ctrl+W / Cmd+W)."
    page = f"""<!DOCTYPE html>
<html lang="{html_lib.escape(lang)}" dir="{html_lib.escape(direction)}">
<head>
  <meta charset="utf-8" />
  <meta name="color-scheme" content="dark light" />
  <title>{html_lib.escape(page_title)}</title>
  <style>
    :root {{ color-scheme: dark light; }}
    body {{
      margin: 0; min-height: 100vh; display: grid; place-items: center;
      font-family: system-ui, -apple-system, 'Inter', sans-serif;
      background: #111216; color: #eceef4;
    }}
    .card {{
      max-width: 460px; padding: 28px 30px; border-radius: 14px;
      background: #191b22; border: 1px solid #2b2f3d;
      box-shadow: 0 18px 40px rgba(0, 0, 0, 0.35);
    }}
    .pill {{
      display: inline-block; padding: 3px 10px; border-radius: 999px;
      font-size: 12px; font-weight: 600; letter-spacing: 0.02em;
      background: rgba(139, 124, 255, 0.14); color: {accent};
      border: 1px solid rgba(139, 124, 255, 0.35);
    }}
    h1 {{ font-size: 20px; margin: 14px 0 8px; }}
    p {{ font-size: 14px; line-height: 1.5; color: #aeb4c4; margin: 0 0 14px; }}
    .hint {{ font-size: 12px; color: #7e8596; }}
  </style>
</head>
<body>
  <div class="card">
    <span class="pill">{html_lib.escape(pill_txt)}</span>
    <h1>{html_lib.escape(headline)}</h1>
    <p>{html_lib.escape(detail)}</p>
    <p class="hint">{html_lib.escape(hint)}</p>
  </div>
</body>
</html>"""
    return page.encode("utf-8")


class GoogleOAuthManager:
    """Manages profile-scoped Google OAuth 2.0 config, browser-tab login, and token refresh."""

    def __init__(
        self,
        runtime: Any,
        token_requester: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
        userinfo_requester: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self.runtime = runtime
        self.passwords = runtime.passwords
        self._lock = threading.RLock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._servers: dict[str, ThreadingHTTPServer] = {}
        self._token_requester = token_requester
        self._userinfo_requester = userinfo_requester

    def _require_unlocked(self) -> str:
        if not self.passwords.unlocked or not self.passwords.active_profile_id:
            raise PermissionError("Unlock a profile with its 6-digit PIN first.")
        return str(self.passwords.active_profile_id)

    def _http_post_form(self, url: str, form_data: dict[str, str]) -> dict[str, Any]:
        if self._token_requester is not None:
            return self._token_requester(url, form_data)
        encoded = urllib.parse.urlencode(form_data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as he:
            detail = ""
            try:
                detail = he.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                pass
            raise RuntimeError(f"Google OAuth endpoint returned HTTP {he.code}: {detail or he}") from he

    def _http_get_userinfo(self, access_token: str) -> dict[str, Any]:
        if self._userinfo_requester is not None:
            return self._userinfo_requester(access_token)
        req = urllib.request.Request(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception:
            return {}

    def save_client_config(
        self,
        *,
        client_id: str = "",
        client_secret: str = "",
        client_secret_json: str = "",
        scopes: list[str] | str | None = None,
        redirect_port: int | None = None,
    ) -> dict[str, Any]:
        self._require_unlocked()
        parsed_redir: list[str] = []
        cid = (client_id or "").strip()
        csec = (client_secret or "").strip()
        if client_secret_json and client_secret_json.strip():
            j_cid, j_csec, parsed_redir = parse_google_client_secret_json(client_secret_json)
            cid = cid or j_cid
            csec = csec or j_csec

        env_now = self.passwords.get_unlocked_credentials_map()
        if not cid:
            cid = env_now.get(f"{VAULT_PREFIX}_CLIENT_ID", "").strip()
        if not csec:
            csec = env_now.get(f"{VAULT_PREFIX}_CLIENT_SECRET", "").strip()

        if not cid or not csec:
            raise ValueError("Both Google Client ID and Client Secret (or a client_secret JSON) are required.")

        updates: dict[str, str] = {
            f"{VAULT_PREFIX}_CLIENT_ID": cid,
            f"{VAULT_PREFIX}_CLIENT_SECRET": csec,
        }
        if scopes is not None:
            if isinstance(scopes, str):
                sc_list = [s.strip() for s in scopes.replace(",", " ").split() if s.strip()]
            else:
                sc_list = [str(s).strip() for s in scopes if str(s).strip()]
            if sc_list:
                updates[f"{VAULT_PREFIX}_SCOPES"] = " ".join(dict.fromkeys(sc_list))

        if redirect_port is not None and int(redirect_port) > 0:
            updates[f"{VAULT_PREFIX}_REDIRECT_PORT"] = str(int(redirect_port))
        elif parsed_redir and not env_now.get(f"{VAULT_PREFIX}_REDIRECT_PORT"):
            for ruri in parsed_redir:
                try:
                    pu = urllib.parse.urlsplit(ruri)
                    if pu.hostname in ("127.0.0.1", "localhost") and pu.port:
                        updates[f"{VAULT_PREFIX}_REDIRECT_PORT"] = str(pu.port)
                        break
                except Exception:
                    pass

        self.passwords.update_vault_entries(updates)
        return self.get_status()

    def get_status(self, session_id: str = "") -> dict[str, Any]:
        unlocked = bool(self.passwords.unlocked and self.passwords.active_profile_id)
        if not unlocked:
            return {
                "ok": True,
                "unlocked": False,
                "configured": False,
                "signed_in": False,
                "drive_authorized": False,
                "has_client_id": False,
                "has_client_secret": False,
                "has_refresh_token": False,
                "masked_client_id": "",
                "email": "",
                "name": "",
                "scopes": list(DEFAULT_GOOGLE_SCOPES),
                "expires_at": 0.0,
                "redirect_port": 0,
                "session": None,
            }

        env_map = self.passwords.get_unlocked_credentials_map()
        cid = env_map.get(f"{VAULT_PREFIX}_CLIENT_ID", "").strip()
        csec = env_map.get(f"{VAULT_PREFIX}_CLIENT_SECRET", "").strip()
        access_tok = env_map.get(f"{VAULT_PREFIX}_ACCESS_TOKEN", "").strip()
        refresh_tok = env_map.get(f"{VAULT_PREFIX}_REFRESH_TOKEN", "").strip()
        email = env_map.get(f"{VAULT_PREFIX}_EMAIL", "").strip()
        name = env_map.get(f"{VAULT_PREFIX}_NAME", "").strip()
        scopes_str = env_map.get(f"{VAULT_PREFIX}_SCOPES", "").strip()
        scopes = [s for s in scopes_str.split() if s] if scopes_str else list(DEFAULT_GOOGLE_SCOPES)
        try:
            expires_at = float(env_map.get(f"{VAULT_PREFIX}_EXPIRY", "0") or 0.0)
        except ValueError:
            expires_at = 0.0
        try:
            redirect_port = int(env_map.get(f"{VAULT_PREFIX}_REDIRECT_PORT", "0") or 0)
        except ValueError:
            redirect_port = 0

        sess_out = None
        if session_id:
            with self._lock:
                s = self._sessions.get(session_id)
                if s and s.get("profile_id") == self.passwords.active_profile_id:
                    sess_out = {
                        "session_id": s["session_id"],
                        "status": s["status"],
                        "email": s.get("email") or "",
                        "error": s.get("error") or "",
                        "gmail_connected": bool(s.get("gmail_connected")),
                        "drive_connected": bool(s.get("drive_connected")),
                        "redirect_uri": s.get("redirect_uri") or "",
                    }

        drive_authorized = bool(
            (access_tok or refresh_tok)
            and email
            and any(
                sc in scopes
                for sc in (
                    GOOGLE_DRIVE_READONLY_SCOPE,
                    "https://www.googleapis.com/auth/drive",
                    "https://www.googleapis.com/auth/drive.metadata.readonly",
                )
            )
        )

        return {
            "ok": True,
            "unlocked": True,
            "configured": bool(cid and csec),
            "signed_in": bool((access_tok or refresh_tok) and email),
            "drive_authorized": drive_authorized,
            "has_client_id": bool(cid),
            "has_client_secret": bool(csec),
            "has_refresh_token": bool(refresh_tok),
            "masked_client_id": _mask_client_id(cid),
            "email": email,
            "name": name,
            "scopes": scopes,
            "expires_at": expires_at,
            "token_valid": bool(access_tok and expires_at > time.time() + 30.0),
            "redirect_port": redirect_port,
            "session": sess_out,
        }

    def start_login(
        self,
        *,
        client_id: str = "",
        client_secret: str = "",
        client_secret_json: str = "",
        scopes: list[str] | str | None = None,
        connect_gmail: bool = True,
        connect_drive: bool = False,
        login_hint: str = "",
        hd: str = "",
        redirect_port: int | None = None,
        redirect_host: str = "127.0.0.1",
        callback_path: str = "/oauth/google/callback",
    ) -> dict[str, Any]:
        profile_id = self._require_unlocked()
        if client_id or client_secret or client_secret_json or scopes is not None or redirect_port is not None:
            self.save_client_config(
                client_id=client_id,
                client_secret=client_secret,
                client_secret_json=client_secret_json,
                scopes=scopes,
                redirect_port=redirect_port,
            )

        env_map = self.passwords.get_unlocked_credentials_map()
        cid = env_map.get(f"{VAULT_PREFIX}_CLIENT_ID", "").strip()
        csec = env_map.get(f"{VAULT_PREFIX}_CLIENT_SECRET", "").strip()
        if not cid or not csec:
            raise ValueError("Configure your Google Client ID and Client Secret first.")

        scopes_str = env_map.get(f"{VAULT_PREFIX}_SCOPES", "").strip()
        if scopes_str:
            eff_scopes = [s for s in scopes_str.split() if s]
        elif connect_drive and not connect_gmail:
            eff_scopes = ["openid", "email", "profile", GOOGLE_DRIVE_READONLY_SCOPE]
        else:
            eff_scopes = list(DEFAULT_GOOGLE_SCOPES)
        if connect_gmail and "https://mail.google.com/" not in eff_scopes:
            eff_scopes.append("https://mail.google.com/")
        if connect_drive and GOOGLE_DRIVE_READONLY_SCOPE not in eff_scopes:
            eff_scopes.append(GOOGLE_DRIVE_READONLY_SCOPE)

        try:
            saved_port = int(env_map.get(f"{VAULT_PREFIX}_REDIRECT_PORT", "0") or 0)
        except ValueError:
            saved_port = 0
        bind_port = int(redirect_port if redirect_port is not None else saved_port or 0)
        host_norm = "localhost" if redirect_host == "localhost" else "127.0.0.1"
        path_norm = callback_path if callback_path.startswith("/") else f"/{callback_path}"

        code_verifier = secrets.token_urlsafe(64)[:96]
        challenge_digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_digest).rstrip(b"=").decode("ascii")
        state = secrets.token_urlsafe(24)
        session_id = f"goauth-{secrets.token_hex(8)}"

        # Clean up any stale pending callback listeners before opening a new one
        self.stop_pending_servers()

        mgr = self

        class _CallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                return

            def do_GET(self) -> None:
                parsed = urllib.parse.urlsplit(self.path)
                if parsed.path != path_norm:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Not found")
                    return
                qs = urllib.parse.parse_qs(parsed.query)
                code = (qs.get("code") or [""])[0]
                cb_state = (qs.get("state") or [""])[0]
                err = (qs.get("error") or [""])[0]
                err_desc = (qs.get("error_description") or [""])[0]

                res = mgr.complete_callback(
                    session_id=session_id,
                    state=cb_state,
                    code=code,
                    error=err_desc or err,
                )
                ok = bool(res.get("ok"))
                email = str(res.get("email") or "")
                headline = f"Signed in as {email}" if ok else "Google sign-in failed"
                detail = (
                    "Authorization complete. Satz stored encrypted OAuth tokens in your active profile vault."
                    if ok
                    else str(res.get("error") or "OAuth exchange did not succeed.")
                )
                i18n_mgr = getattr(mgr.runtime, "i18n", None)
                if i18n_mgr is not None:
                    cb_copy = i18n_mgr.format_oauth_callback_copy(ok, headline, detail)
                    body = _render_callback_html(
                        ok,
                        cb_copy["headline"],
                        cb_copy["detail"],
                        lang=cb_copy["lang"],
                        direction=cb_copy["dir"],
                        page_title=cb_copy["title"],
                        badge_text=cb_copy["badge"],
                        hint_text=cb_copy["hint"],
                    )
                else:
                    body = _render_callback_html(ok, headline, detail)
                self.send_response(200 if ok else 400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

                # Close loopback listener asynchronously right after writing response
                def _shutdown_later() -> None:
                    time.sleep(0.35)
                    mgr._close_server(session_id)

                threading.Thread(target=_shutdown_later, daemon=True).start()

        server = ThreadingHTTPServer(("127.0.0.1", bind_port), _CallbackHandler)
        actual_port = server.server_address[1]
        redirect_uri = f"http://{host_norm}:{actual_port}{path_norm}"

        with self._lock:
            self._sessions[session_id] = {
                "session_id": session_id,
                "profile_id": profile_id,
                "status": "pending",
                "state": state,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
                "scopes": eff_scopes,
                "connect_gmail": bool(connect_gmail),
                "connect_drive": bool(connect_drive),
                "email": "",
                "error": "",
                "gmail_connected": False,
                "drive_connected": False,
                "created_at": time.time(),
            }
            self._servers[session_id] = server

        srv_thread = threading.Thread(target=server.serve_forever, daemon=True, name=f"satz-goauth-{session_id}")
        srv_thread.start()

        def _auto_expire() -> None:
            time.sleep(600.0)
            with self._lock:
                s = self._sessions.get(session_id)
                if s and s.get("status") == "pending":
                    s["status"] = "expired"
                    s["error"] = "Google OAuth session timed out after 10 minutes."
            self._close_server(session_id)

        threading.Thread(target=_auto_expire, daemon=True).start()

        params = {
            "client_id": cid,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(eff_scopes),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        hint_clean = (login_hint or env_map.get(f"{VAULT_PREFIX}_EMAIL") or "").strip()
        hd_clean = (hd or "").strip()
        if hint_clean:
            params["login_hint"] = hint_clean
        if hd_clean:
            params["hd"] = hd_clean
        auth_url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
        return {
            "ok": True,
            "session_id": session_id,
            "auth_url": auth_url,
            "redirect_uri": redirect_uri,
            "scopes": eff_scopes,
        }

    def complete_callback(
        self,
        *,
        session_id: str,
        state: str,
        code: str = "",
        error: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                return {"ok": False, "error": "OAuth session not found or expired."}
            if sess.get("profile_id") != self.passwords.active_profile_id or not self.passwords.unlocked:
                sess["status"] = "error"
                sess["error"] = "Profile was locked or switched during Google sign-in."
                return {"ok": False, "error": sess["error"]}
            expected_state = str(sess.get("state") or "")
            if not state or not hmac.compare_digest(state.encode("utf-8"), expected_state.encode("utf-8")):
                sess["status"] = "error"
                sess["error"] = "Invalid OAuth CSRF state parameter."
                return {"ok": False, "error": sess["error"]}
            if error:
                sess["status"] = "error"
                sess["error"] = error
                return {"ok": False, "error": error}
            if not code:
                sess["status"] = "error"
                sess["error"] = "Missing authorization code from Google redirect."
                return {"ok": False, "error": sess["error"]}

            env_map = self.passwords.get_unlocked_credentials_map()
            cid = env_map.get(f"{VAULT_PREFIX}_CLIENT_ID", "").strip()
            csec = env_map.get(f"{VAULT_PREFIX}_CLIENT_SECRET", "").strip()
            redirect_uri = str(sess["redirect_uri"])
            code_verifier = str(sess["code_verifier"])
            eff_scopes = list(sess.get("scopes") or DEFAULT_GOOGLE_SCOPES)
            connect_gmail = bool(sess.get("connect_gmail"))
            connect_drive = bool(sess.get("connect_drive"))

        try:
            tok_resp = self._http_post_form(
                GOOGLE_TOKEN_URL,
                {
                    "code": code,
                    "client_id": cid,
                    "client_secret": csec,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                },
            )
            access_tok = str(tok_resp.get("access_token") or "").strip()
            if not access_tok:
                raise RuntimeError(f"Token response missing access_token: {tok_resp}")
            refresh_tok = str(tok_resp.get("refresh_token") or env_map.get(f"{VAULT_PREFIX}_REFRESH_TOKEN") or "").strip()
            expires_in = float(tok_resp.get("expires_in") or 3600.0)
            expiry_ts = time.time() + max(60.0, expires_in)
            granted_scope = str(tok_resp.get("scope") or " ".join(eff_scopes)).strip()

            uinfo = self._http_get_userinfo(access_tok)
            email = str(uinfo.get("email") or env_map.get(f"{VAULT_PREFIX}_EMAIL") or "").strip()
            name = str(uinfo.get("name") or env_map.get(f"{VAULT_PREFIX}_NAME") or email).strip()

            updates: dict[str, str] = {
                f"{VAULT_PREFIX}_ACCESS_TOKEN": access_tok,
                f"{VAULT_PREFIX}_EXPIRY": str(round(expiry_ts, 3)),
                f"{VAULT_PREFIX}_SCOPES": granted_scope,
            }
            if refresh_tok:
                updates[f"{VAULT_PREFIX}_REFRESH_TOKEN"] = refresh_tok
            if email:
                updates[f"{VAULT_PREFIX}_EMAIL"] = email
            if name:
                updates[f"{VAULT_PREFIX}_NAME"] = name
            self.passwords.update_vault_entries(updates)

            gmail_connected = False
            if connect_gmail and email and "https://mail.google.com/" in granted_scope and getattr(self.runtime, "mail", None):
                try:
                    self.runtime.mail.connect_google_oauth_account(email=email, label=name or email)
                    gmail_connected = True
                except Exception as me:
                    self.runtime.record_error("google_oauth_mail_link", me)

            drive_connected = False
            has_drive_scope = any(
                sc in granted_scope.split()
                for sc in (
                    GOOGLE_DRIVE_READONLY_SCOPE,
                    "https://www.googleapis.com/auth/drive",
                    "https://www.googleapis.com/auth/drive.metadata.readonly",
                )
            )
            if (connect_drive or has_drive_scope) and email and has_drive_scope and getattr(self.runtime, "drives", None):
                try:
                    self.runtime.drives.on_google_connected(email=email, name=name or email)
                    drive_connected = True
                except Exception as de:
                    self.runtime.record_error("google_oauth_drive_link", de)

            with self._lock:
                sess["status"] = "authorized"
                sess["email"] = email
                sess["name"] = name
                sess["gmail_connected"] = gmail_connected
                sess["drive_connected"] = drive_connected
                sess["error"] = ""

            return {
                "ok": True,
                "status": "authorized",
                "email": email,
                "name": name,
                "gmail_connected": gmail_connected,
                "drive_connected": drive_connected,
            }
        except Exception as exc:
            with self._lock:
                sess["status"] = "error"
                sess["error"] = str(exc)
            return {"ok": False, "error": str(exc)}

    def get_valid_access_token(self, expected_email: str = "", force_refresh: bool = False) -> str:
        """
        Returns an active Google OAuth access_token for the unlocked profile,
        transparently refreshing via `refresh_token` when expired or forced.
        """
        self._require_unlocked()
        env_map = self.passwords.get_unlocked_credentials_map()
        stored_email = env_map.get(f"{VAULT_PREFIX}_EMAIL", "").strip().lower()
        if expected_email and stored_email and expected_email.strip().lower() != stored_email:
            raise PermissionError(
                f"Google OAuth session is signed in as '{stored_email}', not '{expected_email}'."
            )

        access_tok = env_map.get(f"{VAULT_PREFIX}_ACCESS_TOKEN", "").strip()
        refresh_tok = env_map.get(f"{VAULT_PREFIX}_REFRESH_TOKEN", "").strip()
        cid = env_map.get(f"{VAULT_PREFIX}_CLIENT_ID", "").strip()
        csec = env_map.get(f"{VAULT_PREFIX}_CLIENT_SECRET", "").strip()
        try:
            expiry_ts = float(env_map.get(f"{VAULT_PREFIX}_EXPIRY", "0") or 0.0)
        except ValueError:
            expiry_ts = 0.0

        if not force_refresh and access_tok and expiry_ts > (time.time() + 60.0):
            return access_tok

        if not refresh_tok or not cid or not csec:
            if access_tok and not force_refresh:
                return access_tok
            raise PermissionError("Google OAuth refresh token missing. Sign in with Google again.")

        tok_resp = self._http_post_form(
            GOOGLE_TOKEN_URL,
            {
                "client_id": cid,
                "client_secret": csec,
                "refresh_token": refresh_tok,
                "grant_type": "refresh_token",
            },
        )
        new_access = str(tok_resp.get("access_token") or "").strip()
        if not new_access:
            raise RuntimeError(f"Failed refreshing Google OAuth token: {tok_resp}")
        expires_in = float(tok_resp.get("expires_in") or 3600.0)
        new_expiry = time.time() + max(60.0, expires_in)
        updates = {
            f"{VAULT_PREFIX}_ACCESS_TOKEN": new_access,
            f"{VAULT_PREFIX}_EXPIRY": str(round(new_expiry, 3)),
        }
        if tok_resp.get("refresh_token"):
            updates[f"{VAULT_PREFIX}_REFRESH_TOKEN"] = str(tok_resp["refresh_token"]).strip()
        self.passwords.update_vault_entries(updates)
        return new_access

    def disconnect(self, clear_client_config: bool = False) -> dict[str, Any]:
        self._require_unlocked()
        self.stop_pending_servers()
        keys = [
            f"{VAULT_PREFIX}_ACCESS_TOKEN",
            f"{VAULT_PREFIX}_REFRESH_TOKEN",
            f"{VAULT_PREFIX}_EXPIRY",
            f"{VAULT_PREFIX}_EMAIL",
            f"{VAULT_PREFIX}_NAME",
        ]
        if clear_client_config:
            keys.extend([f"{VAULT_PREFIX}_CLIENT_ID", f"{VAULT_PREFIX}_CLIENT_SECRET", f"{VAULT_PREFIX}_SCOPES", f"{VAULT_PREFIX}_REDIRECT_PORT"])
        self.passwords.delete_vault_keys(keys)
        return self.get_status()

    def _close_server(self, session_id: str) -> None:
        with self._lock:
            srv = self._servers.pop(session_id, None)
        if srv is not None:
            try:
                srv.shutdown()
            except Exception:
                pass
            try:
                srv.server_close()
            except Exception:
                pass

    def stop_pending_servers(self) -> None:
        with self._lock:
            sids = list(self._servers.keys())
        for sid in sids:
            self._close_server(sid)
