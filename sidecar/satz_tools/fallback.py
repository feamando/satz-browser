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

    low = q.lower()

    m_unlock_prof = re.search(
        r"\b(?:unlock|switch\s+to|open|load)\s+(?:my\s+)?profile(?:\s+(?:called|named))?\s+['\"]?([A-Za-z0-9_.\-]{2,40})['\"]?",
        q,
        re.IGNORECASE,
    )
    if m_unlock_prof:
        pname = m_unlock_prof.group(1)
        res = REGISTRY.dispatch(
            "settings_prepare_unlock_or_switch_profile",
            {"profile_id": pname},
            runtime=runtime,
            session=session,
        )
        cards = list(getattr(session, "ui_cards", []) or [])
        if not cards and res.get("error") and session is not None:
            session.fallback_reply_text = str(res["error"])
        return cards

    if re.search(r"\b(profiles?|vault)\b", low) and not re.search(r"\b(api\s*key|model|drive|mail|news)\b", low):
        prof_res = REGISTRY.dispatch("settings_list_profiles", {}, runtime=runtime, session=session)
        profiles = prof_res.get("profiles") or []
        active_id = str(prof_res.get("active_profile_id") or "")
        unlocked = bool(prof_res.get("unlocked"))
        if session is not None:
            if not profiles:
                REGISTRY.dispatch("settings_prepare_create_profile", {"profile_name": "default"}, runtime=runtime, session=session)
                return list(getattr(session, "ui_cards", []) or [])
            lines = [
                f"- **{p.get('name') or p.get('id')}** (`{p.get('id')}`)"
                + (" [unlocked]" if unlocked and p.get("id") == active_id else "")
                for p in profiles[:10]
            ]
            session.fallback_reply_text = (
                "Existing profiles:\n"
                + "\n".join(lines)
                + "\n\nSay **create profile <name>** or **unlock profile <name>** to open a card."
            )
        return list(getattr(session, "ui_cards", []) or [])

    if re.search(r"\b(model|models|gemma|planck|hertz|llm|hugging\s*face|local\s+model)\b", low):
        m_res = REGISTRY.dispatch("settings_get_model_roles", {}, runtime=runtime, session=session)
        roles = m_res.get("roles") or {}
        provs = [p for p in (m_res.get("cloud_providers") or []) if p.get("configured")]
        prov_txt = (
            ", ".join(f"{p.get('id')} ({len(p.get('models') or [])} models)" for p in provs)
            if provs
            else "none configured"
        )
        if session is not None:
            session.fallback_reply_text = (
                "Current model routing:\n"
                f"- Chat: `{roles.get('chat', 'planck3 (web)')}` (effective: `{roles.get('effective_chat', roles.get('chat', 'planck3 (web)'))}`)\n"
                f"- Web answers: `{roles.get('web_answer', 'planck3 (web)')}`\n"
                f"- Reader: `{roles.get('reader', 'planck (reader)')}`\n"
                f"- News analyzer: `{roles.get('news_analyzer', 'template')}`\n"
                f"- Cloud providers: {prov_txt}\n\n"
                "Open **Settings -> Models** to download/link Gemma or another local model, or say **add gemini api key** to configure cloud chat."
            )
        return list(getattr(session, "ui_cards", []) or [])

    if re.search(r"\b(drive|drives|google\s+drive|onedrive)\b", low):
        d_res = REGISTRY.dispatch("settings_get_summary", {"section": "drives"}, runtime=runtime, session=session)
        drv = d_res.get("drives") or {}
        if session is not None:
            session.fallback_reply_text = (
                "Cloud Drives status:\n"
                f"- Vault unlocked: {'yes' if drv.get('unlocked') else 'no'}\n"
                f"- Google Drive ready: {'yes' if drv.get('google_drive_ready') else 'no'}"
                + (f" ({drv.get('google_email')})" if drv.get("google_email") else "")
                + "\n"
                f"- OneDrive ready: {'yes' if drv.get('onedrive_signed_in') else 'no'}"
                + (f" ({drv.get('onedrive_email')})" if drv.get("onedrive_email") else "")
                + f"\n- Indexed files: {drv.get('indexed_count', 0)} / {drv.get('total_files', 0)}\n\n"
                "To connect Google Drive, say **connect google** or attach your `client_secret_*.json` file. For OneDrive, open the **Drives** tab in the left rail or **Settings -> Cloud Drives**."
            )
        return list(getattr(session, "ui_cards", []) or [])

    if re.search(r"\b(provider|providers|search\s+api)\b", low):
        p_res = REGISTRY.dispatch("settings_list_providers", {}, runtime=runtime, session=session)
        cats = p_res.get("categories") or []
        if session is not None:
            cat_lines = []
            for c in cats[:6]:
                ready_p = [str(p.get("display_name") or p.get("id")) for p in (c.get("providers") or []) if p.get("auth_ready")]
                total_p = len(c.get("providers") or [])
                cat_lines.append(
                    f"- **{c.get('label') or c.get('id')}**: {total_p} provider(s)"
                    + (f" (ready: {', '.join(ready_p)})" if ready_p else "")
                )
            session.fallback_reply_text = (
                "Action Providers:\n"
                + ("\n".join(cat_lines) if cat_lines else "- No provider categories found.")
                + "\n\nOpen **Settings -> Action Providers** to add credentials or infer a site provider."
            )
        return list(getattr(session, "ui_cards", []) or [])

    # Safe catch-all Settings summary + command guide so Planck-only Settings chat never returns empty output
    sum_res = REGISTRY.dispatch("settings_get_summary", {"section": "all"}, runtime=runtime, session=session)
    prof_info = sum_res.get("profiles") or {}
    models_info = (sum_res.get("models") or {}).get("roles") or {}
    mail_info = sum_res.get("mail") or {}
    oauth_info = sum_res.get("google_oauth") or {}
    if session is not None:
        session.fallback_reply_text = (
            "Satz Settings (Planck local mode):\n"
            f"- Profile unlocked: {'yes' if prof_info.get('unlocked') else 'no'}"
            + (f" (`{prof_info.get('active_profile_id')}`)" if prof_info.get("active_profile_id") else "")
            + "\n"
            f"- Chat / Web model: `{models_info.get('effective_chat') or models_info.get('chat') or 'planck3 (web)'}`\n"
            f"- Mail accounts: {len(mail_info.get('accounts') or [])}\n"
            f"- Google OAuth: {'signed in' if oauth_info.get('signed_in') else ('configured' if oauth_info.get('configured') else 'not configured')}\n\n"
            "Try commands like:\n"
            "- **create profile <name>** or **unlock profile <name>**\n"
            "- **add gemini api key** (or openai / anthropic / mistral)\n"
            "- **add mail account** or **connect google**\n"
            "- **check models**, **check drives**, or **translate interface to German**"
        )
    return list(getattr(session, "ui_cards", []) or [])


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
