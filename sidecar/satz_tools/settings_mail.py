"""Mail account inspection and guided IMAP / POP3 / Gmail OAuth onboarding tools."""
from __future__ import annotations

import secrets
from typing import Any

from satz_tools.registry import satz_tool


@satz_tool(
    name="settings_list_mail_accounts",
    domain="settings",
    mode="read",
    mcp_safe=True,
    description="List configured Mail accounts (email, protocol, unread count, last sync) and preset hosts.",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def settings_list_mail_accounts(runtime: Any, session: Any = None) -> dict[str, Any]:
    res = runtime.mail.list_accounts()
    return {
        "model_payload": {
            "ok": bool(res.get("ok", True)),
            "unlocked": bool(res.get("unlocked")),
            "accounts": res.get("accounts") or [],
            "presets": res.get("presets") or [],
        }
    }


@satz_tool(
    name="settings_prepare_add_mail_account",
    domain="settings",
    mode="ui_prompt",
    mcp_safe=False,
    redacted_args=("password", "app_password"),
    description=(
        "Prepare an inline Mail account setup card pre-filled with IMAP/SMTP host defaults (or Gmail XOAUTH2) "
        "so the user can test and save their email credentials securely outside LLM context."
    ),
    parameters={
        "type": "object",
        "properties": {
            "email": {
                "type": "string",
                "description": "Email address to configure.",
            },
            "label": {
                "type": "string",
                "description": "Friendly display label (e.g. Work or Personal).",
            },
            "provider_hint": {
                "type": "string",
                "enum": ["gmail", "icloud", "outlook", "gmx", "webde", "custom_imap"],
                "description": "Mail provider hint matching Satz presets.",
            },
        },
        "required": [],
    },
)
def settings_prepare_add_mail_account(
    runtime: Any,
    session: Any = None,
    email: str = "",
    label: str = "",
    provider_hint: str = "",
) -> dict[str, Any]:
    unlocked = bool(getattr(runtime.passwords, "unlocked", False))
    if not unlocked:
        profiles_st = runtime.passwords.list_profiles()
        profiles = profiles_st.get("profiles") or []
        first_pid = str((profiles[0] if profiles else {}).get("id") or "")
        card = {
            "id": f"card_{secrets.token_hex(4)}",
            "kind": "profile_unlock_card" if first_pid else "profile_create_card",
            "title": "Unlock profile before adding a mail account" if first_pid else "Create a profile first",
            "subtitle": "Mail credentials are stored encrypted in vault.enc and synced to profile mail.sqlite.",
            "data": {
                "profile_id": first_pid,
                "profile_name": "default" if not first_pid else str((profiles[0] if profiles else {}).get("name") or first_pid),
                "keychain_available": bool(profiles_st.get("keychain_supported")),
            },
        }
        return {
            "model_payload": {
                "ok": False,
                "error": "Unlock an active profile before configuring Mail accounts.",
                "ui_card_emitted": card["kind"],
            },
            "ui_cards": [card],
        }

    em = (email or "").strip()
    hint = (provider_hint or "").strip().lower()
    if not hint and "@" in em:
        dom = em.split("@", 1)[1].lower()
        if "gmail." in dom or "googlemail." in dom:
            hint = "gmail"
        elif "icloud." in dom or "me.com" in dom:
            hint = "icloud"
        elif "outlook." in dom or "hotmail." in dom or "live." in dom:
            hint = "outlook"
        elif "gmx." in dom:
            hint = "gmx"
        elif "web.de" in dom:
            hint = "webde"
        else:
            hint = "custom_imap"
    if not hint or hint == "imap":
        hint = "custom_imap"

    ml = runtime.mail.list_accounts()
    presets = ml.get("presets") or []
    oauth_st = runtime.google_auth.get_status()

    card = {
        "id": f"card_{secrets.token_hex(4)}",
        "kind": "mail_account_card",
        "title": f"Add mail account{f': {em}' if em else ''}",
        "subtitle": "Credentials are tested directly over TLS and stored encrypted in vault.enc.",
        "data": {
            "email": em,
            "label": (label or (em.split("@", 1)[0] if "@" in em else "")).strip(),
            "provider_hint": hint,
            "presets": presets,
            "google_signed_in": bool(oauth_st.get("signed_in")),
            "google_email": oauth_st.get("email") or "",
        },
    }
    return {
        "model_payload": {
            "ok": True,
            "email": em,
            "provider_hint": hint,
            "google_signed_in": bool(oauth_st.get("signed_in")),
            "ui_card_emitted": "mail_account_card",
        },
        "ui_cards": [card],
    }
