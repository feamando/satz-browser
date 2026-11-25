"""App-wide UI localization & custom language pack tools for Settings Chat."""
from __future__ import annotations

import secrets
from typing import Any

from satz_i18n import normalize_lang_spec
from satz_tools.registry import satz_tool


@satz_tool(
    name="settings_get_language_status",
    domain="settings",
    mode="read",
    mcp_safe=True,
    description=(
        "Inspect the active app-wide interface language (shared across all profiles), "
        "saved language packs, missing/stale counts, and which default chat model handles translations. "
        "Optionally pass 'query' to find matching English UI string keys before overriding a label."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Optional text or key fragment to search UI catalog keys (e.g. 'Sync now').",
            },
        },
        "required": [],
    },
)
def settings_get_language_status(
    runtime: Any,
    session: Any = None,
    query: str = "",
) -> dict[str, Any]:
    status = runtime.i18n.get_status()
    out: dict[str, Any] = {
        "ok": True,
        "scope": "app_wide_across_profiles",
        "active_locale": status["active_locale"],
        "active_label": status["active_label"],
        "active_dir": status["active_dir"],
        "default_model": status["default_model"],
        "model_info": status["model_info"],
        "target": status["target"],
        "locales": status["locales"],
        "job": status["job"],
    }
    q = str(query or "").strip().lower()
    if q:
        cat = runtime.i18n.resolve_catalog()
        active_bundle = runtime.i18n.get_bundle(status["active_locale"]).get("entries") or {}
        matches = []
        for k, entry in cat.items():
            en_text = str(entry.get("text") or "")
            if q in k.lower() or q in en_text.lower():
                cur_ent = active_bundle.get(k) or {}
                matches.append(
                    {
                        "key": k,
                        "english": en_text,
                        "translation": cur_ent.get("text") or "",
                        "custom": bool(cur_ent.get("custom")),
                    }
                )
                if len(matches) >= 20:
                    break
        out["matching_keys"] = matches
    return {"model_payload": out}


@satz_tool(
    name="settings_switch_language",
    domain="settings",
    mode="write",
    mcp_safe=True,
    description=(
        "Switch the app-wide interface language immediately (for example 'en', 'de', 'fr', 'German', 'Arabic'). "
        "Works across all profiles. If a saved pack has missing or stale keys, background translation starts automatically."
    ),
    parameters={
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "description": "Target language name or BCP-47 tag (e.g. 'en', 'de', 'fr', 'Japanese', 'ar').",
            },
        },
        "required": ["language"],
    },
)
def settings_switch_language(
    runtime: Any,
    session: Any = None,
    language: str = "",
) -> dict[str, Any]:
    if not str(language or "").strip():
        return {"model_payload": {"ok": False, "error": "language is required"}}
    spec = normalize_lang_spec(language)
    runtime.i18n.set_active_locale(spec["lang"])
    status = runtime.i18n.get_status(lang=spec["lang"])
    target = status.get("target") or {}
    missing = int(target.get("missing") or 0)
    stale = int(target.get("stale") or 0)
    bg_started = False
    if spec["lang"] != "en" and (missing > 0 or stale > 0):
        bg_res = runtime.i18n.start_background_translation(
            spec["lang"],
            only_missing=True,
            activate=True,
        )
        bg_started = bool(bg_res.get("started") or bg_res.get("already_running"))

    m_info = status.get("model_info") or {}
    priv_short = "local only" if m_info.get("local_only") else str(m_info.get("host") or "cloud")
    card = {
        "id": f"card_{secrets.token_hex(4)}",
        "kind": "locale_translate_card",
        "title": f"Translate interface to {target.get('label') or spec['label']}",
        "title_key": "i18n.card_title",
        "title_vars": {"label": str(target.get("label") or spec["label"])},
        "subtitle": (
            f"{missing + stale} missing keys · model: {status['default_model']} · {priv_short}"
        ),
        "subtitle_key": "i18n.card_sub",
        "subtitle_vars": {
            "missing": missing + stale,
            "model": str(status["default_model"]),
            "privacy": priv_short,
        },
        "data": {
            "lang": spec["lang"],
            "label": str(target.get("label") or spec["label"]),
            "dir": spec["dir"],
            "model": str(status["default_model"]),
            "privacy": str(m_info.get("disclosure") or ""),
            "total": int(target.get("total") or 0),
            "translated": int(target.get("translated") or 0),
            "missing": missing + stale,
            "background_started": bg_started,
        },
    }
    return {
        "model_payload": {
            "ok": True,
            "active_locale": spec["lang"],
            "active_label": str(target.get("label") or spec["label"]),
            "active_dir": spec["dir"],
            "translated": int(target.get("translated") or 0),
            "missing": missing,
            "stale": stale,
            "background_sync_started": bg_started,
            "side_effects": ["i18n"],
            "ui_card_emitted": "locale_translate_card",
        },
        "ui_cards": [card],
    }


@satz_tool(
    name="settings_prepare_language_translation",
    domain="settings",
    mode="write",
    mcp_safe=True,
    description=(
        "Prepare an interactive card to translate all Satz UI strings into any language using the user's "
        "selected default chat model (shows privacy disclosure and live progress)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "description": "Target language name or code (e.g. 'Deutsch', 'French', 'ja', 'Arabic').",
            },
            "force": {
                "type": "boolean",
                "description": "Set true to re-translate already translated non-custom strings.",
            },
        },
        "required": ["language"],
    },
)
def settings_prepare_language_translation(
    runtime: Any,
    session: Any = None,
    language: str = "",
    force: bool = False,
) -> dict[str, Any]:
    if not str(language or "").strip():
        return {"model_payload": {"ok": False, "error": "language is required"}}
    spec = normalize_lang_spec(language)
    status = runtime.i18n.get_status(lang=spec["lang"])
    target = status.get("target") or {}
    m_info = status.get("model_info") or {}
    total = int(target.get("total") or 0)
    translated = int(target.get("translated") or 0)
    missing = total if force else int(target.get("missing") or 0) + int(target.get("stale") or 0)
    priv_short = "local only" if m_info.get("local_only") else str(m_info.get("host") or "cloud")

    card = {
        "id": f"card_{secrets.token_hex(4)}",
        "kind": "locale_translate_card",
        "title": f"Translate interface to {spec['label']}",
        "title_key": "i18n.card_title",
        "title_vars": {"label": spec["label"]},
        "subtitle": f"{missing} missing keys · model: {status['default_model']} · {priv_short}",
        "subtitle_key": "i18n.card_sub",
        "subtitle_vars": {
            "missing": missing,
            "model": str(status["default_model"]),
            "privacy": priv_short,
        },
        "data": {
            "lang": spec["lang"],
            "label": spec["label"],
            "dir": spec["dir"],
            "model": str(status["default_model"]),
            "privacy": str(m_info.get("disclosure") or ""),
            "total": total,
            "translated": translated,
            "missing": missing,
            "force": bool(force),
        },
    }
    return {
        "model_payload": {
            "ok": True,
            "lang": spec["lang"],
            "label": spec["label"],
            "dir": spec["dir"],
            "default_model": str(status["default_model"]),
            "privacy": str(m_info.get("disclosure") or ""),
            "total": total,
            "translated": translated,
            "missing": missing,
            "ui_card_emitted": "locale_translate_card",
            "instruction": (
                "A language translation card is displayed with model privacy info and the Translate & apply button."
            ),
        },
        "ui_cards": [card],
    }


@satz_tool(
    name="settings_set_ui_translation_override",
    domain="settings",
    mode="write",
    mcp_safe=True,
    description=(
        "Set or reset a custom user translation for a specific UI key in a non-English pack. "
        "Custom overrides are marked protected and preserved during future background syncs."
    ),
    parameters={
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "description": "Target non-English language code or name (e.g. 'de', 'fr').",
            },
            "key": {
                "type": "string",
                "description": "Exact UI catalog key (e.g. 'mail.sync_now'). Use settings_get_language_status(query=...) first if unsure.",
            },
            "translation": {
                "type": "string",
                "description": "Custom translated string matching all {placeholders}. Omit when reset=true.",
            },
            "reset": {
                "type": "boolean",
                "description": "Set true to clear custom override and revert to model translation.",
            },
        },
        "required": ["language", "key"],
    },
)
def settings_set_ui_translation_override(
    runtime: Any,
    session: Any = None,
    language: str = "",
    key: str = "",
    translation: str = "",
    reset: bool = False,
) -> dict[str, Any]:
    if not str(language or "").strip() or not str(key or "").strip():
        return {"model_payload": {"ok": False, "error": "language and key are required"}}
    res = runtime.i18n.override_entry(
        language,
        key,
        translation if not reset else None,
        reset=bool(reset),
    )
    if res.get("ok"):
        res["side_effects"] = ["i18n"]
    return {"model_payload": res}
