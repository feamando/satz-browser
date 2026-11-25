"""Declarative tools for Satz News Settings (Topics, Sources/Feeds, Personal Trust)."""
from __future__ import annotations

import json
import re
import secrets
from typing import Any

from satz_brain import slugify
from satz_tools.registry import satz_tool
from satz_tools.settings_staging import create_confirm_gate


_TOPIC_CATALOG: list[dict[str, Any]] = [
    {
        "name": "European Union & Policy",
        "keywords": ["eu", "brussels", "commission", "european parliament", "regulation"],
        "tags": ["europe", "eu", "policy", "politics", "brussels", "world", "regulation", "general"],
    },
    {
        "name": "AI & Foundation Models",
        "keywords": ["ai", "llm", "artificial intelligence", "openai", "anthropic", "gemma"],
        "tags": ["tech", "technology", "ai", "software", "science", "innovation", "general"],
    },
    {
        "name": "Semiconductors & Supply Chains",
        "keywords": ["semiconductor", "chip", "nvidia", "tsmc", "asml", "fab"],
        "tags": ["tech", "technology", "chips", "hardware", "economy", "business"],
    },
    {
        "name": "Climate & Energy Transition",
        "keywords": ["climate", "grid", "renewable", "solar", "wind", "emissions", "energy"],
        "tags": ["climate", "energy", "environment", "europe", "science", "green", "general"],
    },
    {
        "name": "Global Economy & Markets",
        "keywords": ["inflation", "ecb", "fed", "tariffs", "trade", "markets", "gdp"],
        "tags": ["economy", "finance", "markets", "business", "trade", "money", "general"],
    },
    {
        "name": "Germany Politics & Economy",
        "keywords": ["germany", "berlin", "bundestag", "bundesbank", "dax", "wirtschaft"],
        "tags": ["germany", "german", "deutschland", "europe", "politics", "economy"],
    },
    {
        "name": "Security & Geopolitics",
        "keywords": ["nato", "ukraine", "defense", "sanctions", "security", "diplomacy"],
        "tags": ["geopolitics", "security", "defense", "world", "ukraine", "war", "international"],
    },
    {
        "name": "Science & Biotech",
        "keywords": ["research", "study", "biotech", "medicine", "space", "physics"],
        "tags": ["science", "health", "biotech", "medicine", "space", "research"],
    },
]

_DOMAIN_ALIASES: dict[str, str] = {
    "tagesschau": "tagesschau.de",
    "ard": "tagesschau.de",
    "spiegel": "spiegel.de",
    "der spiegel": "spiegel.de",
    "dw": "dw.com",
    "deutsche welle": "dw.com",
    "euronews": "euronews.com",
    "bbc": "bbc.com",
    "guardian": "theguardian.com",
    "the guardian": "theguardian.com",
    "le monde": "lemonde.fr",
    "lemonde": "lemonde.fr",
    "meduza": "meduza.io",
    "kyiv independent": "kyivindependent.com",
    "npr": "npr.org",
    "abc": "abc.net.au",
    "cbc": "cbc.ca",
    "arxiv": "arxiv.org",
    "reuters": "reuters.com",
    "ap": "apnews.com",
    "associated press": "apnews.com",
    "rt": "rt.com",
}


def _collect_news_settings_state(runtime: Any) -> dict[str, Any]:
    topics = (runtime.news.list_topics().get("topics") or []) if getattr(runtime, "news", None) else []
    src_data = runtime.news.list_sources() if getattr(runtime, "news", None) else {"sources": [], "categories": []}
    all_sources = src_data.get("sources") or []
    overlay_feeds = list((getattr(runtime.news, "overlay", None) or {}).get("starter_feeds") or [])

    enabled_feeds: list[dict[str, Any]] = []
    feed_by_domain: dict[str, dict[str, Any]] = {}
    for s in all_sources:
        dom = str(s.get("domain") or "")
        for f in s.get("feeds") or []:
            entry = {**f, "domain": dom, "system": s.get("system"), "effective": s.get("effective"), "band": s.get("band"), "category": s.get("category")}
            feed_by_domain.setdefault(dom, entry)
            if f.get("enabled"):
                enabled_feeds.append(entry)

    available_starter: list[dict[str, Any]] = []
    for sf in overlay_feeds:
        dom = str(sf.get("domain") or "").lower().removeprefix("www.")
        trec = runtime.store.trust(dom, personal=True)
        existing_f = feed_by_domain.get(dom)
        available_starter.append(
            {
                "feed_id": str(sf.get("feed_id") or ""),
                "domain": dom,
                "title": str(sf.get("title") or dom),
                "feed_url": str(sf.get("feed_url") or ""),
                "language": str(sf.get("language") or "en"),
                "category": str(trec.get("category") or sf.get("category") or "unscored"),
                "system": round(float(trec.get("system") or 5.0), 2),
                "effective": round(float(trec.get("effective") or 5.0), 2),
                "band": str(trec.get("band") or "low"),
                "enabled": bool(existing_f and existing_f.get("enabled")),
            }
        )

    personal_overrides = [
        {
            "domain": s["domain"],
            "category": s["category"],
            "system": s["system"],
            "personal": s["personal"],
            "effective": s["effective"],
            "band": s["band"],
            "conflict": bool(s.get("conflict")),
        }
        for s in all_sources
        if s.get("personal") is not None
    ]

    return {
        "topics": topics,
        "topics_count": len(topics),
        "active_topics_count": sum(1 for t in topics if not t.get("suppressed")),
        "enabled_feeds": enabled_feeds,
        "enabled_feeds_count": len(enabled_feeds),
        "available_starter_feeds": available_starter,
        "personal_overrides": personal_overrides,
        "personal_overrides_count": len(personal_overrides),
        "all_sources": all_sources,
        "categories": src_data.get("categories") or [],
        "last_sync_at": float(src_data.get("last_sync_at") or 0.0),
        "sync_interval_seconds": float(src_data.get("sync_interval_seconds") or 3600.0),
    }


def _resolve_domain_alias(runtime: Any, raw_domain: str) -> str:
    clean = (raw_domain or "").strip().lower()
    clean = re.sub(r"^https?://", "", clean).split("/", 1)[0].removeprefix("www.")
    if clean in _DOMAIN_ALIASES:
        return _DOMAIN_ALIASES[clean]
    for alias, dom in _DOMAIN_ALIASES.items():
        if clean == alias or (len(clean) >= 3 and alias in clean):
            return dom
    if "." in clean:
        return clean
    if getattr(runtime, "news", None) is not None and clean:
        all_s = runtime.news.list_sources(query=clean).get("sources") or []
        if all_s:
            return str(all_s[0]["domain"])
    return clean


def _build_topic_suggestions(runtime: Any, hint: str = "", limit: int = 8) -> list[dict[str, Any]]:
    state_snap = _collect_news_settings_state(runtime)
    existing_names = {str(t.get("name") or "").strip().lower() for t in state_snap["topics"]}
    hint_low = (hint or "").strip().lower()
    hint_terms = [w for w in re.findall(r"[a-z0-9\u00c0-\u017f]{2,}", hint_low) if w not in {"the", "and", "for", "news", "some", "good", "topics", "about", "what", "suggest"}]

    candidates: list[tuple[int, dict[str, Any]]] = []
    seen_slugs: set[str] = set()

    def _add_cand(score: int, name: str, keywords: list[str], reason: str) -> None:
        clean_n = str(name or "").strip()[:80]
        if not clean_n or clean_n.lower() in existing_names:
            return
        sl = slugify(clean_n)
        if sl in seen_slugs:
            return
        seen_slugs.add(sl)
        candidates.append(
            (
                score,
                {
                    "name": clean_n,
                    "keywords": [str(k).strip() for k in keywords if str(k).strip()][:6],
                    "reason": reason,
                },
            )
        )

    # 1. User Brain interests (topics/stories/orgs, scrubbed for zero PII leakage)
    if getattr(runtime, "brain", None) is not None and not runtime.brain.locked:
        try:
            ents = runtime.brain.search_entities(hint_low if hint_terms else "", limit=10)
            for ent in ents:
                etype = str(ent.get("entity_type") or "").lower()
                if etype not in {"topic", "story", "org", "product"}:
                    continue
                raw_n = str(ent.get("name") or "").strip()
                clean_n = runtime.brain.scrub_pii_for_external_query(raw_n) or ""
                if not clean_n or "@" in clean_n or "[" in clean_n:
                    continue
                _add_cand(95, clean_n, re.findall(r"[a-z0-9]{3,}", clean_n.lower()), f"From your Brain ({etype})")
        except Exception:
            pass

    # 2. Curated topic taxonomy matching hint (or broad diverse starters if hint is vague/empty)
    for item in _TOPIC_CATALOG:
        blob = " ".join([item["name"], *item["keywords"], *item["tags"]]).lower()
        hits = sum(1 for tok in hint_terms if tok in blob)
        if hint_terms and hits == 0:
            continue
        score = 80 + hits * 20
        reason = "Matches your interest" if hint_terms else "Popular news beat"
        _add_cand(score, item["name"], item["keywords"], reason)

    # 3. Current top clustered stories (only if hint matches or if still under limit)
    if getattr(runtime, "store", None) is not None:
        try:
            rows = runtime.store.db.execute(
                """
                SELECT headline, independent_families, confidence10
                FROM satz_news_clusters
                WHERE is_hidden = 0 AND LENGTH(TRIM(headline)) > 0
                ORDER BY story_rank DESC, updated_at DESC
                LIMIT 12
                """
            ).fetchall()
            for r in rows:
                hl = str(r["headline"] or "").strip()
                if hint_terms and not any(tok in hl.lower() for tok in hint_terms):
                    continue
                kws = [w for w in re.findall(r"[a-zA-Z0-9\u00c0-\u017f]{4,}", hl.lower()) if w not in {"with", "from", "that", "this", "over", "after", "says", "into"}]
                if len(hl) > 48:
                    hl = hl[:48].rsplit(" ", 1)[0].strip()
                _add_cand(
                    55 + int(r["independent_families"] or 1) * 5,
                    hl,
                    kws[:4],
                    f"Trending across {int(r['independent_families'] or 1)} source(s)",
                )
        except Exception:
            pass

    # If narrow hint yielded nothing, fall back cleanly to diverse curated suggestions
    if not candidates:
        for item in _TOPIC_CATALOG[:6]:
            _add_cand(50, item["name"], item["keywords"], "Broad starter topic")

    candidates.sort(key=lambda x: -x[0])
    return [c[1] for c in candidates[:limit]]


def _build_source_suggestions(
    runtime: Any,
    query: str = "",
    region_or_topic: str = "",
    language: str = "",
    limit: int = 10,
) -> list[dict[str, Any]]:
    snap = _collect_news_settings_state(runtime)
    combined_q = " ".join(x for x in (query, region_or_topic, language) if x).strip().lower()
    tokens = [
        w
        for w in re.findall(r"[a-z0-9\u00c0-\u017f]{2,}", combined_q)
        if w not in {"good", "best", "news", "source", "sources", "add", "some", "the", "and", "for", "with", "suggest", "show"}
    ]
    lang_filter = (language or "").strip().lower()[:2]

    starter_by_dom = {f["domain"]: f for f in snap["available_starter_feeds"]}
    results: list[tuple[float, dict[str, Any]]] = []
    seen_doms: set[str] = set()

    # Curated starter feeds first (1-click RSS subscribe)
    for dom, sf in starter_by_dom.items():
        hay = f"{dom} {sf['title']} {sf['category']} {sf['language']}".lower()
        hits = sum(1 for tok in tokens if tok in hay)
        if tokens and hits == 0:
            # Map common language/region keywords
            if any(k in tokens for k in ("german", "germany", "deutsch")) and sf["language"] == "de":
                hits = 2
            elif any(k in tokens for k in ("europe", "european", "eu")) and (
                sf["category"] in ("news_eu", "independent") or sf["language"] in ("de", "fr")
            ):
                hits = 1
            elif any(k in tokens for k in ("science", "ai", "tech", "research")) and dom == "arxiv.org":
                hits = 2
        if lang_filter and sf["language"].lower() != lang_filter:
            continue
        score = float(sf["effective"]) + hits * 4.0 + (2.0 if not sf["enabled"] else -1.0)
        seen_doms.add(dom)
        results.append(
            (
                score,
                {
                    "domain": dom,
                    "title": sf["title"],
                    "feed_id": sf["feed_id"],
                    "feed_url": sf["feed_url"],
                    "language": sf["language"],
                    "category": sf["category"],
                    "system": sf["system"],
                    "effective": sf["effective"],
                    "band": sf["band"],
                    "enabled": sf["enabled"],
                    "has_starter_rss": True,
                },
            )
        )

    # High-trust registry outlets matching query tokens (or top trustworthy references if ambiguous)
    for s in snap["all_sources"]:
        dom = str(s.get("domain") or "")
        if not dom or dom in seen_doms:
            continue
        if float(s.get("effective") or 0.0) < 6.5:
            continue
        hay = f"{dom} {s.get('category') or ''} {s.get('why') or ''}".lower()
        hits = sum(1 for tok in tokens if tok in hay)
        if tokens and hits == 0:
            continue
        if not tokens and len(results) >= limit:
            continue
        seen_doms.add(dom)
        has_feed = bool(s.get("feeds"))
        f0 = (s.get("feeds") or [{}])[0]
        results.append(
            (
                float(s["effective"]) + hits * 3.0,
                {
                    "domain": dom,
                    "title": dom,
                    "feed_id": str(f0.get("feed_id") or ""),
                    "feed_url": str(f0.get("feed_url") or ""),
                    "language": str(f0.get("language") or ""),
                    "category": str(s.get("category") or ""),
                    "system": s["system"],
                    "effective": s["effective"],
                    "band": s["band"],
                    "enabled": bool(f0.get("enabled")),
                    "has_starter_rss": has_feed,
                },
            )
        )

    results.sort(key=lambda x: -x[0])
    # Fallback to all starter feeds if specific filter yielded none
    if not results:
        return list(starter_by_dom.values())[:limit]
    return [r[1] for r in results[:limit]]


def build_news_settings_onboarding_payload(runtime: Any) -> dict[str, Any]:
    """Builds onboarding prompt + inline suggestion UI cards when topics or enabled sources are empty."""
    snap = _collect_news_settings_state(runtime)
    no_topics = snap["topics_count"] == 0
    no_feeds = snap["enabled_feeds_count"] == 0
    needs = bool(no_topics or no_feeds)
    topic_suggs = _build_topic_suggestions(runtime, "", limit=6)
    source_suggs = _build_source_suggestions(runtime, "", limit=8)

    cards: list[dict[str, Any]] = []
    if no_topics:
        cards.append(
            {
                "id": f"card_{secrets.token_hex(4)}",
                "kind": "news_topic_suggestions_card",
                "title": "Pick topics of interest to follow",
                "subtitle": "Click topics below to start tracking them, or type your own subjects in chat.",
                "data": {"suggestions": topic_suggs},
            }
        )
    if no_feeds:
        cards.append(
            {
                "id": f"card_{secrets.token_hex(4)}",
                "kind": "news_source_suggestions_card",
                "title": "Choose starter news sources",
                "subtitle": "All source weights keep a strict 30% cap on personal overrides (0.7 * system + 0.3 * personal).",
                "data": {"sources": source_suggs},
            }
        )

    if no_topics and no_feeds:
        prompt_text = (
            "Welcome to **News Settings**. You do not have any tracked topics or active news feeds yet.\n\n"
            "What topics and outlets are you interested in? Reply with subjects (for example *European energy policy, AI chips, German economy*) "
            "or countries/outlets, or click any suggestion card below."
        )
    elif no_topics:
        prompt_text = (
            f"You have **{snap['enabled_feeds_count']} active news feed(s)** configured, but **no tracked topics** yet.\n\n"
            "What topics of interest would you like Satz News to follow? Tell me a few subjects in chat or click suggestions below."
        )
    elif no_feeds:
        prompt_text = (
            f"You have **{snap['active_topics_count']} tracked topic(s)**, but **no enabled RSS sources** yet.\n\n"
            "Tell me which outlets, countries, or beats you trust, or enable starter feeds below."
        )
    else:
        prompt_text = ""

    return {
        "ok": True,
        "needs_onboarding": needs,
        "topics_count": snap["topics_count"],
        "enabled_feeds_count": snap["enabled_feeds_count"],
        "personal_overrides_count": snap["personal_overrides_count"],
        "prompt_text": prompt_text,
        "ui_cards": cards,
        "topic_suggestions": topic_suggs,
        "source_suggestions": source_suggs,
    }


@satz_tool(
    name="news_settings_get_summary",
    domain="news_settings",
    mode="read",
    mcp_safe=True,
    description=(
        "Inspect current Satz News configuration: tracked topics, active and starter RSS sources, "
        "personal trust overrides (with 30% cap rule), and whether onboarding is needed."
    ),
    parameters={
        "type": "object",
        "properties": {
            "focus": {
                "type": "string",
                "enum": ["all", "topics", "sources", "feeds"],
                "description": "Which part of News Settings to inspect.",
            }
        },
        "required": [],
    },
)
def news_settings_get_summary(
    runtime: Any,
    session: Any = None,
    focus: str = "all",
) -> dict[str, Any]:
    snap = _collect_news_settings_state(runtime)
    card = {
        "id": f"card_{secrets.token_hex(4)}",
        "kind": "news_settings_status_card",
        "title": "News settings summary",
        "subtitle": (
            f"{snap['active_topics_count']} tracked topic(s) · {snap['enabled_feeds_count']} active feed(s) · "
            f"{snap['personal_overrides_count']} personal trust override(s)"
        ),
        "data": {
            "topics": snap["topics"][:15],
            "enabled_feeds": snap["enabled_feeds"][:15],
            "personal_overrides": snap["personal_overrides"][:15],
        },
    }
    payload = {
        "ok": True,
        "focus": focus,
        "needs_onboarding": snap["topics_count"] == 0 or snap["enabled_feeds_count"] == 0,
        "topics_count": snap["topics_count"],
        "topics": snap["topics"],
        "enabled_feeds_count": snap["enabled_feeds_count"],
        "enabled_feeds": snap["enabled_feeds"],
        "personal_overrides": snap["personal_overrides"],
        "trust_rule": "effective = 0.7 * system + 0.3 * personal (hard 30% personal cap; scale 0..10)",
    }
    return {"model_payload": payload, "ui_cards": [card]}


@satz_tool(
    name="news_settings_list_sources",
    domain="news_settings",
    mode="read",
    mcp_safe=True,
    description=(
        "List and filter sources in the Satz News Trust Registry & RSS catalog by query, category, "
        "trust band (high/good/low/sceptical/unscored), RSS availability, or personal trust overrides."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Optional domain, keyword, or category substring."},
            "category": {"type": "string", "description": "Optional category id (e.g. independent, news_eu, news_us_uk, science)."},
            "band": {"type": "string", "enum": ["", "high", "good", "low", "sceptical", "unscored"]},
            "with_rss_only": {"type": "boolean"},
            "personal_only": {"type": "boolean", "description": "Return only domains with user personal trust overrides."},
        },
        "required": [],
    },
)
def news_settings_list_sources(
    runtime: Any,
    session: Any = None,
    query: str = "",
    category: str = "",
    band: str = "",
    with_rss_only: bool = False,
    personal_only: bool = False,
) -> dict[str, Any]:
    res = runtime.news.list_sources(
        query=query,
        category=category,
        band_filter=band,
        with_rss_only=bool(with_rss_only),
    )
    srcs = res.get("sources") or []
    if personal_only:
        srcs = [s for s in srcs if s.get("personal") is not None]
    shown = srcs[:20]
    card = {
        "id": f"card_{secrets.token_hex(4)}",
        "kind": "news_source_suggestions_card",
        "title": f"News sources ({len(srcs)} matched)",
        "subtitle": "Click + Enable/Pause to manage RSS feeds or adjust personal trust (capped at 30%).",
        "data": {
            "sources": [
                {
                    "domain": s["domain"],
                    "title": (s["feeds"][0]["title"] if s.get("feeds") else s["domain"]),
                    "feed_id": (s["feeds"][0]["feed_id"] if s.get("feeds") else ""),
                    "feed_url": (s["feeds"][0]["feed_url"] if s.get("feeds") else ""),
                    "language": (s["feeds"][0]["language"] if s.get("feeds") else ""),
                    "category": s["category"],
                    "system": s["system"],
                    "personal": s["personal"],
                    "effective": s["effective"],
                    "band": s["band"],
                    "enabled": bool(s.get("feeds") and any(f.get("enabled") for f in s["feeds"])),
                    "has_starter_rss": bool(s.get("feeds")),
                }
                for s in shown[:10]
            ]
        },
    }
    return {
        "model_payload": {
            "ok": True,
            "total": len(srcs),
            "as_of": res.get("as_of"),
            "sources": [
                {
                    "domain": s["domain"],
                    "category": s["category"],
                    "system": s["system"],
                    "personal": s["personal"],
                    "effective": s["effective"],
                    "band": s["band"],
                    "conflict": bool(s.get("conflict")),
                    "feeds": [{"feed_id": f["feed_id"], "enabled": f["enabled"], "language": f["language"]} for f in (s.get("feeds") or [])],
                }
                for s in shown
            ],
        },
        "ui_cards": [card],
    }


@satz_tool(
    name="news_settings_suggest_sources",
    domain="news_settings",
    mode="read",
    mcp_safe=True,
    description=(
        "Handle broad or ambiguous requests for news sources (e.g. 'good European sources', 'German news', "
        "'science outlets', 'something trustworthy') by returning curated RSS suggestions & trusted registry domains with an interactive card."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "User request or interest description."},
            "region_or_topic": {"type": "string", "description": "Optional region, country, or beat (e.g. europe, germany, tech, science)."},
            "language": {"type": "string", "description": "Optional 2-letter language preference (en, de, fr)."},
        },
        "required": [],
    },
)
def news_settings_suggest_sources(
    runtime: Any,
    session: Any = None,
    query: str = "",
    region_or_topic: str = "",
    language: str = "",
) -> dict[str, Any]:
    suggs = _build_source_suggestions(
        runtime,
        query=query,
        region_or_topic=region_or_topic,
        language=language,
        limit=10,
    )
    card = {
        "id": f"card_{secrets.token_hex(4)}",
        "kind": "news_source_suggestions_card",
        "title": "Suggested news sources",
        "subtitle": "Enable any curated RSS feed with one click, or ask to add a custom RSS URL.",
        "data": {"sources": suggs},
    }
    return {
        "model_payload": {
            "ok": True,
            "suggestions": suggs,
            "categories_hint": ["European & Public", "Independent Investigative", "Science & Tech", "German / French", "US & UK"],
            "ui_card_emitted": "news_source_suggestions_card",
        },
        "ui_cards": [card],
    }


@satz_tool(
    name="news_settings_manage_source_feed",
    domain="news_settings",
    mode="staged_write",
    mcp_safe=False,
    description=(
        "Add, enable, pause, or request confirmation to remove a news source RSS feed. "
        "Starter outlets (dw.com, tagesschau.de, bbc.com, meduza.io, lemonde.fr, spiegel.de, euronews.com, arxiv.org, etc.) "
        "resolve automatically by domain/name without needing an explicit feed URL."
    ),
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "enable", "pause", "remove"],
                "description": "Feed action to perform.",
            },
            "domain": {"type": "string", "description": "Outlet name or domain (e.g. meduza.io, spiegel.de, bbc.com)."},
            "feed_url": {"type": "string", "description": "Explicit RSS/Atom feed URL when adding a custom feed."},
            "title": {"type": "string", "description": "Optional display label."},
            "language": {"type": "string", "description": "2-letter feed language code (default en)."},
            "feed_id": {"type": "string", "description": "Optional exact feed_id."},
        },
        "required": ["action"],
    },
)
def news_settings_manage_source_feed(
    runtime: Any,
    session: Any = None,
    action: str = "add",
    domain: str = "",
    feed_url: str = "",
    title: str = "",
    language: str = "en",
    feed_id: str = "",
) -> dict[str, Any]:
    act = (action or "add").strip().lower()
    dom = _resolve_domain_alias(runtime, domain)
    fid = (feed_id or "").strip()
    raw_url = (feed_url or "").strip()

    snap = _collect_news_settings_state(runtime)
    matched_feed = None
    for s in snap["all_sources"]:
        for f in s.get("feeds") or []:
            if fid and f["feed_id"] == fid:
                matched_feed = {**f, "domain": s["domain"]}
                break
            if dom and s["domain"] == dom:
                matched_feed = {**f, "domain": s["domain"]}
                break
        if matched_feed:
            break

    if act == "remove":
        target_fid = fid or (matched_feed["feed_id"] if matched_feed else "")
        target_label = (matched_feed.get("title") if matched_feed else "") or dom or target_fid
        if not target_fid:
            return {"model_payload": {"ok": False, "error": f"No configured feed found for '{domain or fid}'."}}
        summary = f"Permanently remove news feed '{target_label}' ({target_fid})"
        tok = create_confirm_gate(
            runtime,
            action_type="delete_news_feed",
            summary=summary,
            params={"feed_id": target_fid, "label": target_label},
        )
        card = {
            "id": f"card_{secrets.token_hex(4)}",
            "kind": "confirm_gate_card",
            "title": f"Remove news feed: {target_label}",
            "subtitle": summary,
            "confirm_token": tok,
            "data": {"action_type": "delete_news_feed", "feed_id": target_fid, "danger": True, "requires_pin": False},
        }
        return {
            "model_payload": {"ok": True, "confirm_required": True, "ui_card_emitted": "confirm_gate_card"},
            "ui_cards": [card],
        }

    if act == "pause":
        target_fid = fid or (matched_feed["feed_id"] if matched_feed else "")
        if not target_fid:
            return {"model_payload": {"ok": False, "error": f"No configured feed found to pause for '{domain or fid}'."}}
        res = runtime.news.add_or_toggle_feed({"action": "toggle", "feed_id": target_fid, "enabled": False})
        trec = runtime.store.trust(matched_feed["domain"] if matched_feed else dom)
        return {
            "model_payload": {
                "ok": bool(res.get("ok")),
                "action": "paused",
                "feed_id": target_fid,
                "domain": matched_feed["domain"] if matched_feed else dom,
                "trust_effective": round(float(trec["effective"]), 2),
            }
        }

    # Add or enable
    if matched_feed and not raw_url:
        res = runtime.news.add_or_toggle_feed({"action": "toggle", "feed_id": matched_feed["feed_id"], "enabled": True})
        dom = matched_feed["domain"]
        trec = runtime.store.trust(dom)
        return {
            "model_payload": {
                "ok": bool(res.get("ok")),
                "action": "enabled",
                "feed_id": matched_feed["feed_id"],
                "domain": dom,
                "title": matched_feed.get("title") or dom,
                "trust_system": round(float(trec["system"]), 2),
                "trust_effective": round(float(trec["effective"]), 2),
                "band": trec["band"],
            }
        }

    if raw_url:
        try:
            res = runtime.news.add_or_toggle_feed(
                {
                    "feed_url": raw_url,
                    "domain": dom,
                    "title": title or dom,
                    "language": (language or "en").strip().lower() or "en",
                }
            )
            eff_dom = str(res.get("domain") or dom)
            trec = runtime.store.trust(eff_dom)
            return {
                "model_payload": {
                    "ok": bool(res.get("ok")),
                    "action": "added",
                    "feed_id": res.get("feed_id"),
                    "domain": eff_dom,
                    "feed_url": raw_url,
                    "trust_system": round(float(trec["system"]), 2),
                    "trust_effective": round(float(trec["effective"]), 2),
                    "band": trec["band"],
                }
            }
        except Exception as exc:
            return {"model_payload": {"ok": False, "error": str(exc)}}

    # No feed URL and not in starter catalog -> emit inline card so user can paste RSS URL or inspect suggestions
    trec = runtime.store.trust(dom) if dom else None
    suggs = _build_source_suggestions(runtime, query=domain, limit=6)
    card = {
        "id": f"card_{secrets.token_hex(4)}",
        "kind": "news_add_feed_card",
        "title": f"Add RSS feed{f' for {dom}' if dom else ''}",
        "subtitle": (
            f"{dom} has system score {trec['system']:.1f}/10 ({trec['band']}) in the registry, "
            "or pick a built-in feed below."
            if trec and dom
            else "Enter a public RSS or Atom feed URL to subscribe."
        ),
        "data": {"domain": dom, "title": title or dom, "suggestions": suggs},
    }
    return {
        "model_payload": {
            "ok": False,
            "needs_feed_url": True,
            "domain": dom,
            "suggestions": suggs,
            "ui_card_emitted": "news_add_feed_card",
        },
        "ui_cards": [card],
    }


@satz_tool(
    name="news_settings_set_source_trust",
    domain="news_settings",
    mode="staged_write",
    mcp_safe=False,
    description=(
        "View or update personal trust score (0..10) for a news domain, enforcing Satz's hard 30% cap rule "
        "(effective = 0.7 * system + 0.3 * personal; system score is never overwritten). Pass reset=true to revert to system-only."
    ),
    parameters={
        "type": "object",
        "properties": {
            "domain": {"type": "string", "description": "News domain or outlet name (e.g. bbc.com, tagesschau.de, rt.com)."},
            "personal_score": {
                "type": "number",
                "description": "Desired personal trust score 0..10. Omit only to inspect without changing.",
            },
            "reset": {"type": "boolean", "description": "Set true to clear personal override back to system-only."},
        },
        "required": ["domain"],
    },
)
def news_settings_set_source_trust(
    runtime: Any,
    session: Any = None,
    domain: str = "",
    personal_score: float | None = None,
    reset: bool = False,
) -> dict[str, Any]:
    dom = _resolve_domain_alias(runtime, domain)
    if not dom:
        return {"model_payload": {"ok": False, "error": "Provide a valid domain name (e.g. bbc.com)."}}

    if reset:
        res = runtime.set_domain_trust(dom, None)
        mode_note = "reset_to_system"
    elif personal_score is not None:
        raw_val = float(personal_score)
        clamped = max(0.0, min(10.0, raw_val))
        res = runtime.set_domain_trust(dom, clamped)
        mode_note = "updated"
    else:
        t_rec = runtime.store.trust(dom)
        res = {
            "ok": True,
            "domain": dom,
            "system": round(float(t_rec["system"]), 2),
            "personal": round(float(t_rec["personal"]), 2) if t_rec["personal"] is not None else None,
            "effective": round(float(t_rec["effective"]), 2),
            "band": str(t_rec["band"]),
            "band_label": str(t_rec["band_label"]),
            "category": str(t_rec.get("category") or ""),
            "why": str(t_rec.get("why") or ""),
            "conflict": bool(t_rec.get("conflict")),
        }
        mode_note = "inspected"

    card = {
        "id": f"card_{secrets.token_hex(4)}",
        "kind": "news_source_trust_card",
        "title": f"Source trust: {dom}",
        "subtitle": (
            f"System {res['system']:.1f} · Effective {res['effective']:.2f}/10 ({res['band']}) · "
            "Formula: 0.7 * system + 0.3 * personal"
        ),
        "data": res,
    }
    return {
        "model_payload": {
            **res,
            "status": mode_note,
            "rule": "effective = 0.7 * system + 0.3 * personal (hard 30% cap; system score unchanged)",
            "ui_card_emitted": "news_source_trust_card",
        },
        "ui_cards": [card],
    }


@satz_tool(
    name="news_settings_suggest_topics",
    domain="news_settings",
    mode="read",
    mcp_safe=True,
    description=(
        "Suggest concrete tracked news topics with keywords for broad, ambiguous, or initial onboarding requests "
        "(e.g. 'tech', 'what should I follow?', or when no topics exist yet)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "interest_hint": {"type": "string", "description": "Optional topic area, region, or keyword hint."},
        },
        "required": [],
    },
)
def news_settings_suggest_topics(
    runtime: Any,
    session: Any = None,
    interest_hint: str = "",
) -> dict[str, Any]:
    suggs = _build_topic_suggestions(runtime, hint=interest_hint, limit=8)
    card = {
        "id": f"card_{secrets.token_hex(4)}",
        "kind": "news_topic_suggestions_card",
        "title": "Suggested news topics",
        "subtitle": "Click + Track to start hourly monitoring for a topic, or tell me which ones to follow.",
        "data": {"suggestions": suggs},
    }
    return {
        "model_payload": {
            "ok": True,
            "suggestions": suggs,
            "ui_card_emitted": "news_topic_suggestions_card",
        },
        "ui_cards": [card],
    }


@satz_tool(
    name="news_settings_manage_topic",
    domain="news_settings",
    mode="staged_write",
    mcp_safe=False,
    description=(
        "List, add (follow), suppress, or request confirmation to delete tracked news topics. "
        "Supports single `name` or multiple `names` at once."
    ),
    parameters={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "list", "suppress", "remove"]},
            "name": {"type": "string", "description": "Topic name to add, suppress, or remove."},
            "names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of multiple topic names to add at once.",
            },
            "keywords": {"type": "string", "description": "Optional comma-separated keywords."},
            "topic_id": {"type": "string", "description": "Optional exact topic_id when removing."},
        },
        "required": ["action"],
    },
)
def news_settings_manage_topic(
    runtime: Any,
    session: Any = None,
    action: str = "add",
    name: str = "",
    names: list[str] | None = None,
    keywords: str = "",
    topic_id: str = "",
) -> dict[str, Any]:
    act = (action or "add").strip().lower()
    if act == "list":
        res = runtime.news.list_topics()
        topics = res.get("topics") or []
        return {"model_payload": {"ok": True, "total": len(topics), "topics": topics}}

    if act == "remove":
        topics = runtime.news.list_topics().get("topics") or []
        tid = (topic_id or "").strip()
        target_row = next(
            (
                t
                for t in topics
                if (tid and t["topic_id"] == tid)
                or (name and str(t["name"]).strip().lower() == name.strip().lower())
                or (name and name.strip().lower() in str(t["name"]).strip().lower())
            ),
            None,
        )
        if not target_row:
            return {"model_payload": {"ok": False, "error": f"Tracked topic '{name or tid}' not found."}}
        tok = create_confirm_gate(
            runtime,
            action_type="delete_news_topic",
            summary=f"Remove tracked topic '{target_row['name']}'",
            params={"topic_id": target_row["topic_id"], "name": target_row["name"]},
        )
        card = {
            "id": f"card_{secrets.token_hex(4)}",
            "kind": "confirm_gate_card",
            "title": f"Remove topic: {target_row['name']}",
            "subtitle": f"Stop tracking '{target_row['name']}' and remove its topic watch.",
            "confirm_token": tok,
            "data": {"action_type": "delete_news_topic", "topic_id": target_row["topic_id"], "danger": True, "requires_pin": False},
        }
        return {
            "model_payload": {"ok": True, "confirm_required": True, "ui_card_emitted": "confirm_gate_card"},
            "ui_cards": [card],
        }

    if act == "suppress":
        clean_n = (name or "").strip()
        if not clean_n:
            return {"model_payload": {"ok": False, "error": "Topic name is required to suppress."}}
        res = runtime.news.manage_topic({"action": "suppress", "name": clean_n})
        return {"model_payload": {"ok": True, "suppressed": res.get("suppressed")}}

    target_names = [str(n).strip() for n in (names or []) if str(n).strip()]
    if name and name.strip() and name.strip() not in target_names:
        target_names.append(name.strip())
    if not target_names:
        return {"model_payload": {"ok": False, "error": "Provide at least one topic name to add."}}

    added: list[dict[str, Any]] = []
    for t_name in target_names[:8]:
        kw_arg = keywords if len(target_names) == 1 else ""
        if not kw_arg:
            for cat in _TOPIC_CATALOG:
                if cat["name"].lower() == t_name.lower():
                    kw_arg = ", ".join(cat["keywords"])
                    break
        res = runtime.news.manage_topic({"action": "add", "name": t_name, "keywords": kw_arg or None, "watch": True})
        added.append({"topic_id": res.get("topic_id"), "name": res.get("name"), "watch_id": res.get("watch_id")})

    return {
        "model_payload": {
            "ok": True,
            "action": "added",
            "added": added,
            "total_topics": len(runtime.news.list_topics().get("topics") or []),
        }
    }
