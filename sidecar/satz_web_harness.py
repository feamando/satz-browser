"""
Web Search Harness for Cloud & Chat Models in Satz Browser.

Provides:
1. Conversational web-search intent & anaphora resolution (`is_explicit_web_search_request`,
   `resolve_web_search_query`) so follow-ups like "can you do a web search for that then?"
   search the actual topic from conversation history rather than literal filler words.
2. Snippet-resilient search + polite page fetching (`WebSearchSessionHarness`) with PII
   scrubbing, noise filtering ("How to Search the Internet" / support pages), trusted
   source tagging, and synchronized registration into turn `hydrated_sources`, `source_stats`,
   `cited_web_sources`, and `satz_sources` for deterministic citation checks & page previews.
3. Multi-provider native tool-calling loop (`web_search`, `fetch_webpage`) across Gemini,
   Anthropic, OpenAI, and Mistral, with SSE heartbeats/status progress, Gemini
   `thoughtSignature` preservation, non-tool fallback on HTTP 400, and clean date disclosure.
"""

from __future__ import annotations

import json
import queue
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import nullcontext
from datetime import datetime
from typing import Any, Callable


MAX_CLOUD_TOOL_ROUNDS = 4
CLOUD_HTTP_TIMEOUT_S = 28.0
DEFAULT_WEB_SEARCH_RESULTS = 5
MAX_WEB_SEARCH_RESULTS = 8
AUTO_FETCH_TOP_N = 2


WEB_SEARCH_TOOLS_SPEC: list[dict[str, Any]] = [
    {
        "name": "web_search",
        "description": (
            "Search the live public web using Satz's search engine for current events, real-time prices, "
            "market movers, weather, documentation, and websites. Always pass a concise, self-contained topic "
            "query with key entities/dates (never meta phrases like 'do a web search' or pronouns like 'that'). "
            "Each returned item includes a `cite_tag` like '[1]' or '[2]' registered in SOURCES."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Self-contained web search query (entities, keywords, dates, domains).",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum search results to return (1-8, default 5).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_webpage",
        "description": (
            "Fetch and extract the full readable text of a specific public http(s) URL returned by web_search "
            "or mentioned by the user, upgrading or adding its numbered `cite_tag` in SOURCES."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Public http:// or https:// URL to fetch and read.",
                },
            },
            "required": ["url"],
        },
    },
]


_EXPLICIT_WEB_RE = re.compile(
    r"\b("
    r"web\s+search|"
    r"search\s+(?:on\s+)?the\s+web|"
    r"do\s+(?:a\s+)?(?:quick\s+)?(?:web\s+)?search|"
    r"run\s+(?:a\s+)?(?:web\s+)?search|"
    r"search\s+online|"
    r"check\s+(?:that\s+|it\s+|this\s+)?online|"
    r"look\s+(?:that|it|this)?\s*up\s+online|"
    r"google\s+(?:that|it|this|for)|"
    r"browse\s+the\s+web|"
    r"find\s+(?:that|it|this)?\s*online"
    r")\b",
    re.IGNORECASE,
)

_AFFIRMATIVE_REPLY_RE = re.compile(
    r"^\s*(?:(?:yes|yeah|yep|sure|ok|okay)(?:\s*[,\s]+)?(?:please(?:\s+do)?|do\s+(?:that|it)|go\s+ahead|search\s+for\s+(?:that|it|this)(?:\s+then)?)?|"
    r"please(?:\s+do)?|do\s+(?:that|it)|go\s+ahead|search\s+for\s+(?:that|it|this)(?:\s+then)?)[.!?]*\s*$",
    re.IGNORECASE,
)

_ASSISTANT_SUGGESTED_WEB_RE = re.compile(
    r"\b(real-?time|live\s+(?:web|data|search)|web\s+search|turn\s+on\s+\[?\+?\s*web\]?|search\s+online|don't\s+have\s+(?:live|real-?time|current))\b",
    re.IGNORECASE,
)

_META_PREFIX_RE = re.compile(
    r"^\s*(?:can\s+you\s+|could\s+you\s+|would\s+you\s+|please\s+|just\s+|okay,?\s+|then\s+)*"
    r"(?:do\s+(?:a\s+)?(?:quick\s+)?(?:web\s+)?search(?:\s+online)?(?:\s+(?:for|about|on))?|"
    r"run\s+(?:a\s+)?(?:web\s+)?search(?:\s+(?:for|about|on))?|"
    r"search\s+(?:on\s+)?the\s+web(?:\s+(?:for|about|on))?|"
    r"search\s+online(?:\s+(?:for|about|on))?|"
    r"look\s+up(?:\s+online)?|"
    r"web\s+search\s*[:\-]?\s*(?:for)?|"
    r"google(?:\s+for)?)\s*",
    re.IGNORECASE,
)

_ANAPHORA_ONLY_RE = re.compile(
    r"^(?:that|this|it|them|those|these|the\s+same|that\s+topic|the\s+above)"
    r"(?:\s+(?:then|now|again|please|for\s+me))*[?.!]*$",
    re.IGNORECASE,
)

_BOT_BLOCK_MARKERS = (
    "access denied",
    "you don't have permission to access",
    "enable javascript and cookies to continue",
    "checking if the site connection is secure",
    "just a moment...",
    "403 forbidden",
)

_HOWTO_SEARCH_NOISE_HOSTS = (
    "support.google.com/websearch",
    "support.google.com/chrome/answer/95440",
    "google.com/advanced_search",
    "wikihow.com/search",
)


def is_explicit_web_search_request(
    user_msg: str,
    prior_messages: list[dict[str, str]] | None = None,
) -> bool:
    """Return True when the user explicitly requests a live web search (even if web toggle is off)."""
    txt = (user_msg or "").strip()
    if not txt:
        return False
    if _EXPLICIT_WEB_RE.search(txt):
        return True
    if _AFFIRMATIVE_REPLY_RE.match(txt) and prior_messages:
        for pm in reversed(prior_messages):
            if pm.get("role") == "assistant":
                return bool(_ASSISTANT_SUGGESTED_WEB_RE.search(str(pm.get("content") or "")))
    return False


def _strip_question_scaffolding(raw: str) -> str:
    cleaned = str(raw or "").strip()
    cleaned = _META_PREFIX_RE.sub("", cleaned).strip()
    cleaned = re.sub(
        r"^(?:what\s+(?:are|is|were)\s+(?:the\s+)?|tell\s+me\s+(?:about\s+)?|give\s+me\s+(?:the\s+)?|"
        r"can\s+you\s+tell\s+me\s+(?:about\s+)?|could\s+you\s+(?:find|check)\s+)",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    cleaned = re.sub(r"\s+(?:then|please)[?.!]*$", "", cleaned, flags=re.IGNORECASE).strip(" ?.!")
    return cleaned


def resolve_web_search_query(
    user_msg: str,
    prior_messages: list[dict[str, str]] | None = None,
) -> str:
    """
    Converts conversational/anaphoric web-search prompts (e.g. 'can you do a web search for that then?')
    into a clean self-contained topic query resolved against prior conversation turns.
    """
    candidate = _strip_question_scaffolding(user_msg)
    if candidate and not _ANAPHORA_ONLY_RE.match(candidate) and len(candidate) >= 4:
        return candidate[:180]

    for pm in reversed(prior_messages or []):
        if pm.get("role") != "user":
            continue
        p_txt = str(pm.get("content") or "").strip()
        if not p_txt:
            continue
        p_clean = _strip_question_scaffolding(p_txt)
        if p_clean and not _ANAPHORA_ONLY_RE.match(p_clean) and len(p_clean) >= 4:
            return p_clean[:180]

    fallback = str(user_msg or "").strip()
    return fallback[:180]


def _is_bot_blocked_text(text: str) -> bool:
    head = (text or "")[:500].lower()
    return any(marker in head for marker in _BOT_BLOCK_MARKERS)


def _is_search_howto_noise(url: str, title: str, clean_query: str) -> bool:
    q_low = (clean_query or "").lower()
    if any(tok in q_low for tok in ("how to search", "wikihow", "google advanced", "search syntax")):
        return False
    u_low = (url or "").lower()
    t_low = (title or "").lower()
    if any(h in u_low for h in _HOWTO_SEARCH_NOISE_HOSTS):
        return True
    if "how to search the internet" in t_low or "google advanced search" in t_low:
        return True
    return False


def build_cloud_web_system_addendum(allow_web_tools: bool) -> str:
    """Returns a concise system-instruction addendum explaining live web harness availability + today's date."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    if allow_web_tools:
        return (
            f"CLOUD WEB SEARCH HARNESS ACTIVE (current local date: {today_str}):\n"
            "- You have live `web_search(query, max_results)` and `fetch_webpage(url)` tools wired into the Satz browser.\n"
            "- If the user asks about live/recent events, today's news, stocks/prices, weather, schedules, or asks to search online, "
            "and those facts are not already in SOURCES, invoke `web_search` with a clean, self-contained query "
            "(resolve pronouns like 'that' or 'it' from CONVERSATION HISTORY; never search meta words like 'do a web search').\n"
            "- Every result returned by `web_search` or `fetch_webpage` is registered into SOURCES under its `cite_tag` (`[1]`, `[2]`, ...). "
            "You MUST cite retrieved facts inline using those exact `[n]` numbers (format source links as `[Title](url) [n]`, and keep facts from different sources on separate bullets or sentences so each `[n]` matches that source cleanly).\n"
            "- If a snippet looks truncated or high-value, call `fetch_webpage(url)` to inspect more detail. "
            "Never state that your environment lacks a web search tool, and never invent figures or claims not present in retrieved snippets/excerpts."
        )
    return (
        f"LIVE WEB SEARCH STATUS (current local date: {today_str}):\n"
        "- Live `web_search` is currently paused because the user's `[web: off]` privacy toggle is off.\n"
        "- Answer from open browser tabs in SOURCES, SATZ BRAIN KNOWLEDGE BASE (`[B1]`, ...), or conversation history when available. "
        "If live/real-time web information is needed and missing, tell the user clearly that web search is paused (`web: off`) and they can click `[web: on]` or reply asking you to search the web "
        "(do not claim your environment permanently lacks a web search tool)."
    )


class WebSearchSessionHarness:
    """Maintains per-turn source numbering and executes `web_search` / `fetch_webpage` safely."""

    def __init__(
        self,
        runtime: Any,
        *,
        combined_sources: list[dict[str, Any]],
        hydrated_sources: list[dict[str, Any]],
        used_source_ids: list[str],
        cited_web_sources: list[dict[str, str]],
        source_stats_list: list[dict[str, Any]],
        status_cb: Callable[[str, str], None] | None = None,
    ) -> None:
        self.runtime = runtime
        self.combined_sources = combined_sources
        self.hydrated_sources = hydrated_sources
        self.used_source_ids = used_source_ids
        self.cited_web_sources = cited_web_sources
        self.source_stats_list = source_stats_list
        self.status_cb = status_cb

        self.search_calls = 0
        self.fetch_calls = 0
        self.max_searches = 4
        self.max_fetches = 6

    def _emit_status(self, msg: str, phase: str = "web_search") -> None:
        if self.status_cb:
            try:
                self.status_cb(msg, phase)
            except Exception:
                pass

    def _find_hydrated_index(self, url: str) -> int | None:
        target = (url or "").strip()
        for idx, hs in enumerate(self.hydrated_sources):
            if str(hs.get("url") or "").strip() == target:
                return idx
        return None

    def register_or_update_source(
        self,
        *,
        url: str,
        title: str,
        domain: str,
        snippet: str,
        fetched_text: str,
        capture_mode: str,
        findings: list[dict[str, Any]] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """
        Adds or upgrades a web source in `hydrated_sources` so `[n]` citations,
        `check_citations()`, `page previews`, and `source_stats` stay 100% consistent.
        Returns `(1_based_index, source_entry)`.
        """
        from satz_brain import neutralize_brain_directives_in_source

        clean_url = (url or "").strip()
        clean_title = (title or domain or clean_url).strip()
        clean_domain = (domain or "").strip()
        clean_snippet = neutralize_brain_directives_in_source((snippet or "").strip())
        clean_body = neutralize_brain_directives_in_source((fetched_text or "").strip())

        header = f"{clean_title} ({clean_domain})\nURL: {clean_url}".strip()
        if clean_snippet and clean_body and clean_snippet[:60].lower() not in clean_body[:400].lower():
            full_text = f"{header}\nSnippet: {clean_snippet}\n\n{clean_body}"
        elif clean_body:
            full_text = f"{header}\n\n{clean_body}"
        else:
            full_text = f"{header}\nSnippet: {clean_snippet}".strip()

        excerpt = full_text[:2800]
        findings_list = list(findings or [])

        existing_idx = self._find_hydrated_index(clean_url)
        if existing_idx is not None:
            entry = self.hydrated_sources[existing_idx]
            if len(full_text) > len(str(entry.get("full_text") or "")):
                entry["title"] = clean_title or entry.get("title") or clean_url
                entry["text"] = excerpt
                entry["full_text"] = full_text
                entry["chars_captured"] = len(full_text)
                entry["chars_sent"] = len(excerpt)
                entry["was_cut"] = len(full_text) > len(excerpt)
                entry["capture_mode"] = capture_mode
                if findings_list and not entry.get("findings"):
                    entry["findings"] = findings_list
                for st in self.source_stats_list:
                    if st.get("id") == entry["id"]:
                        st["chars_captured"] = entry["chars_captured"]
                        st["chars_sent"] = entry["chars_sent"]
                        st["was_cut"] = entry["was_cut"]
                        st["capture_mode"] = capture_mode
                        break
            return existing_idx + 1, entry

        entry = {
            "id": clean_url,
            "url": clean_url,
            "title": clean_title,
            "domain": clean_domain,
            "text": excerpt,
            "full_text": full_text,
            "chars_captured": len(full_text),
            "chars_sent": len(excerpt),
            "was_cut": len(full_text) > len(excerpt),
            "capture_mode": capture_mode,
            "is_open_tab": False,
            "findings": findings_list,
        }
        self.hydrated_sources.append(entry)
        self.used_source_ids.append(clean_url)
        self.source_stats_list.append(
            {
                "id": clean_url,
                "chars_captured": entry["chars_captured"],
                "chars_sent": entry["chars_sent"],
                "was_cut": entry["was_cut"],
                "capture_mode": capture_mode,
            }
        )
        if not any(cs.get("url") == clean_url for cs in self.combined_sources):
            self.combined_sources.append(
                {
                    "id": clean_url,
                    "url": clean_url,
                    "title": clean_title,
                    "domain": clean_domain,
                    "is_open_tab": False,
                }
            )
        if not any(cw.get("url") == clean_url for cw in self.cited_web_sources):
            self.cited_web_sources.append({"url": clean_url, "title": clean_title})

        self._cache_source_in_store(clean_url, clean_domain, clean_title, full_text, findings_list, capture_mode)
        return len(self.hydrated_sources), entry

    def _cache_source_in_store(
        self,
        url: str,
        domain: str,
        title: str,
        text: str,
        findings: list[dict[str, Any]],
        capture_mode: str,
    ) -> None:
        now = time.time()
        try:
            with self.runtime.store_lock:
                self.runtime.store.db.execute(
                    """
                    INSERT INTO satz_sources
                      (source_id, conversation_id, url, domain, title, text, extra_json, findings_json, capture_mode, updated_at)
                    VALUES (?, 'chat-web', ?, ?, ?, ?, '[]', ?, ?, ?)
                    ON CONFLICT(source_id) DO UPDATE SET
                      title = CASE WHEN length(excluded.title) > 0 THEN excluded.title ELSE satz_sources.title END,
                      text = CASE WHEN length(excluded.text) > length(satz_sources.text) THEN excluded.text ELSE satz_sources.text END,
                      findings_json = CASE WHEN excluded.findings_json != '[]' THEN excluded.findings_json ELSE satz_sources.findings_json END,
                      capture_mode = excluded.capture_mode,
                      updated_at = excluded.updated_at
                    """,
                    (url, url, domain, title, text[:120000], json.dumps(findings[:8], ensure_ascii=False), capture_mode, now),
                )
                self.runtime.store.db.commit()
        except Exception as exc:
            self.runtime.record_error("web_harness_cache", exc)

    def _polite_fetch_url(self, url: str) -> tuple[str, list[dict[str, Any]], str]:
        """Returns `(extracted_text, findings, title_override)` or `("", [], "")` if blocked/empty."""
        from src.planck3.web import domain_of, extract_jsonld, extract_main_text

        web_lock = getattr(self.runtime, "web_lock", None) or nullcontext()
        try:
            with web_lock:
                page = self.runtime.web.fetch(url)
        except Exception as exc:
            self.runtime.record_error("web_harness_fetch", f"{url}: {exc}")
            return "", [], ""

        html = str(page.get("html") or "")
        if not html.strip():
            return "", [], ""

        extracted = extract_main_text(html, url) or ""
        if not extracted.strip() or _is_bot_blocked_text(extracted):
            return "", [], ""

        extras = extract_jsonld(html)
        if extras:
            extracted = f"{extracted}\n\n" + "\n".join(extras[:6])

        title_override = ""
        m_t = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        if m_t:
            title_override = re.sub(r"\s+", " ", m_t.group(1)).strip()[:160]

        findings = []
        try:
            findings = self.runtime._extract_findings_from_html(html, url, title_override or domain_of(url))
        except Exception:
            findings = []

        return extracted[:24000], findings, title_override

    def execute_web_search(self, query: str, max_results: int = DEFAULT_WEB_SEARCH_RESULTS) -> dict[str, Any]:
        """Runs PII-scrubbed live search + resilient top-result fetch, returning `[n]`-tagged results."""
        from src.planck3.web import domain_of

        if self.search_calls >= self.max_searches:
            return {"ok": False, "error": "Per-turn search budget reached; answer from gathered SOURCES.", "results": []}
        self.search_calls += 1

        raw_q = (query or "").strip()
        if not raw_q:
            return {"ok": False, "error": "Empty search query.", "results": []}

        scrubbed_q = self.runtime.brain.scrub_pii_for_external_query(raw_q).strip() or raw_q
        try:
            limit = max(1, min(int(float(max_results or DEFAULT_WEB_SEARCH_RESULTS)), MAX_WEB_SEARCH_RESULTS))
        except (TypeError, ValueError):
            limit = DEFAULT_WEB_SEARCH_RESULTS
        self._emit_status(f"searching web for '{scrubbed_q[:52]}'...", "web_search")

        web_lock = getattr(self.runtime, "web_lock", None) or nullcontext()
        try:
            with web_lock:
                raw_results = list(self.runtime.web.search(scrubbed_q) or [])
                backend_used = str(getattr(self.runtime.web, "last_backend", "") or getattr(self.runtime.web, "backend", "ddgs"))
        except Exception as exc:
            self.runtime.record_error("web_harness_search", exc)
            return {"ok": False, "error": str(exc), "query_used": scrubbed_q, "results": []}

        filtered = [
            r
            for r in raw_results
            if r.get("url") and not _is_search_howto_noise(str(r.get("url") or ""), str(r.get("title") or ""), scrubbed_q)
        ]
        chosen = (filtered or raw_results)[:limit]

        out_results: list[dict[str, Any]] = []
        fetched_count = 0
        for item in chosen:
            url = str(item.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            dom = str(item.get("domain") or domain_of(url) or "").strip()
            title = str(item.get("title") or dom or url).strip()
            snippet = str(item.get("snippet") or "").strip()

            fetched_txt = ""
            findings: list[dict[str, Any]] = []
            if fetched_count < AUTO_FETCH_TOP_N:
                fetched_txt, findings, title_ov = self._polite_fetch_url(url)
                if title_ov and len(title_ov) > len(title):
                    title = title_ov
                fetched_count += 1

            cap_mode = "fetch" if fetched_txt else "snippet"
            if not fetched_txt and not snippet:
                continue

            cite_idx, entry = self.register_or_update_source(
                url=url,
                title=title,
                domain=dom,
                snippet=snippet,
                fetched_text=fetched_txt,
                capture_mode=cap_mode,
                findings=findings,
            )

            with self.runtime.store_lock:
                t_rec = self.runtime.store.trust(dom) if dom else {"effective": 5.0, "band": "low"}

            out_results.append(
                {
                    "cite_tag": f"[{cite_idx}]",
                    "url": url,
                    "domain": dom,
                    "title": title,
                    "snippet": snippet[:360],
                    "content_excerpt": str(entry.get("text") or "")[:1400],
                    "capture_mode": cap_mode,
                    "trust_effective": float(t_rec.get("effective", 5.0)),
                    "trust_band": str(t_rec.get("band") or "low"),
                }
            )

        return {
            "ok": True,
            "query_used": scrubbed_q,
            "search_backend": backend_used,
            "result_count": len(out_results),
            "results": out_results,
        }

    def execute_fetch_webpage(self, url: str) -> dict[str, Any]:
        """Fetches full readable content for an explicit `http(s)` URL and updates `SOURCES`."""
        from src.planck3.web import domain_of

        if self.fetch_calls >= self.max_fetches:
            return {"ok": False, "error": "Per-turn fetch budget reached; synthesize from gathered SOURCES."}
        self.fetch_calls += 1

        clean_u = (url or "").strip()
        if not clean_u.startswith(("http://", "https://")):
            return {"ok": False, "error": "URL must start with http:// or https://"}

        dom = domain_of(clean_u) or clean_u
        self._emit_status(f"reading webpage {dom}...", "web_search")

        extracted, findings, title_ov = self._polite_fetch_url(clean_u)
        if not extracted:
            return {
                "ok": False,
                "url": clean_u,
                "domain": dom,
                "error": "Could not extract page body (blocked by site bot-protection, robots.txt, or empty response).",
            }

        cite_idx, entry = self.register_or_update_source(
            url=clean_u,
            title=title_ov or dom,
            domain=dom,
            snippet="",
            fetched_text=extracted,
            capture_mode="fetch",
            findings=findings,
        )
        return {
            "ok": True,
            "cite_tag": f"[{cite_idx}]",
            "url": clean_u,
            "domain": dom,
            "title": str(entry.get("title") or dom),
            "content_excerpt": str(entry.get("full_text") or "")[:4500],
        }

    def _dispatch_tool_call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "web_search":
            return self.execute_web_search(
                query=str(args.get("query") or ""),
                max_results=int(args.get("max_results") or DEFAULT_WEB_SEARCH_RESULTS),
            )
        if name == "fetch_webpage":
            return self.execute_fetch_webpage(url=str(args.get("url") or ""))
        return {"ok": False, "error": f"Unknown tool: {name}"}

    def _json_post(self, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float = CLOUD_HTTP_TIMEOUT_S) -> dict[str, Any]:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))

    def _run_gemini_with_tools(
        self,
        slug: str,
        api_key: str,
        sys_text: str,
        user_prompt: str,
        allow_web_tools: bool,
    ) -> str:
        def _gemini_params_schema(params: dict[str, Any]) -> dict[str, Any]:
            type_map = {"object": "OBJECT", "string": "STRING", "integer": "INTEGER", "boolean": "BOOLEAN"}
            props = {
                k: {
                    "type": type_map.get(str(v.get("type", "string")).lower(), "STRING"),
                    "description": str(v.get("description") or ""),
                }
                for k, v in (params.get("properties") or {}).items()
            }
            return {
                "type": "OBJECT",
                "properties": props,
                "required": list(params.get("required") or []),
            }

        gemini_tools = (
            [
                {
                    "functionDeclarations": [
                        {
                            "name": t["name"],
                            "description": t["description"],
                            "parameters": _gemini_params_schema(t["parameters"]),
                        }
                        for t in WEB_SEARCH_TOOLS_SPEC
                    ]
                }
            ]
            if allow_web_tools
            else None
        )

        contents: list[dict[str, Any]] = [{"role": "user", "parts": [{"text": user_prompt}]}]
        candidate_slugs = [slug]
        for fb in ("gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3-flash-preview"):
            if fb not in candidate_slugs:
                candidate_slugs.append(fb)

        def _post_gemini(try_slug: str, cur_contents: list[dict[str, Any]], use_tools: bool) -> dict[str, Any]:
            payload: dict[str, Any] = {
                "contents": cur_contents,
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1800},
                "systemInstruction": {"parts": [{"text": sys_text}]},
            }
            if use_tools and gemini_tools:
                payload["tools"] = gemini_tools
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(try_slug)}:generateContent?key={urllib.parse.quote(api_key)}"
            return self._json_post(url, payload, {"Content-Type": "application/json"})

        active_slug = slug
        tools_enabled_here = bool(allow_web_tools)

        for _round in range(MAX_CLOUD_TOOL_ROUNDS + 1):
            is_final_forced = _round >= MAX_CLOUD_TOOL_ROUNDS
            use_tools_now = tools_enabled_here and not is_final_forced

            raw: dict[str, Any] | None = None
            last_err: Exception | None = None
            slugs_to_try = [active_slug] + [s for s in candidate_slugs if s != active_slug]
            for try_slug in slugs_to_try:
                try:
                    raw = _post_gemini(try_slug, contents, use_tools_now)
                    active_slug = try_slug
                    break
                except urllib.error.HTTPError as he:
                    last_err = he
                    err_body = ""
                    try:
                        err_body = he.read().decode("utf-8", errors="replace")[:320]
                    except Exception:
                        pass
                    if he.code == 400 and use_tools_now and any(k in err_body.lower() for k in ("tool", "function", "declaration")):
                        # Model slug does not support function declarations: fall back cleanly to deterministic search + plain prompt
                        tools_enabled_here = False
                        use_tools_now = False
                        fallback_block = self._fallback_presearch_note(user_prompt)
                        if fallback_block:
                            contents.append({"role": "user", "parts": [{"text": fallback_block}]})
                        try:
                            raw = _post_gemini(try_slug, contents, False)
                            active_slug = try_slug
                            break
                        except Exception as fb_exc:
                            last_err = fb_exc
                            continue
                    if he.code in (404, 429, 500, 503):
                        continue
                    raise RuntimeError(f"Gemini API error ({he.code} on {try_slug}): {err_body or he}") from he
                except Exception as exc:
                    last_err = exc
                    continue

            if raw is None:
                raise RuntimeError(f"Gemini request failed across candidate models ({slugs_to_try}): {last_err}")

            cands = raw.get("candidates") or []
            if not cands:
                raise RuntimeError(f"Gemini ({active_slug}) returned no candidates: {raw}")
            cand_content = cands[0].get("content") or {}
            parts = cand_content.get("parts") or []
            fn_calls = [p["functionCall"] for p in parts if isinstance(p, dict) and p.get("functionCall")]

            if fn_calls and not is_final_forced:
                # Preserve exact model `content` dict so Gemini 2.5+/3+/4 `thoughtSignature` stays intact!
                contents.append(cand_content)
                resp_parts = []
                for fc in fn_calls:
                    fname = str(fc.get("name") or "")
                    fargs = fc.get("args") if isinstance(fc.get("args"), dict) else {}
                    tool_out = self._dispatch_tool_call(fname, fargs)
                    resp_parts.append(
                        {
                            "functionResponse": {
                                "name": fname,
                                "response": {"result": tool_out},
                            }
                        }
                    )
                contents.append({"role": "user", "parts": resp_parts})
                self._emit_status(f"synthesizing answer from {len(self.hydrated_sources)} source(s)...", "generating")
                continue

            text_pieces = [
                str(p.get("text") or "")
                for p in parts
                if isinstance(p, dict) and p.get("text") and not p.get("thought")
            ]
            if not text_pieces:
                text_pieces = [str(p.get("text") or "") for p in parts if isinstance(p, dict) and p.get("text")]
            return "".join(text_pieces).strip()

        return ""

    def _run_anthropic_with_tools(
        self,
        slug: str,
        api_key: str,
        sys_text: str,
        user_prompt: str,
        allow_web_tools: bool,
    ) -> str:
        anth_tools = [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["parameters"],
            }
            for t in WEB_SEARCH_TOOLS_SPEC
        ]
        anth_msgs: list[dict[str, Any]] = [{"role": "user", "content": user_prompt}]
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        tools_enabled_here = bool(allow_web_tools)

        for _round in range(MAX_CLOUD_TOOL_ROUNDS + 1):
            is_final_forced = _round >= MAX_CLOUD_TOOL_ROUNDS
            payload: dict[str, Any] = {
                "model": slug,
                "max_tokens": 1800,
                "temperature": 0.2,
                "system": sys_text,
                "messages": anth_msgs,
            }
            if tools_enabled_here and not is_final_forced:
                payload["tools"] = anth_tools

            try:
                raw = self._json_post("https://api.anthropic.com/v1/messages", payload, headers, timeout=30.0)
            except urllib.error.HTTPError as he:
                err_body = ""
                try:
                    err_body = he.read().decode("utf-8", errors="replace")[:320]
                except Exception:
                    pass
                if he.code == 400 and "tools" in payload:
                    tools_enabled_here = False
                    payload.pop("tools", None)
                    fallback_block = self._fallback_presearch_note(user_prompt)
                    if fallback_block:
                        anth_msgs.append({"role": "user", "content": fallback_block})
                    raw = self._json_post("https://api.anthropic.com/v1/messages", payload, headers, timeout=30.0)
                else:
                    raise RuntimeError(f"Anthropic API error ({he.code}): {err_body or he}") from he

            blocks = raw.get("content") or []
            tool_uses = [b for b in blocks if isinstance(b, dict) and b.get("type") == "tool_use"]
            if tool_uses and not is_final_forced:
                anth_msgs.append({"role": "assistant", "content": blocks})
                tool_results = []
                for tu in tool_uses:
                    fname = str(tu.get("name") or "")
                    fargs = tu.get("input") if isinstance(tu.get("input"), dict) else {}
                    res = self._dispatch_tool_call(fname, fargs)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": str(tu.get("id") or ""),
                            "content": json.dumps(res, ensure_ascii=False),
                        }
                    )
                anth_msgs.append({"role": "user", "content": tool_results})
                self._emit_status(f"synthesizing answer from {len(self.hydrated_sources)} source(s)...", "generating")
                continue

            return "".join(str(b.get("text") or "") for b in blocks if isinstance(b, dict) and b.get("type") == "text").strip()

        return ""

    def _run_openai_compat_with_tools(
        self,
        provider_id: str,
        slug: str,
        api_key: str,
        sys_text: str,
        user_prompt: str,
        allow_web_tools: bool,
    ) -> str:
        endpoint = (
            "https://api.openai.com/v1/chat/completions"
            if provider_id == "openai"
            else "https://api.mistral.ai/v1/chat/completions"
        )
        oa_tools = [{"type": "function", "function": t} for t in WEB_SEARCH_TOOLS_SPEC]
        oa_msgs: list[dict[str, Any]] = [
            {"role": "system", "content": sys_text},
            {"role": "user", "content": user_prompt},
        ]
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        tools_enabled_here = bool(allow_web_tools)

        for _round in range(MAX_CLOUD_TOOL_ROUNDS + 1):
            is_final_forced = _round >= MAX_CLOUD_TOOL_ROUNDS
            payload: dict[str, Any] = {
                "model": slug,
                "messages": oa_msgs,
            }
            if not slug.lower().startswith(("o1", "o3", "o4")):
                payload["temperature"] = 0.2
            if tools_enabled_here and not is_final_forced:
                payload["tools"] = oa_tools
                payload["tool_choice"] = "auto"

            try:
                raw = self._json_post(endpoint, payload, headers, timeout=30.0)
            except urllib.error.HTTPError as he:
                err_body = ""
                try:
                    err_body = he.read().decode("utf-8", errors="replace")[:320]
                except Exception:
                    pass
                if he.code == 400 and "tools" in payload:
                    tools_enabled_here = False
                    payload.pop("tools", None)
                    payload.pop("tool_choice", None)
                    fallback_block = self._fallback_presearch_note(user_prompt)
                    if fallback_block:
                        oa_msgs.append({"role": "user", "content": fallback_block})
                    raw = self._json_post(endpoint, payload, headers, timeout=30.0)
                else:
                    raise RuntimeError(f"{provider_id} API error ({he.code}): {err_body or he}") from he

            choices = raw.get("choices") or []
            if not choices:
                raise RuntimeError(f"{provider_id} returned no choices: {raw}")
            msg = choices[0].get("message") or {}
            t_calls = msg.get("tool_calls") or []
            if t_calls and not is_final_forced:
                oa_msgs.append(
                    {
                        "role": "assistant",
                        "content": msg.get("content") or "",
                        "tool_calls": t_calls,
                    }
                )
                for tc in t_calls:
                    fn = tc.get("function") or {}
                    fname = str(fn.get("name") or "")
                    try:
                        fargs = json.loads(fn.get("arguments") or "{}")
                        if not isinstance(fargs, dict):
                            fargs = {}
                    except Exception:
                        fargs = {}
                    res = self._dispatch_tool_call(fname, fargs)
                    oa_msgs.append(
                        {
                            "role": "tool",
                            "tool_call_id": str(tc.get("id") or ""),
                            "name": fname,
                            "content": json.dumps(res, ensure_ascii=False),
                        }
                    )
                self._emit_status(f"synthesizing answer from {len(self.hydrated_sources)} source(s)...", "generating")
                continue

            return str(msg.get("content") or "").strip()

        return ""

    def _fallback_presearch_note(self, user_prompt: str) -> str:
        """Deterministic fallback search injection if a provider/model rejects native `tools` JSON."""
        m = re.search(r"USER REQUEST:\s*(.+)$", user_prompt, flags=re.DOTALL)
        q_raw = m.group(1).strip() if m else user_prompt[-200:]
        res = self.execute_web_search(q_raw, max_results=DEFAULT_WEB_SEARCH_RESULTS)
        if not res.get("ok") or not res.get("results"):
            return ""
        lines = [
            f"{r['cite_tag']} {r['domain']} ({r['title']}) - {r['url']}\n{r['content_excerpt'][:900]}"
            for r in res["results"]
        ]
        return "RETRIEVED WEB SOURCES:\n" + "\n\n".join(lines)

    def generate_cloud_response(
        self,
        model_id: str,
        chat_msgs: list[dict[str, str]],
        allow_web_tools: bool,
    ) -> str:
        """Executes the cloud chat turn synchronously (run in worker thread by `stream_cloud_chat`)."""
        parsed = self.runtime._parse_cloud_model_id(model_id)
        if not parsed:
            raise RuntimeError(f"Unsupported cloud model identifier: {model_id}")
        provider_id, slug = parsed
        api_key, _ = self.runtime._resolve_provider_api_key(provider_id)
        if not api_key:
            raise RuntimeError(
                f"{provider_id.upper()} API key not configured. Open [settings] -> [model management & cloud setup] and save your key to vault.enc."
            )

        sys_parts = [str(m.get("content") or "") for m in chat_msgs if m.get("role") == "system" and m.get("content")]
        sys_parts.append(build_cloud_web_system_addendum(allow_web_tools))
        sys_text = "\n\n".join(sys_parts).strip()
        user_prompt = "\n\n".join(
            str(m.get("content") or "") for m in chat_msgs if m.get("role") != "system" and m.get("content")
        ).strip() or "Hello"

        if provider_id == "gemini":
            out = self._run_gemini_with_tools(slug, api_key, sys_text, user_prompt, allow_web_tools)
        elif provider_id == "anthropic":
            out = self._run_anthropic_with_tools(slug, api_key, sys_text, user_prompt, allow_web_tools)
        elif provider_id in ("openai", "mistral"):
            out = self._run_openai_compat_with_tools(provider_id, slug, api_key, sys_text, user_prompt, allow_web_tools)
        else:
            raise RuntimeError(f"Unsupported cloud provider: {provider_id}")

        return out.replace("\u2014", "-").strip()


def stream_cloud_chat(
    harness: WebSearchSessionHarness,
    *,
    model_id: str,
    chat_msgs: list[dict[str, str]],
    allow_web_tools: bool,
):
    """
    Generator wrapping `harness.generate_cloud_response` with background execution + 5s SSE heartbeats
    so tool execution + HTTP calls never trip the frontend 30s stall timeout.
    Yields dicts `{phase, status}` / `{delta}` and stores final raw output in `result_box["text"]`.
    """
    ev_q: queue.Queue[dict[str, Any]] = queue.Queue()
    result_box: dict[str, Any] = {"text": "", "error": None}

    orig_cb = harness.status_cb

    def _q_status(msg: str, phase: str) -> None:
        ev_q.put({"status": msg, "phase": phase})
        if orig_cb:
            orig_cb(msg, phase)

    harness.status_cb = _q_status

    def _worker() -> None:
        try:
            result_box["text"] = harness.generate_cloud_response(
                model_id=model_id,
                chat_msgs=chat_msgs,
                allow_web_tools=allow_web_tools,
            )
        except Exception as exc:
            result_box["error"] = exc
        finally:
            ev_q.put({"__done": True})

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    while True:
        try:
            item = ev_q.get(timeout=5.0)
        except queue.Empty:
            yield {"phase": "heartbeat"}
            continue
        if item.get("__done"):
            break
        yield item

    t.join(timeout=5.0)
    harness.status_cb = orig_cb
    if result_box["error"] is not None:
        raise result_box["error"]

    full_raw = str(result_box["text"] or "")
    yield {"__full_raw": full_raw}
