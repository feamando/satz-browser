"""
Per-profile Extensible Action Provider Playbook & Vault-linked Credential Registry.

Stores non-secret category routing, ordered provider priorities, URL templates, and
user constraints per profile (`profiles/<id>/store.sqlite`), while keeping all
API keys, passwords, tokens, and cookies strictly inside encrypted `vault.enc`
(`SatzPasswordsManager`).
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import secrets
import sqlite3
import time
import urllib.parse
from typing import Any


BUILTIN_PROVIDER_CATEGORIES: list[dict[str, Any]] = [
    {
        "category_id": "search.general",
        "parent_group": "search",
        "label": "General",
        "description": "Default web search engines and fallbacks",
        "sort_order": 10,
    },
    {
        "category_id": "search.knowledge",
        "parent_group": "search",
        "label": "Knowledge",
        "description": "Encyclopedias, docs, academic & internal wikis",
        "sort_order": 20,
    },
    {
        "category_id": "search.travel",
        "parent_group": "search",
        "label": "Travel",
        "description": "Flights, trains, and trip planning",
        "sort_order": 30,
    },
    {
        "category_id": "search.accommodation",
        "parent_group": "search",
        "label": "Accommodation",
        "description": "Hotels, apartments, and stays",
        "sort_order": 40,
    },
    {
        "category_id": "maps.navigation",
        "parent_group": "maps",
        "label": "Maps & Navigation",
        "description": "Places, addresses, routes, and local transit",
        "sort_order": 50,
    },
    {
        "category_id": "commerce.tech",
        "parent_group": "commerce",
        "label": "Tech & Software",
        "description": "Electronics, components, and software stores",
        "sort_order": 60,
    },
    {
        "category_id": "commerce.clothing",
        "parent_group": "commerce",
        "label": "Clothing",
        "description": "Apparel, footwear, and fashion retailers",
        "sort_order": 70,
    },
    {
        "category_id": "commerce.food",
        "parent_group": "commerce",
        "label": "Food & Beverages",
        "description": "Groceries, meal kits, and food delivery",
        "sort_order": 80,
    },
]


CURATED_PROVIDER_PRESETS: dict[str, list[dict[str, Any]]] = {
    "search.general": [
        {
            "provider_slug": "brave",
            "display_name": "Brave Search",
            "mode": "search_api",
            "api_driver": "brave",
            "domains": ["search.brave.com"],
            "url_template": "https://search.brave.com/search?q={query}",
            "vault_service": "BRAVE",
            "alt_prefixes": ["BRAVE_SEARCH"],
            "alt_env_keys": ["BRAVE_API_KEY", "BRAVE_SEARCH_API_KEY"],
            "requires_key": True,
        },
        {
            "provider_slug": "kagi",
            "display_name": "Kagi Search",
            "mode": "search_api",
            "api_driver": "kagi",
            "domains": ["kagi.com"],
            "url_template": "https://kagi.com/search?q={query}",
            "vault_service": "KAGI",
            "alt_prefixes": ["KAGI_SEARCH"],
            "alt_env_keys": ["KAGI_API_KEY", "KAGI_TOKEN"],
            "requires_key": True,
        },
        {
            "provider_slug": "serper",
            "display_name": "Google via Serper",
            "mode": "search_api",
            "api_driver": "serper",
            "domains": ["google.com"],
            "url_template": "https://www.google.com/search?q={query}",
            "vault_service": "SERPER",
            "alt_prefixes": [],
            "alt_env_keys": ["SERPER_API_KEY"],
            "requires_key": True,
        },
        {
            "provider_slug": "ddgs",
            "display_name": "DuckDuckGo",
            "mode": "search_api",
            "api_driver": "ddgs",
            "domains": ["duckduckgo.com"],
            "url_template": "https://duckduckgo.com/?q={query}",
            "vault_service": "DDGS",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
        {
            "provider_slug": "google",
            "display_name": "Google Web",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["google.com"],
            "url_template": "https://www.google.com/search?q={query}",
            "vault_service": "GOOGLE",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
    ],
    "search.knowledge": [
        {
            "provider_slug": "wikipedia",
            "display_name": "Wikipedia",
            "mode": "search_api",
            "api_driver": "wikipedia_api",
            "domains": ["wikipedia.org", "en.wikipedia.org"],
            "url_template": "https://en.wikipedia.org/w/index.php?search={query}",
            "vault_service": "WIKIPEDIA",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
        {
            "provider_slug": "wolfram",
            "display_name": "WolframAlpha",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["wolframalpha.com"],
            "url_template": "https://www.wolframalpha.com/input?i={query}",
            "vault_service": "WOLFRAM",
            "alt_prefixes": [],
            "alt_env_keys": ["WOLFRAM_API_KEY"],
            "requires_key": False,
        },
        {
            "provider_slug": "github",
            "display_name": "GitHub",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["github.com"],
            "url_template": "https://github.com/search?q={query}",
            "vault_service": "GITHUB",
            "alt_prefixes": [],
            "alt_env_keys": ["GITHUB_TOKEN"],
            "requires_key": False,
        },
        {
            "provider_slug": "mdn",
            "display_name": "MDN Web Docs",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["developer.mozilla.org"],
            "url_template": "https://developer.mozilla.org/en-US/search?q={query}",
            "vault_service": "MDN",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
        {
            "provider_slug": "confluence",
            "display_name": "Confluence",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["atlassian.net"],
            "url_template": "https://id.atlassian.com/",
            "vault_service": "CONFLUENCE",
            "alt_prefixes": ["JIRA"],
            "alt_env_keys": [],
            "requires_key": False,
        },
    ],
    "search.travel": [
        {
            "provider_slug": "google_flights",
            "display_name": "Google Flights",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["google.com"],
            "url_template": "https://www.google.com/travel/flights?q={query}",
            "vault_service": "GOOGLE",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
        {
            "provider_slug": "db_bahn",
            "display_name": "Deutsche Bahn",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["bahn.de", "int.bahn.de"],
            "url_template": "https://www.bahn.de/angebot",
            "vault_service": "DB_BAHN",
            "alt_prefixes": ["BAHN"],
            "alt_env_keys": [],
            "requires_key": False,
        },
        {
            "provider_slug": "skyscanner",
            "display_name": "Skyscanner",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["skyscanner.net", "skyscanner.com"],
            "url_template": "https://www.skyscanner.net/transport/flights/",
            "vault_service": "SKYSCANNER",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
        {
            "provider_slug": "trainline",
            "display_name": "Trainline",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["thetrainline.com"],
            "url_template": "https://www.thetrainline.com/",
            "vault_service": "TRAINLINE",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
    ],
    "search.accommodation": [
        {
            "provider_slug": "booking",
            "display_name": "Booking.com",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["booking.com"],
            "url_template": "https://www.booking.com/searchresults.html?ss={query}",
            "vault_service": "BOOKING",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
        {
            "provider_slug": "airbnb",
            "display_name": "Airbnb",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["airbnb.com", "airbnb.de"],
            "url_template": "https://www.airbnb.com/s/{query}/homes",
            "vault_service": "AIRBNB",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
        {
            "provider_slug": "hotels",
            "display_name": "Hotels.com",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["hotels.com"],
            "url_template": "https://www.hotels.com/Hotel-Search?destination={query}",
            "vault_service": "HOTELS",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
    ],
    "maps.navigation": [
        {
            "provider_slug": "openstreetmap",
            "display_name": "OpenStreetMap / Nominatim",
            "mode": "search_api",
            "api_driver": "nominatim",
            "domains": ["openstreetmap.org"],
            "url_template": "https://www.openstreetmap.org/search?query={query}",
            "vault_service": "OPENSTREETMAP",
            "alt_prefixes": ["NOMINATIM"],
            "alt_env_keys": [],
            "requires_key": False,
        },
        {
            "provider_slug": "google_maps",
            "display_name": "Google Maps",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["maps.google.com", "google.com"],
            "url_template": "https://www.google.com/maps/search/{query}",
            "vault_service": "GOOGLE_MAPS",
            "alt_prefixes": ["GOOGLE"],
            "alt_env_keys": ["GOOGLE_MAPS_API_KEY"],
            "requires_key": False,
        },
        {
            "provider_slug": "mapbox",
            "display_name": "Mapbox",
            "mode": "search_api",
            "api_driver": "mapbox",
            "domains": ["mapbox.com"],
            "url_template": "https://www.mapbox.com/",
            "vault_service": "MAPBOX",
            "alt_prefixes": [],
            "alt_env_keys": ["MAPBOX_API_KEY", "MAPBOX_TOKEN"],
            "requires_key": True,
        },
        {
            "provider_slug": "apple_maps",
            "display_name": "Apple Maps Web",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["maps.apple.com"],
            "url_template": "https://maps.apple.com/?q={query}",
            "vault_service": "APPLE_MAPS",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
    ],
    "commerce.tech": [
        {
            "provider_slug": "geizhals",
            "display_name": "Geizhals",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["geizhals.de", "geizhals.eu"],
            "url_template": "https://geizhals.de/?fs={query}",
            "vault_service": "GEIZHALS",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
        {
            "provider_slug": "amazon",
            "display_name": "Amazon",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["amazon.de", "amazon.com", "amazon.co.uk"],
            "url_template": "https://www.amazon.de/s?k={query}",
            "vault_service": "AMAZON",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
        {
            "provider_slug": "cyberport",
            "display_name": "Cyberport",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["cyberport.de"],
            "url_template": "https://www.cyberport.de/tools/search?query={query}",
            "vault_service": "CYBERPORT",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
        {
            "provider_slug": "notebooksbilliger",
            "display_name": "Notebooksbilliger",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["notebooksbilliger.de"],
            "url_template": "https://www.notebooksbilliger.de/suche?search={query}",
            "vault_service": "NOTEBOOKSBILLIGER",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
    ],
    "commerce.clothing": [
        {
            "provider_slug": "zalando",
            "display_name": "Zalando",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["zalando.de", "en.zalando.de", "zalando.com"],
            "url_template": "https://www.zalando.de/katalog/?q={query}",
            "vault_service": "ZALANDO",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
        {
            "provider_slug": "uniqlo",
            "display_name": "Uniqlo",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["uniqlo.com"],
            "url_template": "https://www.uniqlo.com/de/de/search?q={query}",
            "vault_service": "UNIQLO",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
        {
            "provider_slug": "asos",
            "display_name": "ASOS",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["asos.com", "asos.de"],
            "url_template": "https://www.asos.com/search/?q={query}",
            "vault_service": "ASOS",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
    ],
    "commerce.food": [
        {
            "provider_slug": "rewe",
            "display_name": "REWE",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["rewe.de", "shop.rewe.de"],
            "url_template": "https://shop.rewe.de/productList?search={query}",
            "vault_service": "REWE",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
        {
            "provider_slug": "hellofresh",
            "display_name": "HelloFresh",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["hellofresh.de", "hellofresh.com"],
            "url_template": "https://www.hellofresh.de/menus",
            "vault_service": "HELLOFRESH",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
        {
            "provider_slug": "wolt",
            "display_name": "Wolt",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["wolt.com"],
            "url_template": "https://wolt.com/en/search?q={query}",
            "vault_service": "WOLT",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
        {
            "provider_slug": "instacart",
            "display_name": "Instacart",
            "mode": "web_account",
            "api_driver": "",
            "domains": ["instacart.com"],
            "url_template": "https://www.instacart.com/store/s?k={query}",
            "vault_service": "INSTACART",
            "alt_prefixes": [],
            "alt_env_keys": [],
            "requires_key": False,
        },
    ],
}


CATEGORY_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "search.general": ("general", "web search", "search engine", "internet", "online search"),
    "search.knowledge": ("knowledge", "wikipedia", "encyclopedia", "docs", "documentation", "reference", "paper", "wiki", "research", "math", "formula"),
    "search.travel": ("travel", "flight", "flights", "train", "trains", "rail", "ticket", "airline", "bahn", "route trip"),
    "search.accommodation": ("accommodation", "accomodation", "hotel", "hotels", "stay", "stays", "airbnb", "booking", "hostel", "apartment", "lodging"),
    "maps.navigation": ("map", "maps", "navigation", "directions", "address", "distance", "route", "nearby", "restaurant near", "cafe near", "transit"),
    "commerce.tech": ("tech", "software", "laptop", "pc", "gpu", "ssd", "monitor", "electronics", "gadget", "phone", "camera", "app", "hardware"),
    "commerce.clothing": ("clothing", "clothes", "jacket", "coat", "shoes", "sneakers", "shirt", "jeans", "apparel", "fashion", "outfit", "size"),
    "commerce.food": ("food", "beverages", "grocery", "groceries", "meal", "recipe", "order food", "supermarket", "drink", "coffee", "delivery"),
}

_BLOCKED_HOSTS = frozenset({
    "localhost",
    "localhost.localdomain",
    "0.0.0.0",
    "127.0.0.1",
    "::1",
    "169.254.169.254",
    "metadata.google.internal",
})
_QUERY_PARAM_NAMES = ("q", "k", "query", "search", "term", "keywords", "keyword", "fs", "ss", "i", "s", "text", "destination")


def _slugify(raw: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (raw or "").strip().lower()).strip("_")
    return s[:max_len] or "item"


def _clean_host(raw: str) -> str:
    val = (raw or "").strip().lower()
    if "://" in val:
        try:
            val = urllib.parse.urlparse(val).hostname or ""
        except Exception:
            val = ""
    else:
        val = val.split("/")[0].split(":")[0]
    return val.removeprefix("www.").strip(".")


def _is_blocked_host(host: str) -> bool:
    h = (host or "").strip().lower().rstrip(".").strip("[]")
    if not h or h in _BLOCKED_HOSTS:
        return True
    if h.endswith((".localhost", ".local", ".internal")):
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return "." not in h
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def validate_url_template(raw_url: str) -> str:
    """Validates an `http(s)` URL or `{query}` search URL template safely."""
    u = (raw_url or "").strip()
    if not u:
        return ""
    # Replace `{query}` temporarily so `urlparse` validates cleanly.
    probe = u.replace("{query}", "satztest")
    parsed = urllib.parse.urlparse(probe)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError("URL template must start with http:// or https://")
    host = (parsed.hostname or "").lower().rstrip(".")
    if _is_blocked_host(host):
        raise ValueError(f"Blocked or invalid host in URL template: {host or u}")
    return u[:600]


def ensure_provider_tables_on_conn(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS satz_provider_categories (
            category_id TEXT PRIMARY KEY,
            parent_group TEXT NOT NULL DEFAULT 'custom',
            label TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            is_builtin INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 100,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS satz_provider_entries (
            id TEXT PRIMARY KEY,
            category_id TEXT NOT NULL,
            provider_slug TEXT NOT NULL,
            display_name TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'web_account',
            api_driver TEXT NOT NULL DEFAULT '',
            domains_json TEXT NOT NULL DEFAULT '[]',
            url_template TEXT NOT NULL DEFAULT '',
            vault_service TEXT NOT NULL DEFAULT '',
            constraints_note TEXT NOT NULL DEFAULT '',
            priority INTEGER NOT NULL DEFAULT 1,
            enabled INTEGER NOT NULL DEFAULT 1,
            auto_learned INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_satz_provider_cat ON satz_provider_entries(category_id, priority ASC);

        CREATE TABLE IF NOT EXISTS satz_provider_suggestions (
            suggestion_id TEXT PRIMARY KEY,
            category_id TEXT NOT NULL,
            provider_slug TEXT NOT NULL,
            display_name TEXT NOT NULL,
            domain TEXT NOT NULL,
            url_template TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            evidence_count INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'pending',
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_satz_prov_sug_status ON satz_provider_suggestions(status, updated_at DESC);
        """
    )

    seeded_row = conn.execute(
        "SELECT value FROM satz_meta WHERE key = 'providers_seeded_v1'"
    ).fetchone()
    if seeded_row and str(seeded_row["value"]) == "1":
        return

    now = time.time()
    for cat in BUILTIN_PROVIDER_CATEGORIES:
        conn.execute(
            """
            INSERT OR IGNORE INTO satz_provider_categories
              (category_id, parent_group, label, description, is_builtin, sort_order, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (
                cat["category_id"],
                cat["parent_group"],
                cat["label"],
                cat["description"],
                int(cat["sort_order"]),
                now,
            ),
        )

    starter_rows: list[tuple[str, dict[str, Any], int]] = []
    if (os.environ.get("BRAVE_API_KEY") or "").strip():
        starter_rows.append(("search.general", CURATED_PROVIDER_PRESETS["search.general"][0], 1))
        starter_rows.append(("search.general", CURATED_PROVIDER_PRESETS["search.general"][3], 2))
    else:
        starter_rows.append(("search.general", CURATED_PROVIDER_PRESETS["search.general"][3], 1))
    starter_rows.append(("search.knowledge", CURATED_PROVIDER_PRESETS["search.knowledge"][0], 1))
    starter_rows.append(("maps.navigation", CURATED_PROVIDER_PRESETS["maps.navigation"][0], 1))

    for cid, preset, prio in starter_rows:
        eid = f"prov_{_slugify(cid, 24)}_{preset['provider_slug']}"
        conn.execute(
            """
            INSERT OR IGNORE INTO satz_provider_entries
              (id, category_id, provider_slug, display_name, mode, api_driver, domains_json,
               url_template, vault_service, constraints_note, priority, enabled, auto_learned, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, 1, 0, ?, ?)
            """,
            (
                eid,
                cid,
                preset["provider_slug"],
                preset["display_name"],
                preset["mode"],
                preset["api_driver"],
                json.dumps(preset["domains"], ensure_ascii=False),
                preset["url_template"],
                preset["vault_service"],
                prio,
                now,
                now,
            ),
        )

    conn.execute(
        "INSERT OR REPLACE INTO satz_meta (key, value) VALUES ('providers_seeded_v1', '1')"
    )
    conn.commit()


def format_provider_search_url(url_template: str, query: str = "") -> str:
    """Safely interpolates `{query}` in a validated URL template."""
    tpl = (url_template or "").strip()
    if not tpl:
        return ""
    q = (query or "").strip()
    if "{query}" in tpl:
        if not q:
            return tpl.replace("{query}", "")
        return tpl.replace("{query}", urllib.parse.quote_plus(q))
    return tpl


def find_preset_match(raw_name_or_domain: str, category_id: str = "") -> dict[str, Any] | None:
    needle = (raw_name_or_domain or "").strip().lower()
    if not needle:
        return None
    needle_dom = _clean_host(needle)
    pools: list[tuple[str, dict[str, Any]]] = []
    if category_id and category_id in CURATED_PROVIDER_PRESETS:
        for p in CURATED_PROVIDER_PRESETS[category_id]:
            pools.append((category_id, p))
    for cid, plist in CURATED_PROVIDER_PRESETS.items():
        if cid == category_id:
            continue
        for p in plist:
            pools.append((cid, p))

    for cid, p in pools:
        slug = p["provider_slug"].lower()
        name = p["display_name"].lower()
        doms = [d.lower().removeprefix("www.") for d in (p.get("domains") or [])]
        if needle == slug or needle == name or (needle_dom and needle_dom in doms):
            return {**p, "suggested_category_id": cid}
        if needle_dom and any(needle_dom.endswith("." + d) or d.endswith("." + needle_dom) for d in doms):
            return {**p, "suggested_category_id": cid}
    return None


class SatzProvidersManager:
    """Manages per-profile default action categories, ordered providers, and Vault credential links."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def ensure_tables_on_conn(self, conn: sqlite3.Connection) -> None:
        ensure_provider_tables_on_conn(conn)

    def _preset_meta(self, provider_slug: str, category_id: str = "") -> dict[str, Any]:
        slug_low = (provider_slug or "").strip().lower()
        if category_id in CURATED_PROVIDER_PRESETS:
            for p in CURATED_PROVIDER_PRESETS[category_id]:
                if p["provider_slug"] == slug_low:
                    return p
        for plist in CURATED_PROVIDER_PRESETS.values():
            for p in plist:
                if p["provider_slug"] == slug_low:
                    return p
        return {}

    def _enrich_provider_row(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        r = dict(row)
        try:
            domains = json.loads(r.get("domains_json") or "[]")
            if not isinstance(domains, list):
                domains = []
        except Exception:
            domains = []
        preset = self._preset_meta(str(r.get("provider_slug") or ""), str(r.get("category_id") or ""))
        vault_svc = str(r.get("vault_service") or "").strip().upper()
        if not vault_svc and domains:
            from satz_passwords import _normalize_service_prefix

            vault_svc = _normalize_service_prefix(str(domains[0]))
        alt_pfxs = list(preset.get("alt_prefixes") or [])

        pm = getattr(self.runtime, "passwords", None)
        if pm is not None and hasattr(pm, "get_service_auth_status"):
            auth_info = pm.get_service_auth_status(vault_svc, domains=domains, alt_prefixes=alt_pfxs)
        else:
            auth_info = {
                "auth_status": "none",
                "matched_service": vault_svc,
                "masked_label": "",
                "fields": [],
                "auth_ready": False,
            }

        # Check env fallback strictly for BRAVE_API_KEY when Brave is selected and vault doesn't have it yet.
        alt_env_keys = list(preset.get("alt_env_keys") or [])
        if not auth_info.get("auth_ready") and str(r.get("api_driver") or "") == "brave":
            if (os.environ.get("BRAVE_API_KEY") or "").strip():
                auth_info["auth_status"] = "api_key"
                auth_info["masked_label"] = "env key"
                auth_info["auth_ready"] = True

        return {
            "id": str(r["id"]),
            "category_id": str(r["category_id"]),
            "provider_slug": str(r["provider_slug"]),
            "display_name": str(r["display_name"]),
            "mode": str(r.get("mode") or "web_account"),
            "api_driver": str(r.get("api_driver") or ""),
            "domains": [str(d) for d in domains if str(d).strip()],
            "url_template": str(r.get("url_template") or ""),
            "vault_service": vault_svc,
            "constraints_note": str(r.get("constraints_note") or ""),
            "priority": int(r.get("priority") or 1),
            "enabled": bool(r.get("enabled", 1)),
            "auto_learned": bool(r.get("auto_learned", 0)),
            "requires_key": bool(preset.get("requires_key", False)),
            "auth_status": auth_info["auth_status"],
            "auth_service": auth_info["matched_service"],
            "masked_auth_label": auth_info["masked_label"],
            "auth_fields": auth_info["fields"],
            "auth_ready": bool(auth_info["auth_ready"]),
            "alt_env_keys": alt_env_keys,
        }

    def infer_provider_template(self, raw_input: str, category_id: str = "") -> dict[str, Any]:
        """Infers display name, domain, `{query}` template, and existing Vault link from a domain or sample URL."""
        raw = (raw_input or "").strip()
        if not raw:
            return {"ok": False, "error": "Enter a domain name, brand, or sample search URL."}

        preset = find_preset_match(raw, category_id=category_id)
        inferred_template = ""
        dom = ""
        display_name = ""
        mode = "web_account"
        api_driver = ""
        vault_svc = ""

        if "://" in raw:
            parsed = urllib.parse.urlparse(raw)
            if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
                return {"ok": False, "error": "Sample URL must start with http:// or https://"}
            host = parsed.hostname.lower().rstrip(".")
            if host in _BLOCKED_HOSTS:
                return {"ok": False, "error": "Blocked host"}
            dom = host.removeprefix("www.")
            q_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            replaced = False
            new_pairs: list[tuple[str, str]] = []
            for k, v in q_pairs:
                if not replaced and (k.lower() in _QUERY_PARAM_NAMES or len(q_pairs) == 1) and v.strip():
                    new_pairs.append((k, "__SATZ_QUERY__"))
                    replaced = True
                else:
                    new_pairs.append((k, v))
            if replaced:
                raw_qs = urllib.parse.urlencode(new_pairs).replace("__SATZ_QUERY__", "{query}")
                inferred_template = urllib.parse.urlunparse(
                    (parsed.scheme, parsed.netloc, parsed.path, "", raw_qs, "")
                )
            else:
                inferred_template = raw
        elif preset:
            dom = str((preset.get("domains") or [""])[0])
            inferred_template = str(preset.get("url_template") or "")
        else:
            dom = _clean_host(raw)
            if dom:
                inferred_template = f"https://{dom}"

        if preset:
            display_name = str(preset["display_name"])
            mode = str(preset.get("mode") or "web_account")
            api_driver = str(preset.get("api_driver") or "")
            vault_svc = str(preset.get("vault_service") or "")
            if not inferred_template:
                inferred_template = str(preset.get("url_template") or "")
            domains = list(preset.get("domains") or ([dom] if dom else []))
        else:
            base = (dom.split(".")[0] if dom else raw).replace("-", " ").replace("_", " ").strip()
            display_name = base.title() if base else raw[:40]
            domains = [dom] if dom else []
            from satz_passwords import _normalize_service_prefix

            vault_svc = _normalize_service_prefix(dom or raw)

        pm = getattr(self.runtime, "passwords", None)
        auth_info = (
            pm.get_service_auth_status(vault_svc, domains=domains)
            if pm is not None and hasattr(pm, "get_service_auth_status")
            else {"auth_status": "none", "matched_service": vault_svc, "masked_label": "", "auth_ready": False}
        )
        return {
            "ok": True,
            "provider_slug": _slugify(preset["provider_slug"] if preset else (dom.split(".")[0] if dom else display_name)),
            "display_name": display_name,
            "domains": domains,
            "url_template": inferred_template,
            "mode": mode,
            "api_driver": api_driver,
            "vault_service": auth_info.get("matched_service") or vault_svc,
            "suggested_category_id": (preset or {}).get("suggested_category_id") or category_id or "search.general",
            "auth_status": auth_info["auth_status"],
            "masked_auth_label": auth_info["masked_label"],
            "auth_ready": bool(auth_info["auth_ready"]),
        }

    def _require_unlocked(self) -> None:
        pm = getattr(self.runtime, "passwords", None)
        if pm is not None and not pm.unlocked:
            raise PermissionError("Unlock a profile with its 6-digit PIN before editing action providers.")

    def list_registry(self) -> dict[str, Any]:
        pm = getattr(self.runtime, "passwords", None)
        unlocked = bool(pm and pm.unlocked)
        profile_id = pm.active_profile_id if unlocked else None
        if pm is not None and not unlocked:
            return {
                "ok": True,
                "unlocked": False,
                "profile_id": None,
                "categories": [],
                "providers_by_category": {},
                "presets": CURATED_PROVIDER_PRESETS,
                "suggestions": [],
            }

        with self.runtime.store_lock:
            conn = self.runtime.store.db
            ensure_provider_tables_on_conn(conn)
            cat_rows = conn.execute(
                """
                SELECT category_id, parent_group, label, description, is_builtin, sort_order, updated_at
                FROM satz_provider_categories
                ORDER BY sort_order ASC, label ASC
                """
            ).fetchall()
            prov_rows = conn.execute(
                """
                SELECT *
                FROM satz_provider_entries
                ORDER BY category_id ASC, priority ASC, created_at ASC
                """
            ).fetchall()
            sug_rows = conn.execute(
                """
                SELECT suggestion_id, category_id, provider_slug, display_name, domain, url_template, reason, evidence_count, status, updated_at
                FROM satz_provider_suggestions
                WHERE status = 'pending'
                ORDER BY updated_at DESC
                LIMIT 12
                """
            ).fetchall()

        categories = [
            {
                "category_id": str(r["category_id"]),
                "parent_group": str(r["parent_group"]),
                "label": str(r["label"]),
                "description": str(r["description"]),
                "is_builtin": bool(r["is_builtin"]),
                "sort_order": int(r["sort_order"] or 100),
            }
            for r in cat_rows
        ]
        providers_by_category: dict[str, list[dict[str, Any]]] = {c["category_id"]: [] for c in categories}
        for pr in prov_rows:
            item = self._enrich_provider_row(pr)
            providers_by_category.setdefault(item["category_id"], []).append(item)

        suggestions = [dict(sr) for sr in sug_rows]
        return {
            "ok": True,
            "unlocked": unlocked,
            "profile_id": profile_id,
            "categories": categories,
            "providers_by_category": providers_by_category,
            "presets": CURATED_PROVIDER_PRESETS,
            "suggestions": suggestions,
        }

    def upsert_category(
        self,
        *,
        category_id: str = "",
        label: str,
        parent_group: str = "custom",
        description: str = "",
        sort_order: int | None = None,
    ) -> dict[str, Any]:
        self._require_unlocked()
        clean_lbl = (label or "").strip()[:64]
        if not clean_lbl:
            raise ValueError("Category label is required.")
        grp = _slugify(parent_group or "custom", 24)
        cid = (category_id or "").strip().lower()
        if not cid:
            cid = f"{grp}.{_slugify(clean_lbl, 32)}"
        now = time.time()
        with self.runtime.store_lock:
            conn = self.runtime.store.db
            ensure_provider_tables_on_conn(conn)
            ex = conn.execute(
                "SELECT is_builtin, sort_order FROM satz_provider_categories WHERE category_id = ?",
                (cid,),
            ).fetchone()
            eff_builtin = int(ex["is_builtin"]) if ex else 0
            if sort_order is not None:
                eff_order = int(sort_order)
            elif ex:
                eff_order = int(ex["sort_order"])
            else:
                max_row = conn.execute("SELECT COALESCE(MAX(sort_order), 80) AS mx FROM satz_provider_categories").fetchone()
                eff_order = int((max_row["mx"] if max_row else 80) or 80) + 10
            conn.execute(
                """
                INSERT INTO satz_provider_categories
                  (category_id, parent_group, label, description, is_builtin, sort_order, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(category_id) DO UPDATE SET
                  parent_group = excluded.parent_group,
                  label = excluded.label,
                  description = excluded.description,
                  sort_order = excluded.sort_order,
                  updated_at = excluded.updated_at
                """,
                (cid, grp, clean_lbl, (description or "").strip()[:200], eff_builtin, eff_order, now),
            )
            conn.commit()
        reg = self.list_registry()
        return {**reg, "category_id": cid}

    def delete_category(self, category_id: str) -> dict[str, Any]:
        self._require_unlocked()
        cid = (category_id or "").strip().lower()
        if not cid:
            raise ValueError("category_id is required.")
        with self.runtime.store_lock:
            conn = self.runtime.store.db
            ensure_provider_tables_on_conn(conn)
            row = conn.execute(
                "SELECT is_builtin FROM satz_provider_categories WHERE category_id = ?",
                (cid,),
            ).fetchone()
            if not row:
                return {"ok": False, "error": f"Category '{cid}' not found."}
            if int(row["is_builtin"]):
                return {"ok": False, "error": "Built-in categories cannot be deleted; disable or remove their providers instead."}
            conn.execute("DELETE FROM satz_provider_entries WHERE category_id = ?", (cid,))
            conn.execute("DELETE FROM satz_provider_suggestions WHERE category_id = ?", (cid,))
            conn.execute("DELETE FROM satz_provider_categories WHERE category_id = ?", (cid,))
            conn.commit()
        return self.list_registry()

    def _renumber_priorities(self, conn: sqlite3.Connection, category_id: str) -> None:
        rows = conn.execute(
            "SELECT id FROM satz_provider_entries WHERE category_id = ? ORDER BY priority ASC, created_at ASC",
            (category_id,),
        ).fetchall()
        for idx, r in enumerate(rows, 1):
            conn.execute("UPDATE satz_provider_entries SET priority = ? WHERE id = ?", (idx, r["id"]))

    def upsert_provider(
        self,
        *,
        category_id: str,
        display_name: str,
        provider_id: str = "",
        provider_slug: str = "",
        mode: str = "web_account",
        api_driver: str = "",
        domains: list[str] | None = None,
        url_template: str = "",
        vault_service: str = "",
        constraints_note: str = "",
        priority: int | None = None,
        enabled: bool = True,
        auto_learned: bool = False,
        credentials: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self._require_unlocked()
        cid = (category_id or "").strip().lower()
        name = (display_name or "").strip()[:80]
        if not cid:
            raise ValueError("category_id is required.")
        if not name:
            raise ValueError("display_name is required.")

        clean_tpl = validate_url_template(url_template) if (url_template or "").strip() else ""
        clean_mode = "search_api" if str(mode or "").strip().lower() == "search_api" else "web_account"
        clean_driver = _slugify(api_driver, 32) if api_driver else ""
        clean_doms: list[str] = []
        for d in (domains or []):
            ch = _clean_host(str(d))
            if ch and ch not in clean_doms:
                clean_doms.append(ch)
        if not clean_doms and clean_tpl:
            ch = _clean_host(clean_tpl)
            if ch:
                clean_doms.append(ch)

        slug = _slugify(provider_slug or (clean_doms[0].split(".")[0] if clean_doms else name), 40)
        eff_vault_svc = re.sub(r"[^A-Z0-9_]+", "_", (vault_service or "").strip().upper()).strip("_")
        if not eff_vault_svc:
            from satz_passwords import _normalize_service_prefix

            eff_vault_svc = _normalize_service_prefix(clean_doms[0] if clean_doms else slug)

        creds = credentials if isinstance(credentials, dict) else {}
        has_secret_write = any(str(creds.get(k) or "").strip() for k in ("api_key", "username", "password", "token", "cookie"))
        pm = getattr(self.runtime, "passwords", None)
        if has_secret_write and (pm is None or not pm.unlocked):
            raise PermissionError("Unlock a profile with its 6-digit PIN before saving provider credentials.")

        now = time.time()
        with self.runtime.store_lock:
            conn = self.runtime.store.db
            ensure_provider_tables_on_conn(conn)
            cat_exists = conn.execute(
                "SELECT 1 FROM satz_provider_categories WHERE category_id = ?",
                (cid,),
            ).fetchone()
            if not cat_exists:
                raise ValueError(f"Unknown category_id: {cid}")

            eff_id = (provider_id or "").strip()
            existing = None
            if eff_id:
                existing = conn.execute("SELECT * FROM satz_provider_entries WHERE id = ?", (eff_id,)).fetchone()
            if existing is None:
                existing = conn.execute(
                    "SELECT * FROM satz_provider_entries WHERE category_id = ? AND provider_slug = ?",
                    (cid, slug),
                ).fetchone()
                if existing:
                    eff_id = str(existing["id"])
            if not eff_id:
                eff_id = f"prov_{_slugify(cid, 18)}_{slug}_{secrets.token_hex(3)}"

            if priority is not None and int(priority) >= 1:
                target_prio = int(priority)
                conn.execute(
                    "UPDATE satz_provider_entries SET priority = priority + 1 WHERE category_id = ? AND priority >= ? AND id != ?",
                    (cid, target_prio, eff_id),
                )
            elif existing is not None:
                target_prio = int(existing["priority"] or 1)
            else:
                mx_row = conn.execute(
                    "SELECT COALESCE(MAX(priority), 0) AS mx FROM satz_provider_entries WHERE category_id = ?",
                    (cid,),
                ).fetchone()
                target_prio = int((mx_row["mx"] if mx_row else 0) or 0) + 1

            conn.execute(
                """
                INSERT INTO satz_provider_entries
                  (id, category_id, provider_slug, display_name, mode, api_driver, domains_json,
                   url_template, vault_service, constraints_note, priority, enabled, auto_learned, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  category_id = excluded.category_id,
                  provider_slug = excluded.provider_slug,
                  display_name = excluded.display_name,
                  mode = excluded.mode,
                  api_driver = excluded.api_driver,
                  domains_json = excluded.domains_json,
                  url_template = excluded.url_template,
                  vault_service = excluded.vault_service,
                  constraints_note = excluded.constraints_note,
                  priority = excluded.priority,
                  enabled = excluded.enabled,
                  updated_at = excluded.updated_at
                """,
                (
                    eff_id,
                    cid,
                    slug,
                    name,
                    clean_mode,
                    clean_driver,
                    json.dumps(clean_doms, ensure_ascii=False),
                    clean_tpl,
                    eff_vault_svc,
                    (constraints_note or "").strip()[:240],
                    target_prio,
                    1 if enabled else 0,
                    1 if auto_learned else (int(existing["auto_learned"]) if existing else 0),
                    float(existing["created_at"]) if existing else now,
                    now,
                ),
            )
            self._renumber_priorities(conn, cid)
            conn.commit()

        if has_secret_write and pm is not None:
            dom_url = clean_doms[0] if clean_doms else clean_tpl
            extra_map: dict[str, str] = {}
            preset_meta = self._preset_meta(slug, cid)
            for ak in preset_meta.get("alt_env_keys") or []:
                if ak == "BRAVE_API_KEY" and str(creds.get("api_key") or "").strip():
                    extra_map["BRAVE_API_KEY"] = str(creds["api_key"]).strip()
            pm.upsert_service_credential(
                service=eff_vault_svc,
                username=str(creds.get("username") or ""),
                password=str(creds.get("password") or ""),
                api_key=str(creds.get("api_key") or ""),
                token=str(creds.get("token") or ""),
                cookie=str(creds.get("cookie") or ""),
                url=dom_url if dom_url else "",
                extra=extra_map or None,
            )

        reg = self.list_registry()
        return {**reg, "provider_id": eff_id}

    def reorder_providers(self, category_id: str, ordered_ids: list[str]) -> dict[str, Any]:
        self._require_unlocked()
        cid = (category_id or "").strip().lower()
        clean_ids = [str(x).strip() for x in (ordered_ids or []) if str(x).strip()]
        with self.runtime.store_lock:
            conn = self.runtime.store.db
            ensure_provider_tables_on_conn(conn)
            cur_rows = conn.execute(
                "SELECT id FROM satz_provider_entries WHERE category_id = ? ORDER BY priority ASC",
                (cid,),
            ).fetchall()
            cur_list = [str(r["id"]) for r in cur_rows]
            final_order = [pid for pid in clean_ids if pid in cur_list] + [pid for pid in cur_list if pid not in clean_ids]
            now = time.time()
            for idx, pid in enumerate(final_order, 1):
                conn.execute(
                    "UPDATE satz_provider_entries SET priority = ?, updated_at = ? WHERE id = ? AND category_id = ?",
                    (idx, now, pid, cid),
                )
            conn.commit()
        return self.list_registry()

    def delete_provider(self, provider_id: str, *, delete_credentials: bool = False) -> dict[str, Any]:
        self._require_unlocked()
        pid = (provider_id or "").strip()
        if not pid:
            raise ValueError("provider_id is required.")
        vault_svc = ""
        cid = ""
        with self.runtime.store_lock:
            conn = self.runtime.store.db
            ensure_provider_tables_on_conn(conn)
            row = conn.execute(
                "SELECT category_id, vault_service FROM satz_provider_entries WHERE id = ?",
                (pid,),
            ).fetchone()
            if not row:
                return {"ok": False, "error": f"Provider '{pid}' not found."}
            cid = str(row["category_id"])
            vault_svc = str(row["vault_service"] or "")
            conn.execute("DELETE FROM satz_provider_entries WHERE id = ?", (pid,))
            self._renumber_priorities(conn, cid)
            conn.commit()
        if delete_credentials and vault_svc:
            pm = getattr(self.runtime, "passwords", None)
            if pm is not None and pm.unlocked:
                try:
                    pm.delete_service_credential(vault_svc)
                except Exception:
                    pass
        return self.list_registry()

    def get_api_key_for_provider(self, entry: dict[str, Any]) -> str:
        """Resolves API key strictly from active unlocked `vault.enc` (with env fallback only for BRAVE_API_KEY)."""
        pm = getattr(self.runtime, "passwords", None)
        slug = str(entry.get("provider_slug") or "").lower()
        vault_svc = str(entry.get("vault_service") or "").upper()
        preset = self._preset_meta(slug, str(entry.get("category_id") or ""))
        alt_keys = list(preset.get("alt_env_keys") or [])
        if pm is not None and pm.unlocked and hasattr(pm, "get_provider_secret"):
            sec = pm.get_provider_secret(vault_svc, field="api_key", alt_keys=alt_keys)
            if sec:
                return sec
        driver = str(entry.get("api_driver") or slug or "").lower()
        if driver == "brave":
            return (os.environ.get("BRAVE_API_KEY") or "").strip()
        return ""

    def get_ordered_search_backends(self) -> list[dict[str, Any]]:
        """Returns ordered enabled `search_api` providers for `search.general`, always ending with local `ddgs` fallback."""
        with self.runtime.store_lock:
            conn = self.runtime.store.db
            ensure_provider_tables_on_conn(conn)
            rows = conn.execute(
                """
                SELECT * FROM satz_provider_entries
                WHERE category_id = 'search.general' AND enabled = 1 AND mode = 'search_api'
                ORDER BY priority ASC, created_at ASC
                """
            ).fetchall()
        enriched = [self._enrich_provider_row(r) for r in rows]
        if not any(str(e.get("api_driver") or "") == "ddgs" for e in enriched):
            enriched.append(
                {
                    "id": "builtin_ddgs_fallback",
                    "category_id": "search.general",
                    "provider_slug": "ddgs",
                    "display_name": "DuckDuckGo",
                    "mode": "search_api",
                    "api_driver": "ddgs",
                    "domains": ["duckduckgo.com"],
                    "url_template": "https://duckduckgo.com/?q={query}",
                    "vault_service": "DDGS",
                    "constraints_note": "",
                    "priority": len(enriched) + 1,
                    "enabled": True,
                    "requires_key": False,
                    "auth_ready": False,
                }
            )
        return enriched

    def resolve_for_intent(
        self,
        *,
        category: str = "",
        intent: str = "",
        query: str = "",
    ) -> dict[str, Any]:
        """Resolves category + prioritized providers + ready `{query}` search URLs + DomainRecipe hints."""
        with self.runtime.store_lock:
            conn = self.runtime.store.db
            ensure_provider_tables_on_conn(conn)
            cat_rows = conn.execute(
                "SELECT category_id, parent_group, label, description, is_builtin, sort_order FROM satz_provider_categories ORDER BY sort_order ASC"
            ).fetchall()

        cats = [dict(r) for r in cat_rows]
        req_cat = (category or "").strip().lower()
        raw_intent = (intent or "").strip().lower()

        matched_cat: dict[str, Any] | None = None
        if req_cat:
            matched_cat = next(
                (c for c in cats if c["category_id"].lower() == req_cat or c["label"].lower() == req_cat),
                None,
            )
        if matched_cat is None:
            hay = f"{req_cat} {raw_intent} {(query or '').lower()}".strip()
            best_score = 0
            for c in cats:
                cid = c["category_id"].lower()
                sc = 0
                if cid == hay or c["label"].lower() in hay:
                    sc += 5
                for kw in CATEGORY_INTENT_KEYWORDS.get(cid, ()):
                    if kw in hay:
                        sc += 3
                for tok in re.findall(r"[a-z0-9]{3,}", f"{c['label']} {c['description']}".lower()):
                    if tok in hay:
                        sc += 2
                if sc > best_score:
                    best_score = sc
                    matched_cat = c

        if matched_cat is None:
            matched_cat = next((c for c in cats if c["category_id"] == "search.general"), cats[0] if cats else None)
        if not matched_cat:
            return {"ok": False, "error": "No provider categories configured."}

        cid = str(matched_cat["category_id"])
        with self.runtime.store_lock:
            prov_rows = self.runtime.store.db.execute(
                """
                SELECT * FROM satz_provider_entries
                WHERE category_id = ? AND enabled = 1
                ORDER BY priority ASC, created_at ASC
                """,
                (cid,),
            ).fetchall()

        recipes_mod = getattr(self.runtime, "recipes", None)
        out_provs: list[dict[str, Any]] = []
        for pr in prov_rows:
            item = self._enrich_provider_row(pr)
            q_eff = (query or "").strip()
            item["search_url"] = format_provider_search_url(item["url_template"], q_eff)
            if recipes_mod is not None and item["domains"]:
                try:
                    recs = recipes_mod.list_recipes(domain=item["domains"][0], limit=3)
                    if recs:
                        item["known_controls"] = [
                            {"control_key": rc["control_key"], "label": rc["label"], "action_kind": rc["action_kind"]}
                            for rc in recs
                        ]
                except Exception:
                    pass
            out_provs.append(item)

        return {
            "ok": True,
            "category": {
                "category_id": cid,
                "parent_group": str(matched_cat["parent_group"]),
                "label": str(matched_cat["label"]),
                "description": str(matched_cat["description"]),
            },
            "providers": out_provs,
            "curated_presets": CURATED_PROVIDER_PRESETS.get(cid, []),
        }

    def get_prompt_routing_hint(self, max_chars: int = 420) -> str:
        """Concise non-secret summary of active user defaults for system addenda (`<=420 chars`)."""
        pm = getattr(self.runtime, "passwords", None)
        if pm is not None and not pm.unlocked:
            return ""
        with self.runtime.store_lock:
            conn = self.runtime.store.db
            ensure_provider_tables_on_conn(conn)
            rows = conn.execute(
                """
                SELECT p.*, c.label AS cat_label
                FROM satz_provider_entries p
                JOIN satz_provider_categories c ON c.category_id = p.category_id
                WHERE p.enabled = 1
                ORDER BY c.sort_order ASC, p.priority ASC
                """
            ).fetchall()

        by_cat: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            item = self._enrich_provider_row(r)
            item["cat_label"] = str(r["cat_label"])
            by_cat.setdefault(item["category_id"], []).append(item)

        parts: list[str] = []
        for cid, plist in by_cat.items():
            # Skip uncustomized default-only general search so idle prompts stay ultra short.
            if cid == "search.general" and len(plist) == 1 and plist[0]["provider_slug"] == "ddgs":
                continue
            top_strs = []
            for idx, p in enumerate(plist[:2], 1):
                auth_tag = " [vault]" if p["auth_ready"] else ""
                dom = p["domains"][0] if p["domains"] else p["display_name"]
                top_strs.append(f"#{idx} {dom}{auth_tag}")
            parts.append(f"{cid}: {', '.join(top_strs)}")

        if not parts:
            return ""
        summary = " | ".join(parts)
        return summary[:max_chars]

    def test_provider(self, provider_id: str, sample_query: str = "winter jacket") -> dict[str, Any]:
        pid = (provider_id or "").strip()
        with self.runtime.store_lock:
            conn = self.runtime.store.db
            ensure_provider_tables_on_conn(conn)
            row = conn.execute("SELECT * FROM satz_provider_entries WHERE id = ?", (pid,)).fetchone()
        if not row:
            return {"ok": False, "error": f"Provider '{pid}' not found."}
        item = self._enrich_provider_row(row)
        preview_url = format_provider_search_url(item["url_template"], sample_query)
        mode = item["mode"]
        if mode == "search_api" and item["requires_key"]:
            key_val = self.get_api_key_for_provider(item)
            if not key_val:
                return {
                    "ok": False,
                    "provider_id": pid,
                    "preview_url": preview_url,
                    "auth_status": item["auth_status"],
                    "error": f"Missing API key in vault.enc ({item['vault_service']}_API_KEY).",
                }
            return {
                "ok": True,
                "provider_id": pid,
                "preview_url": preview_url,
                "auth_status": item["auth_status"],
                "message": f"API key ready ({item['masked_auth_label']}); template verified.",
            }
        return {
            "ok": True,
            "provider_id": pid,
            "preview_url": preview_url,
            "auth_status": item["auth_status"],
            "message": f"Ready ({preview_url or (item['domains'][0] if item['domains'] else item['display_name'])})"
            + (f" · vault: {item['masked_auth_label']}" if item["auth_ready"] else " · no credentials needed"),
        }

    def upsert_suggestion(
        self,
        *,
        category_id: str,
        domain: str,
        display_name: str = "",
        reason: str = "",
        evidence_count: int = 3,
    ) -> dict[str, Any] | None:
        clean_dom = _clean_host(domain)
        cid = (category_id or "").strip().lower()
        if not clean_dom or not cid:
            return None
        sug_id = f"sug_{_slugify(cid, 20)}_{_slugify(clean_dom, 28)}"
        now = time.time()
        preset = find_preset_match(clean_dom, category_id=cid)
        slug = str((preset or {}).get("provider_slug") or _slugify(clean_dom.split(".")[0]))
        eff_name = (display_name or (preset or {}).get("display_name") or clean_dom.split(".")[0].title()).strip()
        tpl = str((preset or {}).get("url_template") or f"https://{clean_dom}")

        with self.runtime.store_lock:
            conn = self.runtime.store.db
            ensure_provider_tables_on_conn(conn)
            # Don't suggest if already #1 in this category or previously dismissed/accepted
            top_row = conn.execute(
                "SELECT domains_json, provider_slug FROM satz_provider_entries WHERE category_id = ? AND priority = 1 LIMIT 1",
                (cid,),
            ).fetchone()
            if top_row:
                if str(top_row["provider_slug"] or "") == slug or clean_dom in str(top_row["domains_json"] or ""):
                    return None
            ex = conn.execute(
                "SELECT status FROM satz_provider_suggestions WHERE suggestion_id = ?",
                (sug_id,),
            ).fetchone()
            if ex and str(ex["status"]) in ("dismissed", "accepted"):
                return None
            conn.execute(
                """
                INSERT INTO satz_provider_suggestions
                  (suggestion_id, category_id, provider_slug, display_name, domain, url_template, reason, evidence_count, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                ON CONFLICT(suggestion_id) DO UPDATE SET
                  evidence_count = MAX(satz_provider_suggestions.evidence_count, excluded.evidence_count),
                  reason = excluded.reason,
                  updated_at = excluded.updated_at
                """,
                (sug_id, cid, slug, eff_name, clean_dom, tpl, reason[:240], int(evidence_count), now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM satz_provider_suggestions WHERE suggestion_id = ?",
                (sug_id,),
            ).fetchone()
        return dict(row) if row else None

    def resolve_suggestion(self, suggestion_id: str, action: str = "accept") -> dict[str, Any]:
        self._require_unlocked()
        sid = (suggestion_id or "").strip()
        act = (action or "accept").strip().lower()
        if not sid:
            return {"ok": False, "error": "suggestion_id is required."}
        with self.runtime.store_lock:
            conn = self.runtime.store.db
            ensure_provider_tables_on_conn(conn)
            row = conn.execute(
                "SELECT * FROM satz_provider_suggestions WHERE suggestion_id = ?",
                (sid,),
            ).fetchone()
            if not row:
                return {"ok": False, "error": f"Suggestion '{sid}' not found."}
            rec = dict(row)
            new_status = "accepted" if act == "accept" else "dismissed"
            conn.execute(
                "UPDATE satz_provider_suggestions SET status = ?, updated_at = ? WHERE suggestion_id = ?",
                (new_status, time.time(), sid),
            )
            conn.commit()

        if act == "accept":
            return self.upsert_provider(
                category_id=str(rec["category_id"]),
                display_name=str(rec["display_name"]),
                provider_slug=str(rec["provider_slug"]),
                domains=[str(rec["domain"])],
                url_template=str(rec.get("url_template") or f"https://{rec['domain']}"),
                priority=1,
                auto_learned=True,
            )
        return self.list_registry()
