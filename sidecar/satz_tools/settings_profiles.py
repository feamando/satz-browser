"""Profile creation, listing, unlock, and switch tools (PINs never pass through LLM)."""
from __future__ import annotations

import secrets
from typing import Any

from satz_tools.registry import satz_tool
from satz_tools.settings_staging import create_confirm_gate


@satz_tool(
    name="settings_list_profiles",
    domain="settings",
    mode="read",
    mcp_safe=True,
    description="List existing encrypted Satz profiles, active unlocked state, and keychain availability.",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def settings_list_profiles(runtime: Any, session: Any = None) -> dict[str, Any]:
    return {"model_payload": runtime.passwords.list_profiles()}


@satz_tool(
    name="settings_prepare_create_profile",
    domain="settings",
    mode="ui_prompt",
    mcp_safe=False,
    description=(
        "Prepare an inline profile onboarding card so the user can create a new encrypted profile "
        "and enter their 6-digit PIN safely outside LLM context."
    ),
    parameters={
        "type": "object",
        "properties": {
            "profile_name": {
                "type": "string",
                "description": "Desired display/identifier name for the new profile (e.g. ngorshkov).",
            },
            "enable_keychain": {
                "type": "boolean",
                "description": "Whether to hint enabling OS keychain / Touch ID unlock when supported.",
            },
        },
        "required": ["profile_name"],
    },
)
def settings_prepare_create_profile(
    runtime: Any,
    session: Any = None,
    profile_name: str = "",
    enable_keychain: bool = True,
) -> dict[str, Any]:
    clean_name = (profile_name or "").strip()[:48]
    if not clean_name:
        return {"model_payload": {"ok": False, "error": "Provide a non-empty profile_name."}}

    profiles_state = runtime.passwords.list_profiles()
    existing_names = {
        str(p.get("name") or "").lower(): str(p.get("id") or "")
        for p in (profiles_state.get("profiles") or [])
    }
    already_id = existing_names.get(clean_name.lower()) or next(
        (
            str(p.get("id") or "")
            for p in (profiles_state.get("profiles") or [])
            if str(p.get("id") or "").lower() == clean_name.lower()
        ),
        "",
    )
    if already_id:
        card = {
            "id": f"card_{secrets.token_hex(4)}",
            "kind": "profile_unlock_card",
            "title": f"Profile '{clean_name}' already exists",
            "subtitle": "Enter its 6-digit PIN or use quick unlock below to switch into it.",
            "data": {
                "profile_id": already_id,
                "profile_name": clean_name,
                "keychain_available": bool(profiles_state.get("keychain_supported")),
            },
        }
        return {
            "model_payload": {
                "ok": True,
                "already_exists": True,
                "profile_id": already_id,
                "ui_card_emitted": "profile_unlock_card",
                "instruction": "A profile with this name already exists; tell the user they can unlock/switch to it via the rendered card.",
            },
            "ui_cards": [card],
        }

    card = {
        "id": f"card_{secrets.token_hex(4)}",
        "kind": "profile_create_card",
        "title": f"Create profile: {clean_name}",
        "subtitle": "Choose a 6-digit PIN to encrypt vault.enc, Mail, and Brain for this profile.",
        "data": {
            "profile_name": clean_name,
            "enable_keychain": bool(enable_keychain),
            "keychain_available": bool(profiles_state.get("keychain_supported")),
        },
    }
    return {
        "model_payload": {
            "ok": True,
            "profile_name": clean_name,
            "ui_card_emitted": "profile_create_card",
            "instruction": "An inline profile creation card with masked PIN inputs is now displayed. Ask the user to set a 6-digit PIN and click Create & unlock.",
        },
        "ui_cards": [card],
    }


@satz_tool(
    name="settings_prepare_unlock_or_switch_profile",
    domain="settings",
    mode="confirm_gate",
    mcp_safe=False,
    description=(
        "Prepare an inline card to unlock or switch to an existing Satz profile via 6-digit PIN "
        "or OS keychain / Touch ID."
    ),
    parameters={
        "type": "object",
        "properties": {
            "profile_id": {
                "type": "string",
                "description": "Profile id or name to unlock/switch to.",
            },
            "use_keychain": {
                "type": "boolean",
                "description": "Set true to prepare a Touch ID / OS keychain unlock confirmation when available.",
            },
        },
        "required": ["profile_id"],
    },
)
def settings_prepare_unlock_or_switch_profile(
    runtime: Any,
    session: Any = None,
    profile_id: str = "",
    use_keychain: bool = False,
) -> dict[str, Any]:
    target_raw = (profile_id or "").strip()
    st = runtime.passwords.list_profiles()
    profiles = st.get("profiles") or []
    match = next(
        (
            p
            for p in profiles
            if str(p.get("id") or "").lower() == target_raw.lower()
            or str(p.get("name") or "").lower() == target_raw.lower()
        ),
        None,
    )
    if not match:
        return {
            "model_payload": {
                "ok": False,
                "error": f"No profile matching '{target_raw}' found.",
                "available_profiles": [p.get("id") for p in profiles],
            }
        }

    pid = str(match["id"])
    pname = str(match.get("name") or pid)
    if bool(match.get("is_active")):
        return {
            "model_payload": {
                "ok": True,
                "already_active": True,
                "profile_id": pid,
                "profile_name": pname,
            }
        }

    if use_keychain and match.get("has_keychain_unlock"):
        tok = create_confirm_gate(
            runtime,
            action_type="switch_or_unlock_profile",
            summary=f"Switch active profile to '{pname}' ({pid}) via OS keychain",
            params={"profile_id": pid, "use_keychain": True},
        )
        card = {
            "id": f"card_{secrets.token_hex(4)}",
            "kind": "confirm_gate_card",
            "title": f"Switch profile to {pname}",
            "subtitle": f"Unlocks '{pname}' ({pid}) via OS keychain and rebinds Brain, Mail, and Vault.",
            "confirm_token": tok,
            "data": {
                "action_type": "switch_or_unlock_profile",
                "profile_id": pid,
                "profile_name": pname,
                "requires_pin": False,
            },
        }
        return {
            "model_payload": {
                "ok": True,
                "profile_id": pid,
                "confirm_required": True,
                "ui_card_emitted": "confirm_gate_card",
            },
            "ui_cards": [card],
        }

    card = {
        "id": f"card_{secrets.token_hex(4)}",
        "kind": "profile_unlock_card",
        "title": f"Unlock profile: {pname}",
        "subtitle": f"Enter the 6-digit PIN for '{pname}' ({pid}) or use quick unlock.",
        "data": {
            "profile_id": pid,
            "profile_name": pname,
            "keychain_available": bool(match.get("has_keychain_unlock") or st.get("keychain_supported")),
        },
    }
    return {
        "model_payload": {
            "ok": True,
            "profile_id": pid,
            "ui_card_emitted": "profile_unlock_card",
        },
        "ui_cards": [card],
    }
