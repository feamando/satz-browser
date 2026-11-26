"""
Deterministic web tools: search backends, polite fetch, main-text extraction.

Every search result and fetched page is cached on disk (sha1 of the key), so a
benchmark run can be replayed bit-identically after the live web changes.

Net modes:
    live     use cache if present, otherwise hit the network and cache it (default)
    replay   cache only; a miss is an empty result (the eval of record)
    refresh  always hit the network, overwrite the cache
"""

import hashlib
import html as html_lib
import json
import re
import time
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib import robotparser

from .util import append_jsonl, now_iso

USER_AGENT = "Planck3-research/0.1 (+https://github.com/feamando/sgs; personal research)"
FETCH_TIMEOUT = 15
MAX_HTML_BYTES = 3_000_000
MIN_SECONDS_PER_HOST = 1.0
MIN_SECONDS_BETWEEN_SEARCHES = 3.0   # upstream engines CAPTCHA bursts and SearXNG then suspends them for 24 h
MAX_CONSECUTIVE_EMPTY = 15           # circuit breaker: abort instead of producing a run of empty results
# ddgs (2026-10-08, round 4): metasearch library, no Docker. It scrapes (DuckDuckGo has no API),
# so it is a research backend, not a product one. Engines are tried in this fixed order (two at a
# time) until enough results come back, so one blocked engine is skipped, not fatal. On the Mac,
# ~15 test queries were enough for DuckDuckGo to answer HTTP 202 (its rate-limit page), Brave 429
# and Mojeek 403 while Bing and Yahoo still answered: blocks are fast and per engine. google is left
# out (it CAPTCHAs scripted clients). A block is RESPECTED: back off and fall back, never rotate
# identities or solve challenges.
DDGS_ENGINES = "duckduckgo,bing,brave,yahoo,mojeek"
RATE_LIMIT_BACKOFF = 30.0
SCRAPED_BACKENDS = ("ddgs", "searxng", "brave")  # general web search: empty -> retry once -> Wikipedia
# brave = the Brave Search API (licensed, keyed: BRAVE_API_KEY from .env). Opt-in (--search brave);
# round 4's pre-registered runs stay on ddgs. Its own pacing: the API meters requests per second.
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
MIN_SECONDS_BRAVE = 1.1
# Relevance (round 6): round 5's search check counted only EMPTY searches, so ddgs answers about
# xhamster.com and calculator.net passed as valid evidence for election questions. A search is now
# ON TOPIC when at least 2 of its top 5 results (1 if fewer come back) mention enough of the
# question's key words in title + snippet. Off-topic results are treated like an empty search: the
# next backend in the chain is tried, and only if nothing is on topic is the first answer served
# (counted as off topic). A run is valid only if most of its searches were on topic.
RELEVANCE_TOP = 5
ON_TOPIC_RUN_MIN = 0.6
_REL_SKIP = {"year", "years", "many", "much", "number", "exactly", "approximately", "roughly", "did", "does",
             "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
             "november", "december", "new", "first", "last", "current", "currently", "which", "name", "called"}


def query_keys(question: str) -> list[str]:
    """The words a result must mention to be about the question (no question-form, month or year words)."""
    from .util import content_words
    out = []
    for w in content_words(question):
        if len(w) > 2 and w not in _REL_SKIP and not re.fullmatch(r"\d{4}s?", w) and w not in out:
            out.append(w)
    return out


def result_on_topic(keys: list[str], result: dict) -> bool:
    from .util import norm_text
    if not keys:
        return True
    words = set(norm_text(f"{result.get('title', '')} {result.get('snippet', '')}").split())
    need = 1 if len(keys) <= 2 else 2 if len(keys) <= 5 else 3
    hits = sum(1 for k in keys if k in words or (len(k) >= 6 and any(w.startswith(k[:5]) for w in words)))
    return hits >= need


def on_topic(question: str, results: list[dict]) -> bool:
    keys = query_keys(question)
    top = results[:RELEVANCE_TOP]
    return bool(top) and sum(result_on_topic(keys, r) for r in top) >= min(2, len(top))


class SearchUnavailable(RuntimeError):
    """Search keeps coming back empty even after fallback: the run must stop, not continue blind."""


class WebCache:
    def __init__(self, root: str | Path, mode: str = "live"):
        assert mode in ("live", "replay", "refresh"), mode
        self.root = Path(root)
        self.mode = mode
        (self.root / "pages").mkdir(parents=True, exist_ok=True)
        (self.root / "search").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(s: str) -> str:
        return hashlib.sha1(s.encode("utf-8")).hexdigest()

    def _path(self, kind: str, key: str) -> Path:
        return self.root / kind / f"{self._key(key)}.json"

    def get(self, kind: str, key: str):
        if self.mode == "refresh":
            return None
        p = self._path(kind, key)
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        return None

    def put(self, kind: str, key: str, obj: dict):
        p = self._path(kind, key)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    @property
    def online(self) -> bool:
        return self.mode != "replay"


class Web:
    """Search + fetch with cache, robots.txt and per-host rate limiting."""

    def __init__(self, cache: WebCache, search_backend: str = "ddgs",
                 searxng_url: str = "http://localhost:8888", n_results: int = 8,
                 log_path: str | Path | None = None):
        import requests
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.cache = cache
        self.backend = search_backend
        self.searxng_url = searxng_url.rstrip("/")
        self.n_results = n_results
        self.log_path = log_path
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self._last_hit: dict[str, float] = {}
        self.calls = {"search": 0, "fetch": 0, "search_net": 0, "fetch_net": 0,
                      "search_empty_primary": 0, "search_fallback": 0, "search_empty_final": 0,
                      "search_ratelimited": 0, "search_secondary": 0, "search_offtopic_primary": 0,
                      "search_offtopic_final": 0, "search_quota_skips": 0}
        self.ddgs_engines = DDGS_ENGINES
        self.fallback = True          # scraped backend empty -> retry once -> Wikipedia for that query
        self.secondary: list[str] = []  # general backends tried after the primary, before Wikipedia (round 6)
        self.relevance = True         # off-topic results count as a failed search (round 6)
        self.brave_reserve = 0        # stop calling Brave when the plan's monthly remainder is this low
        self.brave_remaining = None   # from the API's X-RateLimit-Remaining header (monthly part)
        self.brave_budget = 0         # round 10: at most this many LIVE Brave calls this run (0 = no cap)
        self.brave_used = 0
        self.brave_headers: dict = {}  # the last response's rate-limit headers, as sent (diagnostics)
        self.last_error = None        # the last search's failure, if it failed (HTTP status + body), else None
        self._errors_shown: set = set()
        self.brave_status = None
        self._brave_paused = False
        self._consecutive_empty = 0
        self._last_search = 0.0
        self.last_backend = None      # which backend actually answered the last search
        self.last_on_topic = None

    # ── search ───────────────────────────────────────────────────────────
    def search(self, query: str) -> list[dict]:
        """
        Return [{url, title, snippet, domain}] (at most n_results).

        Chain: primary (cache, then network, one retry if empty) -> secondary backends -> [fallback]
        Wikipedia. A backend's cache is read only when the chain reaches it: reading the fallback
        cache first silently served old Wikipedia results to "SearXNG" runs (round 3b). The first
        ON-TOPIC answer is served; if none is on topic, the first non-empty one (counted off topic).
        """
        self.calls["search"] += 1
        self.last_error = None
        chain = [self.backend] + [b for b in self.secondary if b != self.backend]
        if self.backend in SCRAPED_BACKENDS and self.fallback and "wikipedia" not in chain:
            chain.append("wikipedia")
        first = None
        for i, b in enumerate(chain):
            results = self._lookup(b, query, primary=i == 0)
            if not results:
                continue
            if not self.relevance or on_topic(query, results):
                if i > 0:
                    self.calls["search_fallback" if b == "wikipedia" else "search_secondary"] += 1
                return self._served(b, results, topical=True)
            if i == 0:
                self.calls["search_offtopic_primary"] += 1
            first = first or (b, results)
        if first:
            self.calls["search_offtopic_final"] += 1
            return self._served(first[0], first[1], topical=False)
        return self._served(None, [], count_empty=self.cache.online)

    def _lookup(self, backend: str, query: str, primary: bool) -> list[dict]:
        hit = self.cache.get("search", f"{backend}|{query}")
        if hit is not None and hit.get("results"):
            return hit["results"]
        if backend == "brave" and self.brave_budget and self.brave_used >= self.brave_budget and not self._brave_paused:
            self._brave_paused = True             # the run's credit cap: never spend past it
            print(f"[web] Brave: {self.brave_used} live searches used, the run's budget; no more Brave calls this run", flush=True)
        if not self.cache.online or (backend == "brave" and self._brave_paused):
            if backend == "brave" and self._brave_paused:
                self.calls["search_quota_skips"] += 1
            return []
        results = self._search_net(backend, query)
        if not results and primary and backend in SCRAPED_BACKENDS and not self._brave_paused:
            self.calls["search_empty_primary"] += 1
            time.sleep(2.0)
            results = self._search_net(backend, query)              # one retry: blocks are often transient
        return results

    def _served(self, backend, results, count_empty: bool = True, topical: bool | None = None):
        """Book-keeping for every outcome: which backend served it (cache hits included) + the breaker."""
        self.last_backend = backend or "none"
        self.last_on_topic = topical
        if results:
            self._consecutive_empty = 0
            self.calls[f"served_{backend}"] = self.calls.get(f"served_{backend}", 0) + 1
            return results[: self.n_results]
        if count_empty:
            self.calls["search_empty_final"] += 1
            self._consecutive_empty += 1
            if self._consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                raise SearchUnavailable(
                    f"{self._consecutive_empty} searches in a row came back empty (backend {self.backend}, "
                    f"fallback {'on' if self.fallback else 'off'}). The search engine is blocked or down: "
                    f"stopping instead of producing results with no evidence. Last error: "
                    f"{self.last_error or 'none (the engine answered with no results)'}. Wait, check `docker logs "
                    f"planck3-searxng` (SearXNG) or try again later (ddgs rate limit), then re-run "
                f"(finished work is kept).")
        return []

    def _search_net(self, backend: str, query: str) -> list[dict]:
        self.calls["search_net"] += 1
        if backend in SCRAPED_BACKENDS:
            gap = MIN_SECONDS_BRAVE if backend == "brave" else MIN_SECONDS_BETWEEN_SEARCHES
            wait = gap - (time.time() - self._last_search)
            if wait > 0:
                time.sleep(wait)
            self._last_search = time.time()
        try:
            if backend == "ddgs":
                results = self._search_ddgs(query)
            elif backend == "brave":
                results = self._search_brave(query)
            elif backend == "searxng":
                results = self._search_searxng(query)
            elif backend == "wikipedia":
                results = self._search_wikipedia(query)
            else:
                raise ValueError(f"unknown search backend {backend}")
        except ValueError:
            raise
        except Exception as e:  # network errors must not kill a benchmark run (the breaker handles streaks)
            if not (self.last_error or "").startswith(f"{backend}: HTTP"):     # keep the HTTP status + body
                self._error(backend, query, repr(e)[:300])
            return []
        if results:  # never cache "nothing": a rate-limited engine would poison every later run
            self.cache.put("search", f"{backend}|{query}", {"query": query, "backend": backend,
                                                            "at": now_iso(), "results": results})
        return results

    def search_health(self) -> dict:
        """Per-run search quality: a run with mostly empty searches is not evidence of anything."""
        c = self.calls
        n = max(c["search"], 1)
        final = c["search_empty_final"] / n
        served = {k[len("served_"):]: v for k, v in c.items() if k.startswith("served_")}
        primary = served.get(self.backend, 0) / n
        answered = max(sum(served.values()), 1)
        topical = 1 - c["search_offtopic_final"] / answered
        return {"searches": c["search"], "primary_empty_rate": c["search_empty_primary"] / n,
                "fallback_rate": c["search_fallback"] / n, "secondary_rate": c["search_secondary"] / n,
                "final_empty_rate": final, "served": served, "primary_share": primary,   # cache hits included
                "primary_offtopic_rate": c["search_offtopic_primary"] / n, "on_topic_rate": topical,
                "relevance_checked": self.relevance, "brave_remaining": self.brave_remaining,
                "brave_quota_skips": c["search_quota_skips"], "brave_live_calls": self.brave_used,
                "valid": final <= 0.2 and (topical >= ON_TOPIC_RUN_MIN or not self.relevance)}

    def search_site(self, domain: str, query: str) -> list[dict]:
        """'More results from here': the same question restricted to one source (no fallback)."""
        if self.backend not in SCRAPED_BACKENDS or not self.cache.online:
            return []
        q = f"site:{domain} {query}"
        hit = self.cache.get("search", f"{self.backend}|{q}")
        results = hit["results"] if hit and hit.get("results") else self._search_net(self.backend, q)
        return [r for r in results if r["domain"] == domain or r["domain"].endswith("." + domain)][: self.n_results]

    def _search_ddgs(self, query: str) -> list[dict]:
        from ddgs import DDGS
        from ddgs.exceptions import DDGSException, RatelimitException
        try:
            raw = DDGS(timeout=FETCH_TIMEOUT).text(query, region="us-en", safesearch="off",
                                                   max_results=10, backend=self.ddgs_engines)
        except RatelimitException as e:
            self.calls["search_ratelimited"] += 1
            self._log({"event": "search_ratelimited", "backend": "ddgs", "query": query, "error": repr(e)})
            time.sleep(RATE_LIMIT_BACKOFF)
            return []
        except DDGSException:  # "No results found." is an ordinary empty answer
            return []
        out, seen = [], set()
        for item in raw or []:
            url = item.get("href") or item.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            out.append({"url": url, "title": item.get("title", ""), "snippet": item.get("body", "") or "",
                        "domain": domain_of(url)})
        return out[:20]

    def _search_brave(self, query: str) -> list[dict]:
        import os
        key = os.environ.get("BRAVE_API_KEY")
        if not key:
            raise ValueError("BRAVE_API_KEY is not set: put it in .env (template .env.example; on the box: "
                             ".\\scripts\\planck3.ps1 setkey)")
        self.brave_used += 1
        self._ledger_write()
        r = self.session.get(BRAVE_URL, params={"q": query, "count": 10},
                             headers={"Accept": "application/json", "X-Subscription-Token": key},
                             timeout=FETCH_TIMEOUT)
        self.brave_status = r.status_code
        self._brave_quota(getattr(r, "headers", None) or {}, r.status_code)
        if r.status_code != 200:
            body = (getattr(r, "text", "") or "")[:300].replace("\n", " ")
            self._error("brave", query, f"HTTP {r.status_code}: {body}")
        if r.status_code == 429:  # over the plan's rate or quota: back off, count it, fall back
            self.calls["search_ratelimited"] += 1
            if self.brave_remaining == 0:          # the month is used up: stop asking for this run
                self._brave_paused = True
                return []
            time.sleep(RATE_LIMIT_BACKOFF)
            return []
        r.raise_for_status()
        out, seen = [], set()
        for item in (r.json().get("web") or {}).get("results", []):
            url = item.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            out.append({"url": url, "title": _inline_text(item.get("title", "")),
                        "snippet": _inline_text(item.get("description", "") or ""), "domain": domain_of(url)})
        return out[:20]

    def _brave_quota(self, headers, status: int | None = None):
        """X-RateLimit-Remaining is '<per second>, <per month>': keep the monthly part; pause at the reserve.

        Round 9 fix: a plan without a monthly search quota (credit-based billing) reports a monthly
        limit of 0, so its monthly 'remaining' is 0 even while every search succeeds. That was read as
        "the month is used up", which paused Brave for round 6's whole training collection. A monthly
        remainder is now believed only when the plan reports a monthly limit, and never on a 200."""
        get = lambda k: headers.get(k) or headers.get(k.lower())  # noqa: E731
        rem, lim = get("X-RateLimit-Remaining"), get("X-RateLimit-Limit")
        self.brave_headers = {k: get(k) for k in ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset",
                                                   "X-RateLimit-Policy") if get(k) is not None}
        try:
            monthly = int(str(rem).split(",")[-1].strip()) if rem is not None else None
            monthly_limit = int(str(lim).split(",")[-1].strip()) if lim is not None and "," in str(lim) else None
        except ValueError:
            return
        if monthly is not None and (monthly_limit == 0 or (monthly == 0 and status == 200)):
            monthly = None                       # no monthly quota on this plan: the header says nothing
        self.brave_remaining = monthly if monthly is not None else (None if rem is not None else self.brave_remaining)
        if self.brave_remaining is not None and self.brave_reserve and self.brave_remaining <= self.brave_reserve \
                and not self._brave_paused:
            self._brave_paused = True
            print(f"[web] Brave: {self.brave_remaining} searches left this month (reserve {self.brave_reserve}); "
                  f"the rest of this run uses the next backend in the chain", flush=True)

    # ── the run's Brave credit (round 10: free credit only, spread over months) ──
    def attach_ledger(self, path: str | Path | None = None):
        """A runner-wide budget shared by every process of one runner invocation: the runner writes
        {"budget": B, "used": 0}; each process caps its live Brave calls at what is left and adds its own."""
        import os
        path = path or os.environ.get("PLANCK3_BRAVE_LEDGER")
        if not path or not Path(path).exists():
            return
        self._ledger = Path(path)
        with open(self._ledger, encoding="utf-8-sig") as f:     # PowerShell 5.1 writes a BOM
            d = json.load(f)
        self._ledger_used0 = int(d.get("used", 0))
        left = int(d["budget"]) - self._ledger_used0
        self.brave_budget = max(left, 0)
        if left <= 0:
            self._brave_paused = True
            print(f"[web] Brave: this run's credit is spent ({d['used']} of {d['budget']}); no Brave calls", flush=True)

    def _ledger_write(self):
        if getattr(self, "_ledger", None) is None:
            return
        with open(self._ledger, encoding="utf-8-sig") as f:
            d = json.load(f)
        d["used"] = self._ledger_used0 + self.brave_used
        with open(self._ledger, "w", encoding="utf-8") as f:
            json.dump(d, f)

    def brave_left(self) -> int | None:
        """Live Brave calls this process may still make (None = no cap)."""
        if not self.brave_budget:
            return None
        return max(self.brave_budget - self.brave_used, 0)

    def brave_alive(self) -> bool:
        """Key set AND the live API answers with quota left. Round 9 fix: this used to accept a CACHED
        answer, so with the month's quota at 0 a run still chose Brave (round 6 collected 3 of 1,914
        searches on Brave and the rest on ddgs/Wikipedia). One live search per start is the price."""
        import os
        if not os.environ.get("BRAVE_API_KEY"):
            return False
        if not self.cache.online:            # replay: no network, the cache is all there is
            hit = self.cache.get("search", "brave|Wikipedia")
            return bool(hit and hit.get("results"))
        return self.brave_quota()["ok"]

    def brave_quota(self) -> dict:
        """One live search: is the key valid, and how many searches are left this month (from the headers)?"""
        try:
            res = self._search_brave("Wikipedia")
        except Exception as e:
            return {"ok": False, "remaining": self.brave_remaining, "status": self.brave_status, "headers": self.brave_headers,
                    "why": self._brave_limit_why() or f"{type(e).__name__}: {str(e)[:120]}"}
        if res:
            self.cache.put("search", "brave|Wikipedia", {"query": "Wikipedia", "backend": "brave", "at": now_iso(), "results": res})
        ok = bool(res)                       # a 200 with results is the API serving; nothing else is proof
        why = "" if ok else ("quota used up this month" if self.brave_remaining == 0 else
                             f"no results (HTTP {self.brave_status}: key invalid, out of credit, or rate-limited)")
        if not ok:
            why = self._brave_limit_why() or why
        return {"ok": ok, "remaining": self.brave_remaining, "status": self.brave_status, "headers": self.brave_headers, "why": why}

    def _brave_limit_why(self) -> str:
        """Brave's 402 USAGE_LIMIT_EXCEEDED: the account's own monthly spending cap, not its credit balance."""
        err = self.last_error or ""
        if "USAGE_LIMIT_EXCEEDED" not in err:
            return ""
        m = re.search(r'"current_spend":\s*([\d.]+).*?"usage_limit":\s*([\d.]+)', err)
        spent = f" (spent ${m.group(1)} of a ${m.group(2)} limit)" if m else ""
        return (f"the Brave account's MONTHLY USAGE LIMIT is reached{spent}. Buying credit does not raise it: "
                "raise the monthly usage limit in the Brave API dashboard, then re-run")

    def ddgs_alive(self) -> bool:
        """Installed AND answering (a rate-limited client returns nothing)."""
        try:
            import ddgs  # noqa: F401
        except ImportError:
            return False
        try:
            return len(self._search_ddgs("Wikipedia")) > 0
        except Exception:
            return False

    def _search_searxng(self, query: str) -> list[dict]:
        r = self.session.get(f"{self.searxng_url}/search",
                             params={"q": query, "format": "json", "language": "en"},
                             timeout=FETCH_TIMEOUT)
        r.raise_for_status()
        out, seen = [], set()
        for item in r.json().get("results", []):
            url = item.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            out.append({"url": url, "title": item.get("title", ""),
                        "snippet": item.get("content", "") or "",
                        "domain": domain_of(url)})
        return out[:20]

    def _search_wikipedia(self, query: str) -> list[dict]:
        hits = self._wikipedia_api(query)
        if not hits:  # the API matches ALL words: a long question can find nothing; retry with its subject
            from .candidates import main_entity
            subject = main_entity(query)
            if subject and subject != query:
                hits = self._wikipedia_api(subject)
        return hits

    def _wikipedia_api(self, query: str) -> list[dict]:
        r = self.session.get("https://en.wikipedia.org/w/api.php", params={
            "action": "query", "list": "search", "srsearch": query,
            "format": "json", "srlimit": 10}, timeout=FETCH_TIMEOUT)
        r.raise_for_status()
        out = []
        for item in r.json().get("query", {}).get("search", []):
            title = item["title"]
            url = "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))
            snippet = html_to_text(item.get("snippet", ""))
            out.append({"url": url, "title": title, "snippet": snippet,
                        "domain": "en.wikipedia.org"})
        return out

    def searxng_alive(self) -> bool:
        """Up AND answering: a blocked SearXNG still returns HTTP 200 with an empty result list."""
        try:
            r = self.session.get(f"{self.searxng_url}/search",
                                 params={"q": "Wikipedia", "format": "json"}, timeout=10)
            return r.status_code == 200 and len(r.json().get("results", [])) > 0
        except Exception:
            return False

    # ── fetch ────────────────────────────────────────────────────────────
    def fetch(self, url: str) -> dict:
        """Return {url, status, html, fetched_at}; status 0 = not fetched."""
        self.calls["fetch"] += 1
        hit = self.cache.get("pages", url)
        if hit is not None:
            return hit
        if not self.cache.online:
            return {"url": url, "status": 0, "html": "", "fetched_at": None, "error": "replay-miss"}
        if not self._robots_ok(url):
            page = {"url": url, "status": 0, "html": "", "fetched_at": now_iso(), "error": "robots"}
            self.cache.put("pages", url, page)
            return page
        self._rate_limit(url)
        self.calls["fetch_net"] += 1
        try:
            r = self.session.get(url, timeout=FETCH_TIMEOUT, stream=True)
            ctype = r.headers.get("content-type", "")
            body = r.raw.read(MAX_HTML_BYTES, decode_content=True) if "html" in ctype else b""
            enc = r.encoding or "utf-8"
            page = {"url": url, "final_url": r.url, "status": r.status_code,
                    "html": body.decode(enc, errors="replace"), "fetched_at": now_iso(),
                    "content_type": ctype}
        except Exception as e:
            page = {"url": url, "status": 0, "html": "", "fetched_at": now_iso(), "error": repr(e)}
        self.cache.put("pages", url, page)
        return page

    def _robots_ok(self, url: str) -> bool:
        host = urlparse(url).scheme + "://" + urlparse(url).netloc
        if host not in self._robots:
            rp = robotparser.RobotFileParser()
            try:
                r = self.session.get(host + "/robots.txt", timeout=5)
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except Exception:
                rp.parse([])
            self._robots[host] = rp
        rp = self._robots[host]
        return rp.can_fetch(USER_AGENT, url) if rp else True

    def _rate_limit(self, url: str):
        host = urlparse(url).netloc
        wait = MIN_SECONDS_PER_HOST - (time.time() - self._last_hit.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        self._last_hit[host] = time.time()

    def _error(self, backend: str, query: str, msg: str):
        """A failed search: remembered (the breaker reports it), logged, and printed once per kind."""
        self.last_error = f"{backend}: {msg}"
        self._log({"event": "search_error", "backend": backend, "query": query, "error": msg})
        kind = msg.split(":")[0] if msg.startswith("HTTP") else msg[:40]
        if kind not in self._errors_shown:
            self._errors_shown.add(kind)
            print(f"[web] search error ({backend}): {msg}", flush=True)

    def _log(self, obj):
        if self.log_path:
            append_jsonl(self.log_path, obj)


# ── text extraction ──────────────────────────────────────────────────────
def domain_of(url: str) -> str:
    d = urlparse(url).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def _inline_text(s: str) -> str:
    """API snippets mark matches with <strong>/<b>: drop those tags without adding spaces ("1943 .")."""
    return html_to_text(re.sub(r"(?i)</?(?:strong|b|em|i|mark)>", "", s or ""))


def html_to_text(html: str) -> str:
    """Crude tag stripper (fallback + snippets)."""
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6]|td|th)>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def extract_main_text(html: str, url: str = "") -> str:
    """Main content via trafilatura (tables kept: infoboxes carry facts); crude fallback."""
    if not html:
        return ""
    try:
        import trafilatura
        text = trafilatura.extract(html, url=url or None, include_tables=True,
                                   include_comments=False, favor_recall=True)
        if text and len(text) > 200:
            return text
    except ImportError:
        pass
    except Exception:
        pass
    return html_to_text(html)


def extract_jsonld(html: str) -> list[str]:
    """Flatten schema.org JSON-LD into 'key: value' lines (prices, hours, addresses)."""
    lines = []
    for block in re.findall(r'(?is)<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html or ""):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        _flatten(data, "", lines)
    return lines[:200]


def _flatten(obj, prefix, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("@") and k != "@type":
                continue
            _flatten(v, f"{prefix}{k}." if prefix or k != "@graph" else "", out)
    elif isinstance(obj, list):
        for v in obj[:20]:
            _flatten(v, prefix, out)
    elif isinstance(obj, (str, int, float)) and str(obj).strip():
        val = str(obj).strip()
        if len(val) < 200 and not val.startswith("http"):
            out.append(f"{prefix.rstrip('.')}: {val}")
