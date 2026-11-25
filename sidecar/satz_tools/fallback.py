"""Deterministic safety fallback for Settings turns if a local/small model emits zero tool calls."""
from __future__ import annotations

import re
import secrets
from typing import Any

from satz_tools.registry import REGISTRY


def maybe_fallback_settings_cards(
    runtime: Any,
    session: Any,
    *,
    user_msg: str,
    staged_files: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    If a Settings turn produced zero tool calls and zero ui_cards, inspect explicit
    staged_files or clear onboarding phrasing and invoke the matching declarative tool.
    Returns list of newly emitted ui_cards (empty if none matched).
    """
    if getattr(session, "tool_trace", None) or getattr(session, "ui_cards", None):
        return []

    staged = list(staged_files or [])
    if staged:
        last_sf = staged[-1] if isinstance(staged[-1], dict) else {}
        sid = str(last_sf.get("staging_id") or "").strip()
        kind = str(last_sf.get("detected_kind") or "").strip()
        if sid and kind == "google_client_secret":
            REGISTRY.dispatch(
                "settings_configure_google_oauth",
                {"staging_id": sid},
                runtime=runtime,
                session=session,
            )
            return list(getattr(session, "ui_cards", []) or [])
        if sid and kind == "env_secrets":
            REGISTRY.dispatch(
                "settings_stage_api_key_or_env",
                {"staging_id": sid},
                runtime=runtime,
                session=session,
            )
            return list(getattr(session, "ui_cards", []) or [])

    q = (user_msg or "").strip()
    if not q:
        return []

    m_create_prof = re.search(
        r"\b(?:create|new|make|set\s*up)\s+(?:a\s+)?(?:[a-z]+\s+){0,2}profile(?:\s+(?:called|named))?\s+['\"]?([A-Za-z0-9_.\-]{2,40})['\"]?",
        q,
        re.IGNORECASE,
    )
    if m_create_prof:
        pname = m_create_prof.group(1)
        REGISTRY.dispatch(
            "settings_prepare_create_profile",
            {"profile_name": pname},
            runtime=runtime,
            session=session,
        )
        return list(getattr(session, "ui_cards", []) or [])

    if re.search(r"\b(create|new)\s+(?:a\s+)?profile\b", q, re.IGNORECASE):
        REGISTRY.dispatch(
            "settings_prepare_create_profile",
            {"profile_name": "default"},
            runtime=runtime,
            session=session,
        )
        return list(getattr(session, "ui_cards", []) or [])

    if re.search(r"\b(google|oauth|client[\s_-]*secret|gmail)\b", q, re.IGNORECASE) and re.search(
        r"\b(connect|add|link|sign\s*in|setup|set\s*up|configure|auth|work\s*email)\b",
        q,
        re.IGNORECASE,
    ):
        g_st = runtime.google_auth.get_status() if hasattr(runtime, "google_auth") else {}
        if g_st.get("configured") and getattr(runtime.passwords, "unlocked", False):
            REGISTRY.dispatch("settings_start_google_oauth", {}, runtime=runtime, session=session)
        else:
            session.ui_cards.append(
                {
                    "id": f"card_{secrets.token_hex(4)}",
                    "kind": "google_oauth_connect_card",
                    "title": "Connect a Google account",
                    "subtitle": (
                        "Attach or drop your Google Cloud client_secret_*.json file into the composer "
                        "(encrypted locally in vault.enc) to enable Google browser-tab sign-in."
                    ),
                    "data": {
                        "configured": bool(g_st.get("configured")),
                        "signed_in": bool(g_st.get("signed_in")),
                        "email": g_st.get("email") or "",
                        "masked_client_id": g_st.get("masked_client_id") or "",
                        "unlocked": bool(getattr(runtime.passwords, "unlocked", False)),
                    },
                }
            )
        return list(getattr(session, "ui_cards", []) or [])

    if re.search(r"\b(api\s*key|gemini|anthropic|claude|openai|mistral)\b", q, re.IGNORECASE) and re.search(
        r"\b(add|set|configure|update|save|enter)\b",
        q,
        re.IGNORECASE,
    ):
        prov = "gemini"
        low = q.lower()
        if "anthropic" in low or "claude" in low:
            prov = "anthropic"
        elif "openai" in low or "gpt" in low:
            prov = "openai"
        elif "mistral" in low:
            prov = "mistral"
        REGISTRY.dispatch(
            "settings_stage_api_key_or_env",
            {"provider_id": prov},
            runtime=runtime,
            session=session,
        )
        return list(getattr(session, "ui_cards", []) or [])

    if re.search(r"\b(mail|email|imap|pop3)\s+account\b", q, re.IGNORECASE) and re.search(
        r"\b(add|set\s*up|setup|configure|connect)\b",
        q,
        re.IGNORECASE,
    ):
        REGISTRY.dispatch("settings_prepare_add_mail_account", {}, runtime=runtime, session=session)
        return list(getattr(session, "ui_cards", []) or [])

    m_lang = re.search(
        r"\b(?:translate|switch|set|change)\s+(?:the\s+)?(?:ui|interface|app|browser)?\s*language\s+(?:to|into)\s+([A-Za-z0-9_\-\s]{2,30})",
        q,
        re.IGNORECASE,
    ) or re.search(
        r"\btranslate\s+(?:the\s+)?(?:ui|interface|app|browser)\s+(?:to|into)\s+([A-Za-z0-9_\-\s]{2,30})",
        q,
        re.IGNORECASE,
    )
    if m_lang:
        raw_target = re.split(r"\b(?:using|with|via|please|now)\b", m_lang.group(1), maxsplit=1)[0].strip(" .!?\"'")
        if raw_target:
            if raw_target.lower() in ("en", "english"):
                REGISTRY.dispatch("settings_switch_language", {"language": "en"}, runtime=runtime, session=session)
            else:
                REGISTRY.dispatch("settings_prepare_language_translation", {"language": raw_target}, runtime=runtime, session=session)
            return list(getattr(session, "ui_cards", []) or [])

    return []


def maybe_fallback_news_settings_cards(
    runtime: Any,
    session: Any,
    *,
    user_msg: str,
) -> list[dict[str, Any]]:
    """
    Deterministic safety fallback for News Settings turns if a local/small model emits zero tool calls.
    Handles status/list requests, ambiguous source/topic suggestion requests, trust adjustment,
    and explicit feed or topic additions.
    """
    if getattr(session, "tool_trace", None) or getattr(session, "ui_cards", None):
        return []

    q = (user_msg or "").strip()
    if not q:
        return []
    low = q.lower()

    # 1. Trust adjustment / inspection on a domain (e.g. "trust bbc.com 9", "set trust on rt.com to 2", "reset trust tagesschau")
    m_trust = re.search(
        r"\b(?:trust|score|weight)\b.*?\b([a-z0-9.-]+\.[a-z]{2,}|tagesschau|spiegel|euronews|meduza|lemonde|reuters|bbc|guardian|dw|npr|arxiv)\b(?:\s*(?:to|at|=|:)?\s*(\d+(?:\.\d+)?))?",
        q,
        re.IGNORECASE,
    )
    if m_trust:
        dom = m_trust.group(1)
        score_s = m_trust.group(2)
        reset_flag = bool(re.search(r"\b(reset|clear|default|remove\s+override)\b", low))
        REGISTRY.dispatch(
            "news_settings_set_source_trust",
            {
                "domain": dom,
                "personal_score": float(score_s) if score_s is not None and not reset_flag else None,
                "reset": reset_flag,
            },
            runtime=runtime,
            session=session,
        )
        return list(getattr(session, "ui_cards", []) or [])

    # 2. Ambiguous or explicit topic suggestions (check before generic "news" keyword so "suggest news topics" hits topics)
    if re.search(r"\b(suggest|recommend|ideas|good|interesting|what|which)\b", low) and re.search(
        r"\b(topic|topics|subject|subjects|interest|interests|follow|track|beat|beats)\b",
        low,
    ) and not re.search(r"\b(source|sources|feed|feeds|outlet|outlets|paper|papers|rss)\b", low):
        REGISTRY.dispatch("news_settings_suggest_topics", {"interest_hint": q}, runtime=runtime, session=session)
        return list(getattr(session, "ui_cards", []) or [])

    # 3. Ambiguous or explicit source suggestions / list (e.g. "suggest sources", "good German outlets", "show my sources")
    if re.search(r"\b(suggest|recommend|ideas|good|list|show|what|which|find)\b", low) and re.search(
        r"\b(source|sources|feed|feeds|outlet|outlets|paper|papers|rss|news)\b",
        low,
    ):
        REGISTRY.dispatch("news_settings_suggest_sources", {"query": q}, runtime=runtime, session=session)
        return list(getattr(session, "ui_cards", []) or [])

    # 4. Explicit feed URL addition
    m_url = re.search(r"(https?://[^\s]+)", q, re.IGNORECASE)
    if m_url:
        REGISTRY.dispatch(
            "news_settings_manage_source_feed",
            {"action": "add", "feed_url": m_url.group(1)},
            runtime=runtime,
            session=session,
        )
        return list(getattr(session, "ui_cards", []) or [])

    # 5. Summary / status inspection
    if re.search(r"\b(summary|status|overview|current|show\s+settings|my\s+(?:topics|sources))\b", low):
        REGISTRY.dispatch("news_settings_get_summary", {"focus": "all"}, runtime=runtime, session=session)
        return list(getattr(session, "ui_cards", []) or [])

    # 6. Fallback for short general prompts when empty/onboarding: suggest both topics & sources
    REGISTRY.dispatch("news_settings_suggest_topics", {"interest_hint": q}, runtime=runtime, session=session)
    return list(getattr(session, "ui_cards", []) or [])
