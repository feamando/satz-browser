"""Action provider discovery, setup, and destructive resource confirmation tools."""
from __future__ import annotations

import secrets
from typing import Any

from satz_tools.registry import satz_tool
from satz_tools.settings_staging import create_confirm_gate


@satz_tool(
    name="settings_list_providers",
    domain="settings",
    mode="read",
    mcp_safe=True,
    description="List action provider categories and configured providers (Search, Maps, Flights, Shopping, Custom).",
    parameters={
        "type": "object",
        "properties": {
            "category_id": {
                "type": "string",
                "description": "Optional category id filter.",
            }
        },
        "required": [],
    },
)
def settings_list_providers(
    runtime: Any,
    session: Any = None,
    category_id: str = "",
) -> dict[str, Any]:
    reg = runtime.providers.list_registry()
    cat_filter = (category_id or "").strip()
    cats = reg.get("categories") or []
    if cat_filter:
        cats = [c for c in cats if str(c.get("id") or "") == cat_filter]
    by_cat = reg.get("providers_by_category") or {}
    return {
        "model_payload": {
            "ok": bool(reg.get("ok", True)),
            "unlocked": bool(reg.get("unlocked")),
            "categories": [
                {
                    "id": c.get("id"),
                    "label": c.get("label"),
                    "providers": [
                        {
                            "id": p.get("id"),
                            "display_name": p.get("display_name"),
                            "mode": p.get("mode"),
                            "domains": p.get("domains"),
                            "priority": p.get("priority"),
                            "auth_ready": bool(p.get("auth_ready")),
                            "masked_auth_label": p.get("masked_auth_label") or "",
                        }
                        for p in (by_cat.get(str(c.get("id") or ""), []) or [])
                    ],
                }
                for c in cats
            ],
        }
    }


@satz_tool(
    name="settings_infer_and_prepare_provider",
    domain="settings",
    mode="staged_write",
    mcp_safe=False,
    description=(
        "Infer a website or search-API action provider from a name or URL (e.g. booking.com, brave, idealo.de) "
        "and emit a preview card to save it under a category."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url_or_name": {
                "type": "string",
                "description": "Site URL, domain, or provider name.",
            },
            "category_id": {
                "type": "string",
                "description": "Target category id (e.g. web_search, accommodation, shopping_tech).",
            },
        },
        "required": ["url_or_name"],
    },
)
def settings_infer_and_prepare_provider(
    runtime: Any,
    session: Any = None,
    url_or_name: str = "",
    category_id: str = "",
) -> dict[str, Any]:
    raw_in = (url_or_name or "").strip()
    if not raw_in:
        return {"model_payload": {"ok": False, "error": "Provide a url_or_name."}}
    cat = (category_id or "").strip()
    inf = runtime.providers.infer_provider_template(raw_in, category_id=cat)
    if not inf.get("ok"):
        return {"model_payload": {"ok": False, "error": str(inf.get("error") or "Could not infer provider.")}}

    reg = runtime.providers.list_registry()
    cats = [{"id": c.get("id"), "label": c.get("label")} for c in (reg.get("categories") or [])]
    chosen_cat = cat or str(inf.get("suggested_category_id") or (cats[0]["id"] if cats else "custom"))

    card = {
        "id": f"card_{secrets.token_hex(4)}",
        "kind": "provider_preview_card",
        "title": f"Add provider: {inf.get('display_name') or raw_in}",
        "subtitle": f"Domain: {', '.join(inf.get('domains') or [])} · mode: {inf.get('mode') or 'web_account'}",
        "data": {
            "category_id": chosen_cat,
            "categories": cats,
            "display_name": inf.get("display_name") or raw_in,
            "domains": inf.get("domains") or [],
            "url_template": inf.get("url_template") or "",
            "mode": inf.get("mode") or "web_account",
            "api_driver": inf.get("api_driver") or "",
            "vault_service": inf.get("vault_service") or "",
            "auth_ready": bool(inf.get("auth_ready")),
            "masked_auth_label": inf.get("masked_auth_label") or "",
        },
    }
    return {
        "model_payload": {
            "ok": True,
            "category_id": chosen_cat,
            "display_name": inf.get("display_name"),
            "domains": inf.get("domains"),
            "url_template": inf.get("url_template"),
            "ui_card_emitted": "provider_preview_card",
        },
        "ui_cards": [card],
    }


@satz_tool(
    name="settings_delete_resource_confirm",
    domain="settings",
    mode="confirm_gate",
    mcp_safe=False,
    description=(
        "Prepare a confirmation gate card with a danger banner before removing a profile, mail account, or provider."
    ),
    parameters={
        "type": "object",
        "properties": {
            "resource_type": {
                "type": "string",
                "enum": ["profile", "mail_account", "provider"],
                "description": "Resource type to remove.",
            },
            "resource_id": {
                "type": "string",
                "description": "Exact identifier (profile_id, account_id, or provider_id).",
            },
        },
        "required": ["resource_type", "resource_id"],
    },
)
def settings_delete_resource_confirm(
    runtime: Any,
    session: Any = None,
    resource_type: str = "",
    resource_id: str = "",
) -> dict[str, Any]:
    rtype = (resource_type or "").strip().lower()
    rid = (resource_id or "").strip()
    if rtype not in {"profile", "mail_account", "provider"} or not rid:
        return {
            "model_payload": {
                "ok": False,
                "error": "Provide valid resource_type (profile|mail_account|provider) and resource_id.",
            }
        }

    act_map = {
        "profile": "delete_profile",
        "mail_account": "remove_mail_account",
        "provider": "delete_provider",
    }
    param_key = {
        "profile": "profile_id",
        "mail_account": "account_id",
        "provider": "provider_id",
    }[rtype]
    summary = f"Permanently remove {rtype.replace('_', ' ')} '{rid}'"
    tok = create_confirm_gate(
        runtime,
        action_type=act_map[rtype],
        summary=summary,
        params={param_key: rid},
    )
    card = {
        "id": f"card_{secrets.token_hex(4)}",
        "kind": "confirm_gate_card",
        "title": f"Remove {rtype.replace('_', ' ')}: {rid}",
        "subtitle": summary,
        "confirm_token": tok,
        "data": {
            "action_type": act_map[rtype],
            "resource_type": rtype,
            "resource_id": rid,
            "danger": True,
            "requires_pin": rtype == "profile",
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
