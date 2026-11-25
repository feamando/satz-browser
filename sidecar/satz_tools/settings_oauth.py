"""Google OAuth client configuration & browser-tab login tools."""
from __future__ import annotations

import secrets
from typing import Any

from satz_google_auth import DEFAULT_GOOGLE_SCOPES
from satz_tools.registry import satz_tool
from satz_tools.settings_staging import create_confirm_gate, get_staged_file_entry


_SCOPE_PRESETS: dict[str, list[str]] = {
    "gmail": list(DEFAULT_GOOGLE_SCOPES),
    "gmail_and_drive": [
        *DEFAULT_GOOGLE_SCOPES,
        *(
            ["https://www.googleapis.com/auth/drive.readonly"]
            if "https://www.googleapis.com/auth/drive.readonly" not in DEFAULT_GOOGLE_SCOPES
            else []
        ),
    ],
    "calendar": [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/calendar.readonly",
    ],
    "drive": [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/drive.readonly",
    ],
    "basic": [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ],
}


@satz_tool(
    name="settings_configure_google_oauth",
    domain="settings",
    mode="staged_write",
    mcp_safe=False,
    description=(
        "Save a staged Google OAuth client_secret.json file (referenced by staging_id) into "
        "encrypted profile vault.enc and prepare the Google sign-in button card."
    ),
    parameters={
        "type": "object",
        "properties": {
            "staging_id": {
                "type": "string",
                "description": "Staged file handle returned when user attached their client_secret JSON.",
            },
            "scopes_preset": {
                "type": "string",
                "enum": ["gmail", "gmail_and_drive", "calendar", "drive", "basic"],
                "description": "OAuth scope bundle (defaults to gmail; use drive or gmail_and_drive for Google Drive).",
            },
            "redirect_port": {
                "type": "integer",
                "description": "Optional fixed loopback port for Web OAuth clients (0 = automatic).",
            },
        },
        "required": ["staging_id"],
    },
)
def settings_configure_google_oauth(
    runtime: Any,
    session: Any = None,
    staging_id: str = "",
    scopes_preset: str = "gmail",
    redirect_port: int = 0,
) -> dict[str, Any]:
    if not getattr(runtime.passwords, "unlocked", False):
        profiles_st = runtime.passwords.list_profiles()
        profiles = profiles_st.get("profiles") or []
        first_pid = str((profiles[0] if profiles else {}).get("id") or "")
        if first_pid:
            card = {
                "id": f"card_{secrets.token_hex(4)}",
                "kind": "profile_unlock_card",
                "title": "Unlock profile before saving Google OAuth credentials",
                "subtitle": "Google client secrets are encrypted inside your active profile vault.enc.",
                "data": {
                    "profile_id": first_pid,
                    "profile_name": str((profiles[0] if profiles else {}).get("name") or first_pid),
                    "keychain_available": bool(profiles_st.get("keychain_supported")),
                },
            }
            return {
                "model_payload": {
                    "ok": False,
                    "error": "Active profile is locked. Unlock a profile first so client_secret can be encrypted in vault.enc.",
                    "ui_card_emitted": "profile_unlock_card",
                },
                "ui_cards": [card],
            }
        card = {
            "id": f"card_{secrets.token_hex(4)}",
            "kind": "profile_create_card",
            "title": "Create a profile before saving Google OAuth credentials",
            "subtitle": "Google OAuth secrets require an encrypted profile vault.",
            "data": {"profile_name": "default", "enable_keychain": True},
        }
        return {
            "model_payload": {
                "ok": False,
                "error": "No unlocked profile found. Create a profile first.",
                "ui_card_emitted": "profile_create_card",
            },
            "ui_cards": [card],
        }

    entry = get_staged_file_entry(runtime, staging_id, include_raw=True)
    if not entry:
        return {
            "model_payload": {
                "ok": False,
                "error": f"Staged file '{staging_id}' expired or was not found. Ask the user to attach client_secret.json again.",
            }
        }
    if entry.get("detected_kind") != "google_client_secret":
        return {
            "model_payload": {
                "ok": False,
                "error": f"File '{entry.get('filename')}' was detected as {entry.get('detected_kind')}, not a Google OAuth client_secret JSON.",
            }
        }

    scopes = _SCOPE_PRESETS.get((scopes_preset or "gmail").strip().lower(), list(DEFAULT_GOOGLE_SCOPES))
    port_val = max(0, min(65535, int(redirect_port or 0)))
    st = runtime.google_auth.save_client_config(
        client_secret_json=entry.get("raw_text") or "",
        scopes=scopes,
        redirect_port=port_val,
    )
    if not st.get("ok"):
        return {"model_payload": {"ok": False, "error": str(st.get("error") or "Failed to save Google client config.")}}

    card = {
        "id": f"card_{secrets.token_hex(4)}",
        "kind": "google_oauth_connect_card",
        "title": "Google OAuth client saved",
        "subtitle": f"Encrypted in vault.enc ({st.get('masked_client_id') or 'ready'}). Click below to open Google sign-in in a Satz browser tab.",
        "data": {
            "configured": bool(st.get("configured")),
            "signed_in": bool(st.get("signed_in")),
            "email": st.get("email") or "",
            "masked_client_id": st.get("masked_client_id") or "",
            "redirect_port": st.get("redirect_port") or 0,
            "scopes": st.get("scopes") or scopes,
        },
    }
    st_scopes = [str(s) for s in (st.get("scopes") or scopes)]
    return {
        "model_payload": {
            "ok": True,
            "masked_client_id": st.get("masked_client_id"),
            "configured": bool(st.get("configured")),
            "signed_in": bool(st.get("signed_in")),
            "scopes": st_scopes,
            "drive_scope_authorized": any("drive" in s.lower() for s in st_scopes),
            "ui_card_emitted": "google_oauth_connect_card",
            "instruction": "Client secret saved into vault.enc. Tell the user to click 'Sign in with Google in browser tab' on the rendered card (or call settings_start_google_oauth if asked to open sign-in immediately).",
        },
        "ui_cards": [card],
    }


@satz_tool(
    name="settings_start_google_oauth",
    domain="settings",
    mode="ui_prompt",
    mcp_safe=False,
    description=(
        "Start a loopback Google OAuth 2.0 PKCE login session and emit an inline card with the "
        "Open Google sign-in tab action."
    ),
    parameters={
        "type": "object",
        "properties": {
            "scopes_preset": {
                "type": "string",
                "enum": ["gmail", "gmail_and_drive", "calendar", "drive", "basic"],
                "description": "Optional scope preset if overriding defaults (use drive or gmail_and_drive for Cloud Drives).",
            }
        },
        "required": [],
    },
)
def settings_start_google_oauth(
    runtime: Any,
    session: Any = None,
    scopes_preset: str = "",
) -> dict[str, Any]:
    if not getattr(runtime.passwords, "unlocked", False):
        return {
            "model_payload": {
                "ok": False,
                "error": "Active profile is locked. Unlock a profile before starting Google OAuth.",
            }
        }
    scopes = _SCOPE_PRESETS.get(scopes_preset.strip().lower()) if scopes_preset else None
    try:
        res = runtime.google_auth.start_login(scopes=scopes)
    except Exception as exc:
        return {"model_payload": {"ok": False, "error": str(exc)}}

    if not res.get("ok"):
        return {"model_payload": {"ok": False, "error": str(res.get("error") or "Could not start Google OAuth login.")}}

    st = runtime.google_auth.get_status(session_id=str(res.get("session_id") or ""))
    card = {
        "id": f"card_{secrets.token_hex(4)}",
        "kind": "google_oauth_connect_card",
        "title": "Sign in with Google",
        "subtitle": "Click Open Google sign-in to authorize inside a live Satz browser tab.",
        "data": {
            "configured": True,
            "signed_in": bool(st.get("signed_in")),
            "email": st.get("email") or "",
            "masked_client_id": st.get("masked_client_id") or "",
            "session_id": res.get("session_id") or "",
            "auth_url": res.get("auth_url") or "",
            "redirect_uri": res.get("redirect_uri") or "",
            "scopes": res.get("scopes") or [],
        },
    }
    req_scopes = [str(s) for s in (res.get("scopes") or [])]
    return {
        "model_payload": {
            "ok": True,
            "session_id": res.get("session_id"),
            "redirect_uri": res.get("redirect_uri"),
            "scopes": req_scopes,
            "drive_scope_authorized": any("drive" in s.lower() for s in req_scopes),
            "ui_card_emitted": "google_oauth_connect_card",
            "instruction": "Loopback OAuth listener is ready. Instruct the user to click 'Open Google sign-in' on the card to complete sign-in in their browser tab.",
        },
        "ui_cards": [card],
    }


@satz_tool(
    name="settings_refresh_or_disconnect_google",
    domain="settings",
    mode="confirm_gate",
    mcp_safe=False,
    description=(
        "Refresh the active Google OAuth access token or prepare a confirmation gate to disconnect Google OAuth."
    ),
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["refresh", "disconnect"],
                "description": "Use 'refresh' to renew tokens now or 'disconnect' to request confirmation.",
            },
            "clear_client_config": {
                "type": "boolean",
                "description": "When disconnecting, also clear stored client_id/client_secret from vault.enc.",
            },
        },
        "required": ["action"],
    },
)
def settings_refresh_or_disconnect_google(
    runtime: Any,
    session: Any = None,
    action: str = "refresh",
    clear_client_config: bool = False,
) -> dict[str, Any]:
    if not getattr(runtime.passwords, "unlocked", False):
        return {"model_payload": {"ok": False, "error": "Unlock an active profile first."}}

    act = (action or "refresh").strip().lower()
    if act == "refresh":
        try:
            runtime.google_auth.get_valid_access_token(force_refresh=True)
            st = runtime.google_auth.get_status()
            return {
                "model_payload": {
                    "ok": True,
                    "signed_in": bool(st.get("signed_in")),
                    "email": st.get("email") or "",
                    "expires_at": st.get("expires_at") or 0,
                }
            }
        except Exception as exc:
            return {"model_payload": {"ok": False, "error": str(exc)}}

    tok = create_confirm_gate(
        runtime,
        action_type="google_disconnect",
        summary=(
            "Disconnect Google OAuth session tokens and erase saved client credentials from vault.enc"
            if clear_client_config
            else "Disconnect active Google OAuth session tokens (keeps saved client credentials)"
        ),
        params={"clear_client_config": bool(clear_client_config)},
    )
    card = {
        "id": f"card_{secrets.token_hex(4)}",
        "kind": "confirm_gate_card",
        "title": "Disconnect Google account",
        "subtitle": (
            "Removes saved OAuth tokens and client config from vault.enc."
            if clear_client_config
            else "Revokes local Google OAuth session tokens."
        ),
        "confirm_token": tok,
        "data": {
            "action_type": "google_disconnect",
            "danger": bool(clear_client_config),
            "clear_client_config": bool(clear_client_config),
        },
    }
    return {
        "model_payload": {
            "ok": True,
            "confirm_required": True,
            "ui_card_emitted": "confirm_gate_card",
        },
        "ui_cards": [card],
    }
