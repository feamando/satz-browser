"""Model role configuration & API-key / .env vault onboarding tools (zero secret echo)."""
from __future__ import annotations

import secrets
from typing import Any

from satz_tools.registry import satz_tool
from satz_tools.settings_staging import create_confirm_gate, get_staged_file_entry


@satz_tool(
    name="settings_get_model_roles",
    domain="settings",
    mode="read",
    mcp_safe=True,
    description=(
        "Inspect active model roles (chat, web_answer, reader, news_planner, news_analyzer) "
        "and configured cloud API providers without exposing raw API keys."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def settings_get_model_roles(runtime: Any, session: Any = None) -> dict[str, Any]:
    cfg = runtime.get_model_management_config()
    safe_providers = [
        {
            "id": p.get("id"),
            "label": p.get("label"),
            "env_key": p.get("env_key"),
            "configured": bool(p.get("configured")),
            "key_source": p.get("key_source") or "none",
            "masked_key": p.get("masked_key") or "",
            "models": [m.get("id") for m in (p.get("models") or [])[:10]],
        }
        for p in (cfg.get("cloud_providers") or [])
    ]
    return {
        "model_payload": {
            "ok": True,
            "roles": cfg.get("roles") or {},
            "cloud_providers": safe_providers,
        }
    }


@satz_tool(
    name="settings_set_model_roles",
    domain="settings",
    mode="staged_write",
    mcp_safe=False,
    description=(
        "Update default Satz model role assignments (chat_model, reader_model, planner_model, or web_model) "
        "across local and configured cloud models."
    ),
    parameters={
        "type": "object",
        "properties": {
            "chat_model": {
                "type": "string",
                "description": "Model id for primary chat (e.g. gemma-4-e4b or gemini:gemini-3-flash-preview).",
            },
            "reader_model": {
                "type": "string",
                "description": "Model id for article reading (e.g. hertz (reader) or a cloud slug).",
            },
            "planner_model": {
                "type": "string",
                "description": "Model id for News planning (e.g. gemma-4-e4b or cloud slug).",
            },
            "web_model": {
                "type": "string",
                "description": "Model id for web answering (e.g. planck3 (web)).",
            },
        },
        "required": [],
    },
)
def settings_set_model_roles(
    runtime: Any,
    session: Any = None,
    chat_model: str = "",
    reader_model: str = "",
    planner_model: str = "",
    web_model: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if (chat_model or "").strip():
        payload["role_chat"] = chat_model.strip()
        payload["role_news_analyzer"] = chat_model.strip()
    if (reader_model or "").strip():
        payload["role_reader"] = reader_model.strip()
    if (planner_model or "").strip():
        payload["role_news_planner"] = planner_model.strip()
    if (web_model or "").strip():
        payload["role_web_answer"] = web_model.strip()

    if not payload:
        return {"model_payload": {"ok": False, "error": "Specify at least one model role to update."}}

    res = runtime.update_model_management_config(payload)
    if not res.get("ok"):
        return {"model_payload": {"ok": False, "error": str(res.get("error") or "Failed to update model roles.")}}

    return {
        "model_payload": {
            "ok": True,
            "roles": res.get("roles") or {},
            "message": "Updated model role routing.",
        }
    }


@satz_tool(
    name="settings_stage_api_key_or_env",
    domain="settings",
    mode="ui_prompt",
    mcp_safe=False,
    redacted_args=("api_key", "raw_env"),
    description=(
        "Add a cloud API key (Gemini, Anthropic, OpenAI, Mistral) or import keys from a staged .env file. "
        "NEVER accepts raw API keys in chat text: renders a masked vault input card or staged .env confirmation card."
    ),
    parameters={
        "type": "object",
        "properties": {
            "provider_id": {
                "type": "string",
                "enum": ["gemini", "anthropic", "openai", "mistral"],
                "description": "Target cloud provider when entering a single API key.",
            },
            "staging_id": {
                "type": "string",
                "description": "Optional staged .env file handle to import keys from.",
            },
        },
        "required": [],
    },
)
def settings_stage_api_key_or_env(
    runtime: Any,
    session: Any = None,
    provider_id: str = "",
    staging_id: str = "",
) -> dict[str, Any]:
    unlocked = bool(getattr(runtime.passwords, "unlocked", False))

    if (staging_id or "").strip():
        entry = get_staged_file_entry(runtime, staging_id, include_raw=False)
        if not entry:
            return {
                "model_payload": {
                    "ok": False,
                    "error": f"Staged file '{staging_id}' expired or was not found.",
                }
            }
        if entry.get("detected_kind") != "env_secrets":
            return {
                "model_payload": {
                    "ok": False,
                    "error": f"File '{entry.get('filename')}' was classified as {entry.get('detected_kind')}, not KEY=VALUE env pairs.",
                }
            }
        safe = entry.get("safe_fields") or {}
        keys_list = list(safe.get("keys") or [])
        previews = dict(safe.get("masked_previews") or {})
        if not unlocked:
            card = {
                "id": f"card_{secrets.token_hex(4)}",
                "kind": "profile_unlock_card",
                "title": "Unlock profile to import staged .env keys",
                "subtitle": f"Staged '{entry.get('filename')}' ({len(keys_list)} keys). Unlock a profile to store them encrypted in vault.enc.",
                "data": {
                    "profile_id": str(
                        ((runtime.passwords.list_profiles().get("profiles") or [{}])[0]).get("id") or ""
                    ),
                    "keychain_available": bool(runtime.passwords.list_profiles().get("keychain_supported")),
                },
            }
            return {
                "model_payload": {
                    "ok": False,
                    "error": "Profile is locked; unlock profile first to import staged .env keys.",
                    "ui_card_emitted": "profile_unlock_card",
                },
                "ui_cards": [card],
            }

        tok = create_confirm_gate(
            runtime,
            action_type="import_staged_env",
            summary=f"Import {len(keys_list)} key(s) from {entry.get('filename')} into active vault.enc",
            params={"staging_id": staging_id, "keys": keys_list},
        )
        card = {
            "id": f"card_{secrets.token_hex(4)}",
            "kind": "confirm_gate_card",
            "title": f"Import keys from {entry.get('filename')}",
            "subtitle": "Merges the staged KEY=VALUE pairs directly into encrypted vault.enc.",
            "confirm_token": tok,
            "data": {
                "action_type": "import_staged_env",
                "keys": keys_list,
                "masked_previews": previews,
            },
        }
        return {
            "model_payload": {
                "ok": True,
                "keys": keys_list,
                "confirm_required": True,
                "ui_card_emitted": "confirm_gate_card",
            },
            "ui_cards": [card],
        }

    prov = (provider_id or "gemini").strip().lower()
    if prov not in {"gemini", "anthropic", "openai", "mistral"}:
        prov = "gemini"

    card = {
        "id": f"card_{secrets.token_hex(4)}",
        "kind": "vault_secret_input_card",
        "title": f"Add {prov.title()} API key",
        "subtitle": "Key is masked locally and encrypted in vault.enc; it never enters chat logs or LLM context.",
        "data": {
            "mode": "cloud_provider",
            "provider_id": prov,
            "unlocked": unlocked,
        },
    }
    return {
        "model_payload": {
            "ok": True,
            "provider_id": prov,
            "ui_card_emitted": "vault_secret_input_card",
            "instruction": "A masked API key entry card is now displayed. Ask the user to paste their API key into the card input.",
        },
        "ui_cards": [card],
    }
