#!/usr/bin/env python3
"""
Satz News Engine (v0.6 M25-M30):
Incorporates Planck 3.0 news-reader principles (read -> weigh -> write, trust-blind
extraction, source-family deduplication, itemized 0-10 confidence with -2 news penalty,
30% personal trust cap, system-only counterfactual divergence, and faithfulness gating)
into a profile-scoped desktop browser News surface connected to SatzBrain and all
configured local/cloud models.
"""

from __future__ import annotations

import email.utils
import hashlib
import html as html_lib
import json
import math
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from satz_brain import neutralize_brain_directives_in_source, slugify


_SIDECAR_DIR = Path(__file__).resolve().parent
DEFAULT_OVERLAY_PATH = _SIDECAR_DIR / "config" / "news_registry_overlay.json"

HALF_LIFE_HOURS = 18.0
EXPLORE_MIN_SHARE = 0.25
HIGH_EXPLORE_THRESHOLD = 8.0
DEFAULT_FETCH_TIMEOUT = 6.0

STOP_TITLE_WORDS = {
    "the", "and", "for", "with", "that", "from", "this", "have", "what", "when",
    "where", "which", "will", "into", "over", "after", "about", "amid", "says",
    "new", "says", "news", "report", "reports", "latest", "update", "today",
    "live", "how", "why", "who", "are", "was", "were", "has", "had", "not",
    "but", "you", "your", "their", "more", "than", "over", "under", "first",
}


class SatzLLMReader:
    """
    Trust-blind LLM candidate reader implementing `src.planck3.readers.LLMReader`'s
    `read(question, answer_type, pool) -> list[float]` contract across any local or
    cloud provider routed through `SatzSidecarRuntime._complete_role_prompt`.
    Never receives domain trust weights so user scores cannot bias reading.
    """

    kind = "llm"

    def __init__(self, runtime: Any, model_id: str, role_key: str = "news_reader", max_cands: int = 20):
        self.runtime = runtime
        self.model_id = model_id
        self.role_key = role_key
        self.name = model_id
        self.max_cands = max_cands or 20
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

    def read(self, question: str, answer_type: str, pool: dict[str, Any]) -> list[float]:
        from src.planck3.readers import READER_SYSTEM

        raw_cands = pool.get("cands") or []
        cands = raw_cands[: self.max_cands]
        if not cands:
            return []

        lines = [
            f"QUESTION: {question}",
            f"EXPECTED ANSWER TYPE: {answer_type}",
            f"CANDIDATES (from {'search result snippets' if pool.get('snippet') else 'a page'}):",
        ]
        for i, c in enumerate(cands):
            doms = ", ".join((c.get("domains") or [])[:3])
            ctx = str(c.get("context") or "")[:200]
            lines.append(f"  [{i}] {str(c.get('value') or '')[:80]} | \"{ctx}\" | {doms}")

        user_prompt = neutralize_brain_directives_in_source("\n".join(lines))
        raw = self.runtime._complete_role_prompt(
            self.model_id,
            READER_SYSTEM,
            user_prompt,
            temperature=0.05,
            max_tokens=160,
        )
        self.usage["calls"] += 1

        out = [0.0] * len(raw_cands)
        m = re.search(r"\{.*?\}", raw or "", re.S)
        if not m:
            return out
        try:
            d = json.loads(m.group(0))
            k = d.get("k")
            if k is not None and 0 <= int(k) < len(cands):
                out[int(k)] = max(0.0, min(1.0, float(d.get("p", 0.5))))
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
        return out


def faithful_news(
    text: str,
    question_or_headline: str,
    sources: list[dict[str, Any]],
    required_value: str | None = None,
    answer_type: str = "text",
    max_words: int = 220,
    allow_brief: bool = True,
) -> tuple[bool, list[str]]:
    """
    Validates generated News answers & digests:
    - Cites only [1..len(sources)] (or [B1..])
    - Contains no ungrounded numbers or proper nouns missing from question + sources
    - Respects max_words (<= 60 for direct fact cards, <= 220 for story briefs)
    """
    from src.planck3.candidates import _entities
    from src.planck3.metrics import is_correct
    from src.planck3.util import STOPWORDS, norm_text
    from src.planck3.writer import ALLOWED_WORDS, CITE, cited

    t = (text or "").strip()
    if not t:
        return False, ["empty"]

    problems: list[str] = []
    if required_value:
        if not (norm_text(required_value) in norm_text(t) or is_correct(t, [required_value], answer_type)):
            problems.append(f"does not state chosen value {required_value!r}")

    cites = cited(t)
    if any(c < 1 or c > len(sources) for c in cites):
        problems.append("cites a source number outside listed sources")
    if sources and not cites and "[B" not in t:
        problems.append("missing source citations")

    hay_raw = " ".join(
        [question_or_headline or "", required_value or ""]
        + [
            f"{s.get('name', '')} {s.get('domain', '')} {s.get('url', '')} {s.get('title', '')} "
            f"{s.get('context', '')} {s.get('snippet', '')} {s.get('body_text', '')} {s.get('text', '')} {s.get('says') or ''}"
            for s in sources
        ]
    )
    body = re.sub(r"\[([^\][]+)\]\(https?://[^\s)]+\)", r"\1", t)
    body = re.sub(r"\[B\d+\]", " ", CITE.sub(" ", body))
    have_nums = set(re.findall(r"\d+", hay_raw))
    for n in re.findall(r"\d+", body):
        if n not in have_nums:
            problems.append(f"number {n} is not in cited sources")

    extra_allowed = ALLOWED_WORDS | {
        "agreed", "contested", "consensus", "divergent", "perspectives", "framing",
        "sources", "independent", "developing", "confirmed", "conflict", "system",
        "updated", "missing", "brief", "summary", "headline", "headlines", "confidence", "band",
        "key", "several", "today", "top", "recent", "major", "meanwhile", "according",
        "highlights", "reports", "reporting", "coverage", "story", "stories",
        "eur", "usd", "gbp", "chf", "eu", "uk", "us", "un", "nato", "ai", "ev", "gdp",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december",
    }
    hay_words = set(norm_text(hay_raw).split())
    long_hay = [hw for hw in hay_words if len(hw) >= 5]
    for sent in re.split(r"(?<=[.!?\n])\s+", body):
        for ent, _off in _entities(sent):
            for w in norm_text(ent).split():
                if not w or w in hay_words or w in STOPWORDS or w in extra_allowed:
                    continue
                if len(w) >= 5 and any(hw.startswith(w[:5]) or w.startswith(hw[:5]) for hw in long_hay):
                    continue
                problems.append(f"entity {ent!r} is not in cited sources")
                break

    words_limit = max_words if allow_brief else 60
    if len(t.split()) > words_limit:
        problems.append(f"longer than {words_limit} words")

    return not problems, problems


_BRIEFING_NEWS_RE = re.compile(
    r"\b("
    r"top\s+(?:\w+\s+){0,3}(?:stories|news|headlines)|"
    r"corroborated\s+(?:\w+\s+){0,3}(?:stories|news)|"
    r"today'?s\s+(?:\w+\s+){0,3}(?:stories|news|headlines)|"
    r"compare\s+perspectives|perspectives\s+on|latest\s+(?:\w+\s+){0,2}(?:news|headlines|developments)|"
    r"news\s+(?:digest|briefing|summary|roundup)|summarize\s+(?:\w+\s+){0,2}news|"
    r"what'?s\s+happening|what\s+happened\s+(?:today|this\s+week)"
    r")\b",
    re.IGNORECASE,
)

_SCALAR_FACT_RE = re.compile(
    r"^\s*(?:how\s+(?:much|many|old|long|tall|far)|who\s+(?:won|is|was|are)|when\s+(?:did|was|will)|what\s+(?:year|date|percent|percentage|price|amount))\b",
    re.IGNORECASE,
)


def _is_briefing_news_query(q: str) -> bool:
    txt = (q or "").strip()
    if not txt or _SCALAR_FACT_RE.match(txt):
        return False
    return bool(_BRIEFING_NEWS_RE.search(txt))


def _expand_news_topic_tokens(tokens: set[str]) -> set[str]:
    exp_map = {
        "european": {"europe", "eu", "brussels", "eurozone"},
        "europe": {"european", "eu", "brussels"},
        "german": {"germany", "berlin", "bundestag"},
        "germany": {"german", "berlin"},
        "french": {"france", "paris"},
        "france": {"french", "paris"},
        "british": {"britain", "uk", "london"},
        "uk": {"britain", "british", "london"},
        "american": {"america", "us", "usa", "washington"},
        "global": {"world", "international"},
        "energy": {"grid", "power", "electricity", "renewables", "gas"},
        "grid": {"energy", "power", "electricity"},
    }
    out = set(tokens)
    for t in list(tokens):
        out |= exp_map.get(t, set())
    return out


def _plan_news_search_query(raw_q: str) -> str:
    """Converts conversational/meta News chat prompts into crisp news search terms."""
    q = str(raw_q or "").strip()
    q = re.sub(
        r"^(?:what\s+(?:are|is)\s+(?:today'?s|the|current)?\s*|"
        r"compare\s+perspectives\s+(?:on|about)\s+|"
        r"summarize\s+(?:the\s+)?|tell\s+me\s+(?:about\s+)?)",
        "",
        q,
        flags=re.IGNORECASE,
    ).strip()
    q = re.sub(r"\b(?:top|corroborated|current|stories|story|today'?s)\b", " ", q, flags=re.IGNORECASE)
    q = re.sub(r"\beuropean\b", "Europe European", q, flags=re.IGNORECASE)
    q = re.sub(r"\s+", " ", q).strip(" ?.!")
    if not q or q.lower() == "news":
        return "breaking world news today"
    if "news" not in q.lower():
        q = f"{q} news"
    return q[:140]


def _is_section_index_url(url: str) -> bool:
    """True for publisher homepages & section hubs (/hub/europe, /world/europe) vs real article URLs."""
    try:
        p = urllib.parse.urlsplit((url or "").strip())
        path = p.path.strip("/")
        if not path:
            return True
        segs = [s for s in path.split("/") if s]
        last = segs[-1].lower()
        if any(seg.lower() in ("hub", "topics", "topic", "section", "tag", "category") for seg in segs[:-1]):
            return True
        if len(segs) <= 2 and "-" not in last and not re.search(r"\d", path):
            return True
        if len(segs) <= 3 and segs[0].lower() in ("news", "world") and "-" not in last and not re.search(r"\d", path):
            return True
        return False
    except Exception:
        return False


def _tokenize_title(title: str) -> set[str]:
    return {
        w
        for w in re.findall(r"[a-z0-9äöüß]{3,}", (title or "").lower())
        if w not in STOP_TITLE_WORDS and not w.isdigit()
    }


def _parse_pub_date(raw: str | None, fallback_ts: float) -> float:
    s = (raw or "").strip()
    if not s:
        return fallback_ts
    try:
        dt = email.utils.parsedate_to_datetime(s)
        return dt.timestamp()
    except Exception:
        pass
    try:
        iso = s.replace("Z", "+00:00")
        from datetime import datetime

        return datetime.fromisoformat(iso).timestamp()
    except Exception:
        return fallback_ts


def _strip_html(raw: str) -> str:
    txt = re.sub(r"<script[^>]*>.*?</script>", " ", raw or "", flags=re.S | re.I)
    txt = re.sub(r"<style[^>]*>.*?</style>", " ", txt, flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = html_lib.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def _is_safe_http_url(url: str) -> bool:
    try:
        p = urllib.parse.urlsplit(url.strip())
        if p.scheme not in ("http", "https") or not p.netloc:
            return False
        host = (p.hostname or "").lower()
        if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.endswith(".local"):
            return False
        return True
    except Exception:
        return False


def parse_feed_xml(xml_text: str, domain: str, base_url: str = "") -> list[dict[str, Any]]:
    """Parses RSS 2.0 or Atom XML into normalized article metadata dictionaries."""
    items: list[dict[str, Any]] = []
    if not xml_text or not xml_text.strip():
        return items
    try:
        root = ET.fromstring(xml_text.encode("utf-8", errors="replace"))
    except ET.ParseError:
        return items

    now_ts = time.time()

    def _tag_name(el: ET.Element) -> str:
        return el.tag.rsplit("}", 1)[-1].lower()

    def _child_text(parent: ET.Element, *names: str) -> str:
        want = set(names)
        for ch in parent:
            if _tag_name(ch) in want:
                if ch.text and ch.text.strip():
                    return ch.text.strip()
                inner = "".join(ch.itertext()).strip()
                if inner:
                    return inner
        return ""

    # RSS 2.0 / RDF <item>
    for el in root.iter():
        tname = _tag_name(el)
        if tname not in ("item", "entry"):
            continue
        title = _strip_html(_child_text(el, "title"))
        link = _child_text(el, "link")
        if not link:
            for ch in el:
                if _tag_name(ch) == "link":
                    href = (ch.attrib.get("href") or "").strip()
                    rel = (ch.attrib.get("rel") or "alternate").lower()
                    if href and rel in ("alternate", ""):
                        link = href
                        break
        if not link and base_url:
            link = _child_text(el, "id", "guid")
        if not link or not title:
            continue
        if base_url and link.startswith("/"):
            link = urllib.parse.urljoin(base_url, link)

        desc_raw = _child_text(el, "description", "summary", "content", "encoded")
        snippet = _strip_html(desc_raw)[:600]
        author = _strip_html(_child_text(el, "author", "creator", "name"))[:120]
        pub_raw = _child_text(el, "pubDate", "published", "updated", "date")
        pub_ts = _parse_pub_date(pub_raw, now_ts)

        image_url = ""
        for ch in el:
            tn = _tag_name(ch)
            if tn in ("enclosure", "content", "thumbnail") and ch.attrib.get("url"):
                u_img = ch.attrib["url"].strip()
                if u_img.startswith(("http://", "https://")):
                    image_url = u_img
                    break
        if not image_url:
            img_m = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', desc_raw or "", re.I)
            if img_m:
                image_url = img_m.group(1)

        items.append(
            {
                "url": link,
                "domain": domain,
                "title": title,
                "snippet": snippet,
                "author": author,
                "published_at": pub_ts,
                "image_url": image_url,
            }
        )
    return items[:40]


class SatzNewsEngine:
    """Orchestrates Satz News feeds, Story Clustering, Source Scoring & Chat Answers."""

    def __init__(self, runtime: Any, overlay_path: Path | None = None):
        self.runtime = runtime
        self.overlay_path = overlay_path or DEFAULT_OVERLAY_PATH
        self.overlay = self._load_overlay()

    def _load_overlay(self) -> dict[str, Any]:
        if self.overlay_path.exists():
            try:
                return json.loads(self.overlay_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"wire_markers": {}, "starter_feeds": []}

    @staticmethod
    def ensure_news_tables_on_conn(db_conn: sqlite3.Connection) -> None:
        db_conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS satz_news_feeds (
                feed_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                feed_url TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'unscored',
                language TEXT NOT NULL DEFAULT 'en',
                enabled INTEGER NOT NULL DEFAULT 1,
                etag TEXT,
                last_modified TEXT,
                last_fetched_at REAL DEFAULT 0.0,
                error_count INTEGER DEFAULT 0,
                backoff_until REAL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS satz_news_articles (
                article_id TEXT PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                canonical_url TEXT,
                domain TEXT NOT NULL,
                family TEXT NOT NULL,
                title TEXT NOT NULL,
                snippet TEXT NOT NULL DEFAULT '',
                body_text TEXT NOT NULL DEFAULT '',
                translated_text TEXT,
                language TEXT NOT NULL DEFAULT 'en',
                image_url TEXT,
                author TEXT,
                published_at REAL NOT NULL,
                fetched_at REAL NOT NULL,
                trust_system REAL NOT NULL,
                trust_effective REAL NOT NULL,
                cluster_id TEXT,
                wire_origin TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_news_art_cluster ON satz_news_articles(cluster_id);
            CREATE INDEX IF NOT EXISTS idx_news_art_pub ON satz_news_articles(published_at);

            CREATE TABLE IF NOT EXISTS satz_news_clusters (
                cluster_id TEXT PRIMARY KEY,
                headline TEXT NOT NULL,
                summary_md TEXT NOT NULL,
                perspectives_json TEXT,
                agreed_claims_json TEXT,
                contested_claims_json TEXT,
                missing_perspectives_json TEXT,
                confidence10 REAL NOT NULL,
                band TEXT NOT NULL,
                independent_families INTEGER NOT NULL,
                topic_tags_json TEXT,
                brain_match_reasons_json TEXT,
                story_rank REAL NOT NULL,
                first_seen_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                is_hidden INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS satz_news_topics (
                topic_id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                keywords_json TEXT NOT NULL DEFAULT '[]',
                suppressed INTEGER NOT NULL DEFAULT 0,
                watch_id TEXT,
                created_at REAL NOT NULL
            );
            """
        )

    def seed_starter_feeds(self, db_conn: sqlite3.Connection | None = None) -> None:
        feeds = self.overlay.get("starter_feeds") or []
        if not feeds:
            return
        conn = db_conn or self.runtime.store.db
        for f in feeds:
            fid = str(f.get("feed_id") or slugify(str(f.get("feed_url") or "")))
            conn.execute(
                """
                INSERT OR IGNORE INTO satz_news_feeds
                (feed_id, domain, feed_url, title, category, language, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fid,
                    str(f.get("domain") or ""),
                    str(f.get("feed_url") or ""),
                    str(f.get("title") or ""),
                    str(f.get("category") or "unscored"),
                    str(f.get("language") or "en"),
                    1 if f.get("default_enabled", True) else 0,
                ),
            )
        conn.commit()

    def resolve_article_family(
        self,
        domain: str,
        text: str = "",
        author: str = "",
        canonical_url: str = "",
    ) -> tuple[str, str | None]:
        """
        Determines independent source family by combining `planck3.registry` base families
        (wikimedia, bbc, transfermarkt) with syndicated wire markers (AP, Reuters, AFP, dpa).
        Returns `(family, wire_origin_or_none)`.
        """
        from src.planck3.web import domain_of

        reg_rec = self.runtime.store.registry.lookup(domain)
        base_fam = str(reg_rec.get("family") or domain)
        hay = f"{author}\n{text[:700]}".lower()

        for wire_id, spec in (self.overlay.get("wire_markers") or {}).items():
            fam = str(spec.get("family") or wire_id)
            patterns = [str(p).lower() for p in (spec.get("patterns") or [])]
            if any(p and p in hay for p in patterns):
                return fam, wire_id

        if canonical_url:
            canon_dom = domain_of(canonical_url)
            if canon_dom and canon_dom != domain:
                canon_rec = self.runtime.store.registry.lookup(canon_dom)
                return str(canon_rec.get("family") or canon_dom), canon_dom

        return base_fam, None

    def _trust_for_domain(self, domain: str, use_personal: bool = True) -> dict[str, Any]:
        return self.runtime.store.trust(domain, personal=use_personal)

    # ── M26: Source Registry Listing & Feed Management ──────────────────────
    def list_sources(
        self,
        query: str = "",
        category: str = "",
        band_filter: str = "",
        conflicted_only: bool = False,
        with_rss_only: bool = False,
    ) -> dict[str, Any]:
        reg = self.runtime.store.registry
        q_low = (query or "").strip().lower()
        cat_f = (category or "").strip().lower()
        band_f = (band_filter or "").strip().lower()

        with self.runtime.store_lock:
            personal_rows = {
                r["domain"]: float(r["score"])
                for r in self.runtime.store.db.execute("SELECT domain, score FROM personal").fetchall()
            }
            visit_rows = {
                r["domain"]: int(r["visits"] or 0)
                for r in self.runtime.store.db.execute("SELECT domain, visits FROM satz_domain_visits").fetchall()
            }
            feed_rows = self.runtime.store.db.execute(
                "SELECT feed_id, domain, feed_url, title, category, language, enabled, last_fetched_at, error_count FROM satz_news_feeds"
            ).fetchall()

        feeds_by_domain: dict[str, list[dict[str, Any]]] = {}
        for fr in feed_rows:
            d = str(fr["domain"] or "").lower().removeprefix("www.")
            feeds_by_domain.setdefault(d, []).append(
                {
                    "feed_id": fr["feed_id"],
                    "feed_url": fr["feed_url"],
                    "title": fr["title"],
                    "language": fr["language"],
                    "enabled": bool(fr["enabled"]),
                    "last_fetched_at": float(fr["last_fetched_at"] or 0.0),
                    "error_count": int(fr["error_count"] or 0),
                }
            )

        from src.planck3.registry import trust_record

        domains_map = getattr(reg, "domains", None) or {}
        categories_map = getattr(reg, "categories", None) or {}
        all_domains = set(domains_map.keys())
        all_domains |= set(personal_rows.keys())
        all_domains |= set(visit_rows.keys())
        all_domains |= set(feeds_by_domain.keys())

        items: list[dict[str, Any]] = []
        for dom in sorted(all_domains):
            p_score = personal_rows.get(dom)
            trec = trust_record(dom, personal=p_score, registry=reg)
            sys_score = float(trec["system"])
            eff_score = float(trec["effective"])
            dom_cat = str(trec["category"] or "")
            dom_band = str(trec["band"] or "")
            dom_feeds = feeds_by_domain.get(dom, [])

            if q_low and q_low not in dom.lower() and q_low not in dom_cat.lower() and q_low not in str(trec["why"] or "").lower():
                continue
            if cat_f and dom_cat.lower() != cat_f:
                continue
            if band_f:
                if band_f == "unscored":
                    if trec["scored"]:
                        continue
                elif dom_band != band_f:
                    continue
            if conflicted_only and not trec["conflict"]:
                continue
            if with_rss_only and not dom_feeds:
                continue

            cat_meta = categories_map.get(dom_cat) or {}
            items.append(
                {
                    "domain": dom,
                    "category": dom_cat,
                    "rubric": cat_meta.get("rubric") or "",
                    "family": trec["family"],
                    "system": round(sys_score, 2),
                    "personal": round(p_score, 2) if p_score is not None else None,
                    "effective": round(eff_score, 2),
                    "band": dom_band,
                    "band_label": trec["band_label"],
                    "why": trec["why"],
                    "scored": bool(trec["scored"]),
                    "conflict": bool(trec["conflict"]),
                    "visits": visit_rows.get(dom, 0),
                    "feeds": dom_feeds,
                }
            )

        items.sort(key=lambda x: (-x["effective"], -len(x["feeds"]), x["domain"]))
        return {
            "ok": True,
            "as_of": getattr(reg, "as_of", None) or "2026-10-09",
            "categories": [
                {
                    "id": cid,
                    "score": cmeta.get("score"),
                    "rubric": cmeta.get("rubric") or "",
                    "what": cmeta.get("what") or "",
                }
                for cid, cmeta in categories_map.items()
            ],
            "total": len(items),
            "sources": items,
        }

    def add_or_toggle_feed(self, data: dict[str, Any]) -> dict[str, Any]:
        from src.planck3.web import domain_of

        action = str(data.get("action") or "upsert").strip().lower()
        feed_id = str(data.get("feed_id") or "").strip()
        if action == "toggle" and feed_id:
            enabled = 1 if data.get("enabled", True) else 0
            with self.runtime.store_lock:
                self.runtime.store.db.execute(
                    "UPDATE satz_news_feeds SET enabled = ? WHERE feed_id = ?",
                    (enabled, feed_id),
                )
                self.runtime.store.db.commit()
            return {"ok": True, "feed_id": feed_id, "enabled": bool(enabled)}

        if action == "delete" and feed_id:
            with self.runtime.store_lock:
                self.runtime.store.db.execute("DELETE FROM satz_news_feeds WHERE feed_id = ?", (feed_id,))
                self.runtime.store.db.commit()
            return {"ok": True, "deleted": feed_id}

        raw_url = str(data.get("feed_url") or data.get("url") or "").strip()
        custom_domain = str(data.get("domain") or "").strip().lower().removeprefix("www.")
        title = str(data.get("title") or "").strip()
        lang = str(data.get("language") or "en").strip().lower() or "en"

        if raw_url:
            if not _is_safe_http_url(raw_url):
                raise ValueError("Feed URL must be a valid public http/https URL")
            dom = custom_domain or domain_of(raw_url)
            fid = feed_id or f"feed-{slugify(dom)}-{hashlib.sha1(raw_url.encode('utf-8')).hexdigest()[:6]}"
            reg_rec = self.runtime.store.registry.lookup(dom)
            with self.runtime.store_lock:
                self.runtime.store.db.execute(
                    """
                    INSERT OR REPLACE INTO satz_news_feeds
                    (feed_id, domain, feed_url, title, category, language, enabled)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    """,
                    (fid, dom, raw_url, title or dom, str(reg_rec.get("category") or "unscored"), lang),
                )
                self.runtime.store.db.execute(
                    """
                    INSERT INTO satz_domain_visits (domain, visits, dwell_seconds, last_visited)
                    VALUES (?, 0, 0.0, ?)
                    ON CONFLICT(domain) DO NOTHING
                    """,
                    (dom, time.time()),
                )
                self.runtime.store.db.commit()
            return {"ok": True, "feed_id": fid, "domain": dom, "feed_url": raw_url}

        if custom_domain:
            with self.runtime.store_lock:
                self.runtime.store.db.execute(
                    """
                    INSERT INTO satz_domain_visits (domain, visits, dwell_seconds, last_visited)
                    VALUES (?, 0, 0.0, ?)
                    ON CONFLICT(domain) DO NOTHING
                    """,
                    (custom_domain, time.time()),
                )
                self.runtime.store.db.commit()
            return {"ok": True, "domain": custom_domain}

        raise ValueError("Provide a feed_url or domain")

    # ── M26/M28: Conditional Feed Ingestion & Article Capture ───────────────
    def _fetch_feed_http(self, url: str, etag: str | None = None, last_modified: str | None = None) -> dict[str, Any]:
        if not _is_safe_http_url(url):
            raise ValueError(f"Blocked non-public URL: {url}")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SatzBrowser/0.6",
            "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
        }
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_FETCH_TIMEOUT) as resp:
                body = resp.read(2_500_000)
                charset = resp.headers.get_content_charset() or "utf-8"
                return {
                    "status": int(getattr(resp, "status", 200) or 200),
                    "not_modified": False,
                    "etag": resp.headers.get("ETag") or etag,
                    "last_modified": resp.headers.get("Last-Modified") or last_modified,
                    "text": body.decode(charset, errors="replace"),
                }
        except urllib.error.HTTPError as he:
            if he.code == 304:
                return {"status": 304, "not_modified": True, "etag": etag, "last_modified": last_modified, "text": ""}
            raise

    def upsert_article(self, item: dict[str, Any], language: str = "en") -> str:
        from src.planck3.web import domain_of

        url = str(item.get("url") or "").strip()
        if not url:
            return ""
        domain = str(item.get("domain") or domain_of(url) or "").lower().removeprefix("www.")
        title = str(item.get("title") or domain).strip()
        snippet = str(item.get("snippet") or "")[:1200]
        body_text = str(item.get("body_text") or snippet or "")[:30000]
        author = str(item.get("author") or "")[:120]
        canonical_url = str(item.get("canonical_url") or "").strip()
        image_url = str(item.get("image_url") or "").strip()
        now_ts = time.time()
        pub_ts = float(item.get("published_at") or now_ts)

        t_sys = self._trust_for_domain(domain, use_personal=False)["system"]
        t_eff = self._trust_for_domain(domain, use_personal=True)["effective"]
        family, wire_origin = self.resolve_article_family(domain, f"{title}\n{snippet}\n{body_text}", author, canonical_url)
        art_id = f"art-{hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]}"

        with self.runtime.store_lock:
            self.runtime.store.db.execute(
                """
                INSERT INTO satz_news_articles
                (article_id, url, canonical_url, domain, family, title, snippet, body_text,
                 translated_text, language, image_url, author, published_at, fetched_at,
                 trust_system, trust_effective, wire_origin)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title = CASE WHEN LENGTH(excluded.title) > 0 THEN excluded.title ELSE satz_news_articles.title END,
                    snippet = CASE WHEN LENGTH(excluded.snippet) > LENGTH(satz_news_articles.snippet) THEN excluded.snippet ELSE satz_news_articles.snippet END,
                    body_text = CASE WHEN LENGTH(excluded.body_text) > LENGTH(satz_news_articles.body_text) THEN excluded.body_text ELSE satz_news_articles.body_text END,
                    image_url = COALESCE(NULLIF(excluded.image_url, ''), satz_news_articles.image_url),
                    family = excluded.family,
                    trust_system = excluded.trust_system,
                    trust_effective = excluded.trust_effective,
                    wire_origin = COALESCE(excluded.wire_origin, satz_news_articles.wire_origin),
                    fetched_at = excluded.fetched_at
                """,
                (
                    art_id, url, canonical_url, domain, family, title, snippet, body_text,
                    item.get("translated_text"), language, image_url, author, pub_ts, now_ts,
                    float(t_sys), float(t_eff), wire_origin,
                ),
            )
            if snippet or body_text:
                p_txt = f"{title}: {(body_text or snippet)[:500]}"
                self.runtime.store.add_passages(
                    [{"url": url, "domain": domain, "title": title, "text": p_txt}],
                    entity=domain,
                    question=f"[conv:conv-news] news feed {domain}",
                )
            self.runtime.store.db.commit()
        return art_id

    def refresh_news_feeds(
        self,
        force: bool = False,
        include_topic_search: bool = False,
        fetcher: Callable[[str, str | None, str | None], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Polls enabled RSS/Atom feeds using zero LLM tokens (conditional HTTP GET),
        plus optional PII-scrubbed Brave/ddgs search for followed topics when requested.
        """
        now_ts = time.time()
        http_get = fetcher or self._fetch_feed_http

        with self.runtime.store_lock:
            self.seed_starter_feeds(self.runtime.store.db)
            feeds = self.runtime.store.db.execute(
                "SELECT * FROM satz_news_feeds WHERE enabled = 1"
            ).fetchall()

        fetched_feeds = 0
        new_articles = 0
        not_modified = 0
        errors: list[str] = []

        due_feeds = []
        for fr in feeds:
            last_f = float(fr["last_fetched_at"] or 0.0)
            backoff_until = float(fr["backoff_until"] or 0.0)
            if not force and ((last_f > 0 and now_ts - last_f < 600.0) or (backoff_until > now_ts)):
                continue
            due_feeds.append(fr)

        fetch_outcomes: list[tuple[Any, dict[str, Any] | None, Exception | None]] = []
        if len(due_feeds) <= 1:
            for fr in due_feeds:
                try:
                    fetch_outcomes.append((fr, http_get(fr["feed_url"], fr["etag"], fr["last_modified"]), None))
                except Exception as exc:
                    fetch_outcomes.append((fr, None, exc))
        else:
            def _fetch_one(fr_row):
                return http_get(fr_row["feed_url"], fr_row["etag"], fr_row["last_modified"])

            with ThreadPoolExecutor(max_workers=min(6, len(due_feeds))) as pool:
                fut_map = {pool.submit(_fetch_one, fr): fr for fr in due_feeds}
                for fut in as_completed(fut_map):
                    fr = fut_map[fut]
                    try:
                        fetch_outcomes.append((fr, fut.result(), None))
                    except Exception as exc:
                        fetch_outcomes.append((fr, None, exc))

        for fr, res, err_exc in fetch_outcomes:
            fid = fr["feed_id"]
            furl = fr["feed_url"]
            dom = fr["domain"]
            lang = fr["language"] or "en"
            if err_exc is not None:
                errors.append(f"{dom}: {err_exc}")
                err_cnt = int(fr["error_count"] or 0) + 1
                backoff = now_ts + min(3600.0, 120.0 * (2 ** min(err_cnt, 4)))
                with self.runtime.store_lock:
                    self.runtime.store.db.execute(
                        "UPDATE satz_news_feeds SET error_count = ?, backoff_until = ? WHERE feed_id = ?",
                        (err_cnt, backoff, fid),
                    )
                    self.runtime.store.db.commit()
                continue
            assert res is not None
            if res.get("not_modified"):
                not_modified += 1
                with self.runtime.store_lock:
                    self.runtime.store.db.execute(
                        "UPDATE satz_news_feeds SET last_fetched_at = ?, error_count = 0 WHERE feed_id = ?",
                        (now_ts, fid),
                    )
                    self.runtime.store.db.commit()
                continue
            fetched_feeds += 1
            parsed_items = parse_feed_xml(str(res.get("text") or ""), dom, furl)
            for it in parsed_items[:15]:
                if self.upsert_article(it, language=lang):
                    new_articles += 1
            with self.runtime.store_lock:
                self.runtime.store.db.execute(
                    """
                    UPDATE satz_news_feeds
                    SET etag = ?, last_modified = ?, last_fetched_at = ?, error_count = 0, backoff_until = 0.0
                    WHERE feed_id = ?
                    """,
                    (res.get("etag"), res.get("last_modified"), now_ts, fid),
                )
                self.runtime.store.db.commit()

        if include_topic_search:
            safe_queries = self._build_scrubbed_topic_queries(limit=4)
            for tq in safe_queries:
                try:
                    results = self.runtime.web.search(tq)
                    for r in (results or [])[:5]:
                        self.upsert_article(
                            {
                                "url": r.get("url") or "",
                                "domain": r.get("domain") or "",
                                "title": r.get("title") or "",
                                "snippet": r.get("snippet") or "",
                                "published_at": now_ts,
                            }
                        )
                        new_articles += 1
                except Exception as exc:
                    errors.append(f"search '{tq}': {exc}")

        clusters_count = self.recluster_and_rank()
        return {
            "ok": True,
            "fetched_feeds": fetched_feeds,
            "not_modified": not_modified,
            "articles_ingested": new_articles,
            "clusters": clusters_count,
            "errors": errors[:5],
        }

    # ── M27: Local Brain + Mail Signal Extraction & PII Scrubber Gate ───────
    def build_local_interest_signals(self) -> list[dict[str, Any]]:
        """
        100% on-device signal extraction combining:
        - Explicit followed topics (`satz_news_topics`)
        - `planck3.Store.interests()` and `adjacent()` graph entities
        - Non-private `SatzBrain` entities (Topics, Projects, Organizations, Places, Orders)
        Never performs network IO.
        """
        signals: list[dict[str, Any]] = []
        seen_terms: set[str] = set()

        with self.runtime.store_lock:
            topic_rows = self.runtime.store.db.execute(
                "SELECT topic_id, name, keywords_json, suppressed FROM satz_news_topics"
            ).fetchall()

        suppressed_names = {str(r["name"] or "").lower() for r in topic_rows if r["suppressed"]}
        for tr in topic_rows:
            if tr["suppressed"]:
                continue
            nm = str(tr["name"] or "").strip()
            if not nm or nm.lower() in seen_terms:
                continue
            seen_terms.add(nm.lower())
            kws = json.loads(tr["keywords_json"] or "[]")
            signals.append(
                {
                    "term": nm,
                    "keywords": [nm.lower(), *(str(k).lower() for k in kws)],
                    "source": f"topic:{nm}",
                    "weight": 2.0,
                }
            )

        if not self.runtime.brain.locked:
            for ent in self.runtime.brain.list_entities()[:40]:
                etype = str(ent.get("type") or "").lower()
                if etype in ("person", "account", "promotion"):
                    continue
                nm = str(ent.get("name") or "").strip()
                clean_nm = self.runtime.brain.scrub_pii_for_external_query(nm)
                if not clean_nm or len(clean_nm) < 3 or clean_nm.lower() in suppressed_names:
                    continue
                if clean_nm.lower() in seen_terms:
                    continue
                seen_terms.add(clean_nm.lower())
                src_tag = "mail vendor" if etype == "order" else f"brain {etype}"
                signals.append(
                    {
                        "term": clean_nm,
                        "keywords": list(_tokenize_title(clean_nm)) or [clean_nm.lower()],
                        "source": f"{src_tag}: {clean_nm}",
                        "weight": 1.3 if etype == "project" else 1.0,
                    }
                )

        with self.runtime.store_lock:
            for ent_nm, score_val in self.runtime.store.interests(n=8):
                clean_nm = self.runtime.brain.scrub_pii_for_external_query(str(ent_nm or ""))
                if not clean_nm or len(clean_nm) < 3 or clean_nm.lower() in suppressed_names:
                    continue
                if clean_nm.lower() in seen_terms:
                    continue
                seen_terms.add(clean_nm.lower())
                signals.append(
                    {
                        "term": clean_nm,
                        "keywords": list(_tokenize_title(clean_nm)) or [clean_nm.lower()],
                        "source": f"search history: {clean_nm}",
                        "weight": min(1.5, float(score_val or 0.5)),
                    }
                )

        return signals[:24]

    def _build_scrubbed_topic_queries(self, limit: int = 4) -> list[str]:
        signals = self.build_local_interest_signals()
        queries: list[str] = []
        for s in signals:
            cleaned = self.runtime.brain.scrub_pii_for_external_query(s["term"])
            if len(cleaned) >= 4:
                q = f"{cleaned} latest news"
                if q not in queries:
                    queries.append(q)
            if len(queries) >= limit:
                break
        return queries

    # ── M28: Story Clustering, Confidence Scoring & "For You" Matching ──────
    def recluster_and_rank(self) -> int:
        from src.planck3.qtype import PENALTY
        from src.planck3.registry import BAND_LABEL, band

        now_ts = time.time()
        cutoff = now_ts - 7 * 86400.0
        with self.runtime.store_lock:
            art_rows = self.runtime.store.db.execute(
                "SELECT * FROM satz_news_articles WHERE published_at >= ? ORDER BY published_at DESC LIMIT 250",
                (cutoff,),
            ).fetchall()

        if not art_rows:
            return 0

        # Refresh trust scores under current profile's personal overrides
        articles: list[dict[str, Any]] = []
        for r in art_rows:
            dom = str(r["domain"])
            t_rec = self._trust_for_domain(dom, use_personal=True)
            t_sys = self._trust_for_domain(dom, use_personal=False)
            toks = _tokenize_title(str(r["title"] or ""))
            articles.append(
                {
                    "article_id": r["article_id"],
                    "url": r["url"],
                    "domain": dom,
                    "family": r["family"] or t_rec["family"],
                    "title": r["title"],
                    "snippet": r["snippet"] or "",
                    "body_text": r["body_text"] or "",
                    "translated_text": r["translated_text"],
                    "language": r["language"] or "en",
                    "image_url": r["image_url"] or "",
                    "author": r["author"] or "",
                    "published_at": float(r["published_at"] or now_ts),
                    "trust_system": float(t_sys["system"]),
                    "trust_effective": float(t_rec["effective"]),
                    "trust_record": t_rec,
                    "wire_origin": r["wire_origin"],
                    "tokens": toks,
                }
            )

        clusters: list[dict[str, Any]] = []
        for art in articles:
            best_idx = -1
            best_sim = 0.0
            for idx, cl in enumerate(clusters):
                if abs(art["published_at"] - cl["anchor_ts"]) > 3 * 86400.0:
                    continue
                inter = len(art["tokens"] & cl["tokens"])
                if inter < 2:
                    continue
                union = max(1, len(art["tokens"] | cl["tokens"]))
                jacc = inter / union
                if (jacc >= 0.28 or inter >= 3) and jacc > best_sim:
                    best_sim = jacc
                    best_idx = idx
            if best_idx >= 0:
                cl = clusters[best_idx]
                cl["articles"].append(art)
                cl["tokens"] |= art["tokens"]
            else:
                clusters.append(
                    {
                        "anchor_ts": art["published_at"],
                        "tokens": set(art["tokens"]),
                        "articles": [art],
                    }
                )

        signals = self.build_local_interest_signals()

        with self.runtime.store_lock:
            for cl in clusters:
                arts = sorted(cl["articles"], key=lambda a: (-a["trust_effective"], -a["published_at"]))
                lead = arts[0]
                cid = f"newscl-{hashlib.sha1(lead['url'].encode('utf-8')).hexdigest()[:14]}"

                # Family collapse: copies within the same syndication/mirror family count once
                fam_best: dict[str, dict[str, Any]] = {}
                for a in arts:
                    fk = a["family"]
                    if fk not in fam_best or a["trust_effective"] > fam_best[fk]["trust_effective"]:
                        fam_best[fk] = a
                fams_sorted = sorted(fam_best.values(), key=lambda a: -a["trust_effective"])
                indep_count = len(fams_sorted)
                top_trust = fams_sorted[0]["trust_effective"]
                agree_bonus = min(2.0, sum(1.0 for f in fams_sorted[1:] if f["trust_effective"] >= 7.0))
                conf10 = round(max(0.0, min(10.0, top_trust + agree_bonus - PENALTY["news"])), 1)
                band_code = band(conf10)

                # Local Brain / Mail relevance matching
                cluster_hay = " ".join(f"{a['title']} {a['snippet'][:240]}" for a in arts[:4]).lower()
                match_reasons: list[str] = []
                brain_boost = 0.0
                matched_tags: list[str] = []
                for sig in signals:
                    kws = sig["keywords"]
                    if any(kw in cluster_hay for kw in kws):
                        match_reasons.append(sig["source"])
                        matched_tags.append(sig["term"])
                        brain_boost += 0.25 * float(sig["weight"])
                        if len(match_reasons) >= 3:
                            break
                if not match_reasons and fams_sorted[0]["trust_record"]["system"] >= HIGH_EXPLORE_THRESHOLD:
                    match_reasons.append(f"explore: high-trust {lead['domain']} ({fams_sorted[0]['trust_record']['system']:.0f}/10)")

                avg_top3 = sum(f["trust_effective"] for f in fams_sorted[:3]) / max(1, min(3, indep_count))
                age_hours = max(0.0, (now_ts - max(a["published_at"] for a in arts)) / 3600.0)
                decay = math.exp(-math.log(2.0) * age_hours / HALF_LIFE_HOURS)
                story_rank = (0.6 * avg_top3 + 0.4 * min(10.0, 2.0 * indep_count)) * decay * (1.0 + min(0.6, brain_boost))

                bullets = []
                for idx_f, f in enumerate(fams_sorted[:3], 1):
                    snip = (f["snippet"] or f["title"]).strip()
                    if snip and not snip.endswith((".", "!", "?")):
                        snip += "."
                    bullets.append(f"- {snip} [{idx_f}]")
                summary_md = "\n".join(bullets)

                first_seen = min(a["published_at"] for a in arts)
                updated_at = max(a["published_at"] for a in arts)

                self.runtime.store.db.execute(
                    """
                    INSERT INTO satz_news_clusters
                    (cluster_id, headline, summary_md, confidence10, band, independent_families,
                     topic_tags_json, brain_match_reasons_json, story_rank, first_seen_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(cluster_id) DO UPDATE SET
                        headline = excluded.headline,
                        summary_md = excluded.summary_md,
                        confidence10 = excluded.confidence10,
                        band = excluded.band,
                        independent_families = excluded.independent_families,
                        topic_tags_json = excluded.topic_tags_json,
                        brain_match_reasons_json = excluded.brain_match_reasons_json,
                        story_rank = excluded.story_rank,
                        updated_at = excluded.updated_at
                    """,
                    (
                        cid,
                        lead["title"],
                        summary_md,
                        conf10,
                        band_code,
                        indep_count,
                        json.dumps(matched_tags, ensure_ascii=False),
                        json.dumps(match_reasons, ensure_ascii=False),
                        round(story_rank, 4),
                        first_seen,
                        updated_at,
                    ),
                )
                for a in arts:
                    self.runtime.store.db.execute(
                        "UPDATE satz_news_articles SET cluster_id = ?, trust_effective = ?, trust_system = ? WHERE article_id = ?",
                        (cid, a["trust_effective"], a["trust_system"], a["article_id"]),
                    )
            self.runtime.store.db.commit()
        return len(clusters)

    def get_stories(
        self,
        lane: str = "top",
        topic: str = "",
        explore: bool = False,
        limit: int = 30,
    ) -> dict[str, Any]:
        from src.planck3.registry import BAND_LABEL

        lane_l = (lane or "top").strip().lower()
        topic_l = (topic or "").strip().lower()

        with self.runtime.store_lock:
            cluster_rows = self.runtime.store.db.execute(
                """
                SELECT * FROM satz_news_clusters
                WHERE is_hidden = 0
                ORDER BY story_rank DESC, updated_at DESC
                LIMIT ?
                """,
                (max(10, limit * 2),),
            ).fetchall()

            articles_by_cluster: dict[str, list[dict[str, Any]]] = {}
            if cluster_rows:
                cids = [r["cluster_id"] for r in cluster_rows]
                ph = ",".join("?" for _ in cids)
                arows = self.runtime.store.db.execute(
                    f"SELECT * FROM satz_news_articles WHERE cluster_id IN ({ph}) ORDER BY trust_effective DESC, published_at DESC",
                    cids,
                ).fetchall()
                for ar in arows:
                    dom = str(ar["domain"])
                    t_rec = self._trust_for_domain(dom, use_personal=not explore)
                    t_sys = self._trust_for_domain(dom, use_personal=False)
                    articles_by_cluster.setdefault(ar["cluster_id"], []).append(
                        {
                            "article_id": ar["article_id"],
                            "url": ar["url"],
                            "domain": dom,
                            "family": ar["family"],
                            "title": ar["title"],
                            "snippet": ar["snippet"],
                            "body_text": ar["body_text"],
                            "translated_text": ar["translated_text"],
                            "language": ar["language"] or "en",
                            "image_url": ar["image_url"] or "",
                            "author": ar["author"] or "",
                            "published_at": float(ar["published_at"] or 0.0),
                            "trust_system": float(t_sys["system"]),
                            "trust_effective": float(t_rec["effective"]),
                            "category": t_rec["category"],
                            "conflict": bool(t_rec["conflict"]),
                            "wire_origin": ar["wire_origin"],
                        }
                    )

        stories_out: list[dict[str, Any]] = []
        matched_out: list[dict[str, Any]] = []
        explore_out: list[dict[str, Any]] = []

        for cr in cluster_rows:
            cid = cr["cluster_id"]
            arts = articles_by_cluster.get(cid, [])
            if not arts:
                continue
            tags = json.loads(cr["topic_tags_json"] or "[]")
            reasons = json.loads(cr["brain_match_reasons_json"] or "[]")
            if topic_l:
                hay = f"{cr['headline']} {' '.join(tags)} {cr['summary_md']}".lower()
                if topic_l not in hay:
                    continue

            # Deduplicate family badges for card display
            seen_fam: set[str] = set()
            family_badges: list[dict[str, Any]] = []
            collapsed_mirrors = 0
            for a in arts:
                if a["family"] in seen_fam:
                    collapsed_mirrors += 1
                    continue
                seen_fam.add(a["family"])
                family_badges.append(
                    {
                        "family": a["family"],
                        "domain": a["domain"],
                        "url": a["url"],
                        "trust_system": round(a["trust_system"], 1),
                        "trust_effective": round(a["trust_effective"], 1),
                        "category": a["category"],
                        "conflict": a["conflict"],
                        "language": a["language"],
                    }
                )

            conf10 = float(cr["confidence10"] or 5.0)
            b_code = str(cr["band"] or "low")
            persp = json.loads(cr["perspectives_json"]) if cr["perspectives_json"] else None
            has_conflict = bool(persp and len(persp.get("framings") or []) >= 2) or (len(family_badges) >= 2 and any(f["trust_effective"] < 6.0 for f in family_badges))
            lead_img = next((a["image_url"] for a in arts if a.get("image_url")), "")

            card = {
                "cluster_id": cid,
                "headline": cr["headline"],
                "summary_md": cr["summary_md"],
                "confidence10": conf10,
                "band": b_code,
                "band_label": BAND_LABEL.get(b_code, b_code),
                "independent_families": int(cr["independent_families"] or len(family_badges)),
                "collapsed_mirrors": collapsed_mirrors,
                "topic_tags": tags,
                "brain_match_reasons": reasons,
                "outside_usual": bool(explore),
                "story_rank": float(cr["story_rank"] or 0.0),
                "updated_at": float(cr["updated_at"] or 0.0),
                "is_read": bool(cr["is_read"]),
                "has_conflict": has_conflict,
                "lead_image": lead_img,
                "families": family_badges,
                "articles": arts[:6],
            }

            if lane_l == "perspectives" and not (len(family_badges) >= 2 or has_conflict):
                continue

            is_explore_item = all(str(r).startswith("explore:") for r in reasons)
            if lane_l == "foryou":
                if not is_explore_item:
                    matched_out.append(card)
                else:
                    explore_out.append(card)
            else:
                stories_out.append(card)

        if lane_l == "foryou":
            # Enforce >= 25% trusted "explore" quota to prevent filter bubbles
            target_n = min(limit, len(matched_out) + len(explore_out))
            min_exp = max(1, math.ceil(target_n * EXPLORE_MIN_SHARE)) if explore_out else 0
            taken_m = matched_out[: max(0, target_n - min_exp)]
            taken_e = explore_out[: max(min_exp, target_n - len(taken_m))]
            combined = []
            mi, ei = 0, 0
            while len(combined) < limit and (mi < len(taken_m) or ei < len(taken_e)):
                if mi < len(taken_m):
                    combined.append(taken_m[mi])
                    mi += 1
                if mi < len(taken_m):
                    combined.append(taken_m[mi])
                    mi += 1
                if ei < len(taken_e):
                    combined.append(taken_e[ei])
                    ei += 1
            stories_out = combined[:limit]
        else:
            stories_out = stories_out[:limit]

        return {
            "ok": True,
            "lane": lane_l,
            "explore": explore,
            "total": len(stories_out),
            "stories": stories_out,
        }

    # ── M28: On-Demand Non-English Article Translation ──────────────────────
    def translate_article(self, article_id: str, target_lang: str = "en") -> dict[str, Any]:
        with self.runtime.store_lock:
            row = self.runtime.store.db.execute(
                "SELECT * FROM satz_news_articles WHERE article_id = ?",
                (article_id,),
            ).fetchone()
        if not row:
            raise ValueError("Article not found")
        if row["translated_text"]:
            return {
                "ok": True,
                "article_id": article_id,
                "language": row["language"],
                "translated_text": row["translated_text"],
                "original_text": row["body_text"] or row["snippet"],
                "cached": True,
            }
        roles = self.runtime.get_model_management_config()["roles"]
        capture_model = roles.get("news_capture") or "gemma-4-e4b"
        raw_src = (row["body_text"] or row["snippet"] or "").strip()[:3500]
        if not raw_src:
            return {"ok": False, "error": "Article text is empty"}

        safe_src = neutralize_brain_directives_in_source(raw_src)
        sys_p = (
            f"You translate news reporting accurately into {target_lang}. "
            "Preserve all numbers, dates, quotes, and proper nouns faithfully. Do not summarize or invent facts."
        )
        usr_p = f"HEADLINE: {row['title']}\nDOMAIN: {row['domain']}\nTEXT:\n{safe_src}"
        translated = self.runtime._complete_role_prompt(
            capture_model,
            sys_p,
            usr_p,
            temperature=0.1,
            max_tokens=1400,
        )
        with self.runtime.store_lock:
            self.runtime.store.db.execute(
                "UPDATE satz_news_articles SET translated_text = ? WHERE article_id = ?",
                (translated, article_id),
            )
            self.runtime.store.db.commit()
        return {
            "ok": True,
            "article_id": article_id,
            "language": row["language"],
            "translated_text": translated,
            "original_text": raw_src,
            "model": capture_model,
            "cached": False,
        }

    # ── M29: Perspective Spread Matrix (Agreed / Divergent / Blind Spots) ───
    def get_perspectives(self, cluster_id: str, refresh: bool = False) -> dict[str, Any]:
        with self.runtime.store_lock:
            cr = self.runtime.store.db.execute(
                "SELECT * FROM satz_news_clusters WHERE cluster_id = ?",
                (cluster_id,),
            ).fetchone()
            if not cr:
                raise ValueError("Story cluster not found")
            arows = self.runtime.store.db.execute(
                "SELECT * FROM satz_news_articles WHERE cluster_id = ? ORDER BY trust_effective DESC, published_at DESC",
                (cluster_id,),
            ).fetchall()

        if cr["perspectives_json"] and not refresh:
            try:
                cached = json.loads(cr["perspectives_json"])
                if cached and cached.get("framings"):
                    return {"ok": True, "cluster_id": cluster_id, **cached, "cached": True}
            except Exception:
                pass

        # Group by independent family while tracking collapsed copies
        seen_fam: set[str] = set()
        fam_articles: list[dict[str, Any]] = []
        collapsed_wire = 0
        for ar in arows:
            fam = str(ar["family"] or ar["domain"])
            if fam in seen_fam:
                collapsed_wire += 1
                continue
            seen_fam.add(fam)
            t_rec = self._trust_for_domain(ar["domain"], use_personal=True)
            t_sys = self._trust_for_domain(ar["domain"], use_personal=False)
            fam_articles.append(
                {
                    "url": ar["url"],
                    "domain": ar["domain"],
                    "family": fam,
                    "title": ar["title"],
                    "snippet": ar["snippet"] or ar["body_text"][:400],
                    "category": t_rec["category"],
                    "why": t_rec["why"],
                    "trust_system": round(float(t_sys["system"]), 2),
                    "trust_effective": round(float(t_rec["effective"]), 2),
                    "conflict": bool(t_rec["conflict"]),
                }
            )

        roles = self.runtime.get_model_management_config()["roles"]
        analyzer_model = roles.get("news_analyzer") or roles.get("chat") or "gemma-4-e4b"

        agreed_facts: list[str] = []
        framings: list[dict[str, Any]] = []
        blind_spots: list[str] = []

        cats_present = {a["category"] for a in fam_articles}
        if "primary_official" not in cats_present and "eu_gov" not in cats_present and "us_agency" not in cats_present:
            blind_spots.append("missing: no primary official government or agency filing (trust 9.0) retrieved in this cluster")
        if "science" not in cats_present and any(w in str(cr["headline"] or "").lower() for w in ("climate", "health", "ai", "study", "energy", "virus")):
            blind_spots.append("missing: no peer-reviewed or scientific journal source (science 10.0) attached")
        if collapsed_wire > 0:
            blind_spots.append(f"deduped: {collapsed_wire} syndicated/wire duplicate article(s) were collapsed into their origin family")

        # Try structured perspective extraction via configured analyzer model when >= 2 families exist
        if len(fam_articles) >= 2 and analyzer_model != "template":
            try:
                src_lines = []
                for idx, fa in enumerate(fam_articles[:6], 1):
                    src_lines.append(
                        f"[{idx}] {fa['domain']} (cat={fa['category']}, eff={fa['trust_effective']}/10, fam={fa['family']}): "
                        f"{fa['title']} | {neutralize_brain_directives_in_source(fa['snippet'][:320])}"
                    )
                sys_p = (
                    "Compare reporting across independent news outlets objectively. "
                    "Return JSON ONLY: {\"agreed\": [\"fact with [1, 2] citation\"], "
                    "\"framings\": [{\"label\": \"group name\", \"indices\": [1], \"claims\": [\"claim [1]\"]}], "
                    "\"blind_spot\": \"what perspective or primary document is missing\"}. "
                    "Every number and proper noun must come from the provided sources."
                )
                usr_p = f"STORY: {cr['headline']}\nSOURCES:\n" + "\n".join(src_lines)
                raw = self.runtime._complete_role_prompt(
                    analyzer_model, sys_p, usr_p, temperature=0.1, max_tokens=700
                )
                m = re.search(r"\{.*\}", raw or "", re.S)
                if m:
                    parsed = json.loads(m.group(0))
                    cand_agreed = [str(x).strip() for x in (parsed.get("agreed") or []) if str(x).strip()][:5]
                    if cand_agreed and all(faithful_news(line, cr["headline"], fam_articles, max_words=220)[0] for line in cand_agreed):
                        agreed_facts = cand_agreed
                    for fr_item in (parsed.get("framings") or [])[:3]:
                        idxs = [int(i) for i in (fr_item.get("indices") or []) if isinstance(i, int) and 1 <= i <= len(fam_articles)]
                        if not idxs:
                            continue
                        claims_clean = [
                            str(c).strip()
                            for c in (fr_item.get("claims") or [])
                            if str(c).strip() and faithful_news(str(c), cr["headline"], fam_articles, max_words=220)[0]
                        ]
                        if not claims_clean:
                            claims_clean = [f"{fam_articles[i - 1]['title']} [{i}]" for i in idxs]
                        framings.append(
                            {
                                "label": str(fr_item.get("label") or f"Group {', '.join(str(i) for i in idxs)}"),
                                "sources": [fam_articles[i - 1] for i in idxs],
                                "claims": claims_clean[:4],
                            }
                        )
                    if parsed.get("blind_spot"):
                        blind_spots.insert(0, f"note: {str(parsed['blind_spot']).strip()}")
            except Exception:
                pass

        # Deterministic fallback grouping by trust/category buckets when LLM output skipped/unavailable
        if not framings:
            tier_a = [a for a in fam_articles if a["category"] in ("independent", "science", "news_eu", "public_broadcaster", "eu_gov", "european_gov_non_eu", "intergov")]
            tier_b = [a for a in fam_articles if a["category"] in ("news_us_uk", "news_other", "us_agency", "us_gov")]
            tier_c = [a for a in fam_articles if a not in tier_a and a not in tier_b]
            for label, grp in (
                ("Independent & European Public Reporting", tier_a),
                ("US / UK & International Wires", tier_b),
                ("Politicized, Regional Pressure & Other", tier_c),
            ):
                if grp:
                    framings.append(
                        {
                            "label": label,
                            "sources": grp[:4],
                            "claims": [
                                f"{g['title']} - {(g['snippet'] or '')[:180]} [{fam_articles.index(g) + 1}]"
                                for g in grp[:3]
                            ],
                        }
                    )

        if not agreed_facts and fam_articles:
            if len(fam_articles) >= 2:
                agreed_facts.append(f"{cr['headline']} covered across {len(fam_articles)} independent families [1, 2].")
            else:
                agreed_facts.append(f"Currently reported by 1 independent family ({fam_articles[0]['domain']}) [1].")

        sys_top = sorted(fam_articles, key=lambda a: -a["trust_system"])[0]["domain"] if fam_articles else ""
        eff_top = fam_articles[0]["domain"] if fam_articles else ""
        counterfactual = (
            f"Personal trust scores elevated {eff_top} over system top choice {sys_top}."
            if sys_top and eff_top and sys_top != eff_top
            else "System-only trust weights preserve the same primary ordering."
        )

        payload = {
            "headline": cr["headline"],
            "agreed": agreed_facts,
            "framings": framings,
            "blind_spots": blind_spots,
            "syndicated_collapsed": collapsed_wire,
            "system_counterfactual": counterfactual,
            "analyzer_model": analyzer_model,
            "privacy_disclosure": (
                "Local extractive perspective grouping (0 cloud tokens)."
                if not self.runtime._parse_cloud_model_id(analyzer_model)
                else f"Sent {len(fam_articles)} public article snippets to {analyzer_model}; private Brain & Mail omitted."
            ),
        }

        with self.runtime.store_lock:
            self.runtime.store.db.execute(
                """
                UPDATE satz_news_clusters
                SET perspectives_json = ?, agreed_claims_json = ?, missing_perspectives_json = ?
                WHERE cluster_id = ?
                """,
                (
                    json.dumps(payload, ensure_ascii=False),
                    json.dumps(agreed_facts, ensure_ascii=False),
                    json.dumps(blind_spots, ensure_ascii=False),
                    cluster_id,
                ),
            )
            self.runtime.store.db.commit()

        return {"ok": True, "cluster_id": cluster_id, **payload, "cached": False}

    # ── M25: Audited read -> weigh -> write News Chat Pipeline ──────────────
    def _build_reader(self, model_id: str):
        if model_id in ("hertz (reader)", "planck (reader)"):
            try:
                return self.runtime.ensure_reader(model_id)
            except Exception:
                from src.planck3.readers import HeuristicReader

                return HeuristicReader()
        if model_id == "heuristic":
            from src.planck3.readers import HeuristicReader

            return HeuristicReader()
        return SatzLLMReader(self.runtime, model_id, role_key="news_reader", max_cands=20)

    def answer_news_question(
        self,
        question: str,
        open_sources: list[dict[str, Any]] | None = None,
        roles_override: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Full Planck 3.0 audited pipeline for News chat:
        1. `news_planner` decomposes + scrubs query (PII Scrubber Gate)
        2. `news_capture` gathers local articles + open tabs + live web results
        3. Trust-blind `news_reader` scores candidates
        4. `consolidate()` runs twice (`personal` vs `system_only`) for counterfactual diff
        5. `news_analyzer` writes concise summary guarded by `faithful_news` (template fallback)
        """
        from src.planck3.candidates import rank_passages, snippet_candidates, span_candidates, title_aboutness
        from src.planck3.chat import infer_answer_type
        from src.planck3.consolidate import consolidate, divergence
        from src.planck3.qtype import classify
        from src.planck3.web import domain_of, extract_jsonld, extract_main_text
        from src.planck3.writer import TemplateWriter

        roles = dict(self.runtime.get_model_management_config()["roles"])
        if roles_override:
            roles.update(roles_override)

        planner_m = roles.get("news_planner") or "gemma-4-e4b"
        reader_m = roles.get("news_reader") or "hertz (reader)"
        analyzer_m = roles.get("news_analyzer") or roles.get("chat") or "gemma-4-e4b"

        t_start = time.perf_counter()
        raw_q = (question or "").strip()
        scrubbed_q = self.runtime.brain.scrub_pii_for_external_query(raw_q) or raw_q
        is_briefing = _is_briefing_news_query(scrubbed_q)
        at = infer_answer_type(scrubbed_q)
        qt = classify(scrubbed_q)
        if not qt or qt == "encyclopedic":
            qt = "news"
        steps: list[str] = []

        planned_q = _plan_news_search_query(scrubbed_q) if is_briefing else scrubbed_q
        search_queries = [planned_q]
        steps.append(f"1. Planned query ({qt.replace('_', ' ')}): \"{planned_q}\" via {planner_m}")

        # Gather candidate results: RSS articles + open tabs + live web search
        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        docs: list[dict[str, Any]] = []

        for src in open_sources or []:
            u = str(src.get("url") or "").strip()
            if not u or u in seen_urls:
                continue
            txt, _ = self.runtime.get_source_text(str(src.get("id") or u), u, str(src.get("title") or u))
            if txt:
                seen_urls.add(u)
                dom = str(src.get("domain") or domain_of(u) or "")
                results.append(
                    {
                        "url": u,
                        "domain": dom,
                        "title": str(src.get("title") or dom),
                        "snippet": txt[:400],
                        "capture_mode": "dom",
                    }
                )
                docs.append({"url": u, "domain": dom, "title": str(src.get("title") or dom), "text": txt, "capture_mode": "dom"})

        with self.runtime.store_lock:
            art_cnt = self.runtime.store.db.execute("SELECT COUNT(*) FROM satz_news_articles").fetchone()[0]
        if art_cnt == 0 and getattr(self.runtime.web.cache, "online", True):
            try:
                rf = self.refresh_news_feeds(force=False)
                if rf.get("articles_ingested"):
                    steps.append(f"1b. Auto-warmed RSS feeds ({rf['fetched_feeds']} feed(s), {rf['articles_ingested']} article(s))")
            except Exception:
                pass

        q_toks = _expand_news_topic_tokens(_tokenize_title(scrubbed_q))
        with self.runtime.store_lock:
            local_arts = self.runtime.store.db.execute(
                "SELECT url, domain, title, snippet, body_text, image_url FROM satz_news_articles ORDER BY trust_effective DESC, published_at DESC LIMIT 160"
            ).fetchall()

        scored_local: list[tuple[int, sqlite3.Row]] = []
        for ar in local_arts:
            a_toks = _tokenize_title(f"{ar['title']} {ar['snippet']}")
            if not q_toks:
                overlap = 0
            else:
                overlap = sum(
                    1
                    for qt_tok in q_toks
                    if qt_tok in a_toks
                    or (len(qt_tok) >= 5 and any(at_tok.startswith(qt_tok[:5]) or qt_tok.startswith(at_tok[:5]) for at_tok in a_toks))
                )
            if overlap >= 1 or is_briefing:
                scored_local.append((overlap, ar))

        scored_local.sort(key=lambda pair: (-pair[0],))
        for ov, ar in scored_local:
            if not is_briefing and ov == 0:
                continue
            if len(results) >= (8 if is_briefing else 5):
                break
            u = ar["url"]
            if u in seen_urls:
                continue
            seen_urls.add(u)
            body_or_snip = ar["body_text"] or ar["snippet"] or ""
            results.append(
                {
                    "url": u,
                    "domain": ar["domain"],
                    "title": ar["title"],
                    "snippet": ar["snippet"] or body_or_snip[:400],
                    "image_url": ar["image_url"] or "",
                    "capture_mode": "rss",
                }
            )
            if body_or_snip:
                docs.append(
                    {
                        "url": u,
                        "domain": ar["domain"],
                        "title": ar["title"],
                        "text": body_or_snip,
                        "capture_mode": "rss",
                    }
                )

        try:
            web_res = self.runtime.web.search(search_queries[0]) or []
            for r in web_res:
                u = str(r.get("url") or "").strip()
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    d_r = dict(r)
                    d_r.setdefault("capture_mode", "snippet")
                    results.append(d_r)
        except Exception as e:
            steps.append(f"2. Web search note: {e} (using {len(results)} local news source(s))")

        # Drop bare section homepages (/hub/europe, /, /europe) when actual article URLs exist
        non_index_results = [r for r in results if not _is_section_index_url(str(r.get("url") or ""))]
        if len(non_index_results) >= 2:
            results = non_index_results

        def _tp(dom: str) -> dict[str, Any]:
            return self._trust_for_domain(dom, use_personal=True)

        def _ts(dom: str) -> dict[str, Any]:
            return self._trust_for_domain(dom, use_personal=False)

        for r in results:
            tr = _tp(r.get("domain") or "")
            r["trust_record"] = tr
            r["trust"] = tr["combined"]

        steps.append(
            f"2. Gathered {len(results)} source(s) from {len({r.get('domain') for r in results})} domain(s)"
        )

        # Build snippet pool & trust-blind reader pass (only for specific fact/claim questions, not multi-story digests)
        reader = self._build_reader(reader_m)
        pools: list[dict[str, Any]] = []
        if results and not is_briefing:
            scands = snippet_candidates(scrubbed_q, results, at)
            if scands:
                pools.append({"name": "snippets", "cands": scands, "snippet": True, "r": []})
                pools[-1]["r"] = reader.read(scrubbed_q, at, pools[-1])
                steps.append(f"3. Extracted & scored {len(scands)} snippet candidate(s) with {reader_m} (trust-blind)")

        cons = consolidate(pools, at, qt, _tp)
        # Escalate to opening up to 3 full pages when snippets need full article context
        if results and (is_briefing or cons["value"] is None or cons["confidence"] < 7.0):
            already_docs = {d["url"] for d in docs}
            order = sorted(
                results,
                key=lambda r: (
                    not _is_section_index_url(str(r.get("url") or "")),
                    title_aboutness(planned_q, r.get("title", "")) >= 0.3,
                    r["trust_record"]["effective"],
                ),
                reverse=True,
            )
            opened_cnt = 0
            for r in order:
                if opened_cnt >= (3 if is_briefing else 2):
                    break
                if r["url"] in already_docs:
                    doc_obj = next((d for d in docs if d["url"] == r["url"]), None)
                    text = doc_obj["text"] if doc_obj else ""
                    extra_l: list[str] = []
                else:
                    try:
                        page = self.runtime.web.fetch(r["url"])
                    except Exception:
                        page = {}
                    opened_cnt += 1
                    if not page.get("html"):
                        continue
                    text = extract_main_text(page["html"], r["url"])
                    extra_l = extract_jsonld(page["html"])
                    if text:
                        docs.append(
                            {
                                "url": r["url"],
                                "domain": r["domain"],
                                "title": r.get("title", ""),
                                "trust": r["trust"],
                                "text": text,
                                "capture_mode": "fetch",
                            }
                        )
                        r["capture_mode"] = "fetch"
                        already_docs.add(r["url"])
                if text and not is_briefing:
                    pc = span_candidates(scrubbed_q, text, at, url=r["url"], extra_lines=extra_l)
                    if pc:
                        p_obj = {"name": f"page:{r['domain']}", "cands": pc, "snippet": False, "r": []}
                        p_obj["r"] = reader.read(scrubbed_q, at, p_obj)
                        pools.append(p_obj)
                        steps.append(f"3b. Opened {r['domain']} ({r['trust_record']['effective']:.1f}/10): {len(pc)} candidate(s)")
            if not is_briefing:
                cons = consolidate(pools, at, qt, _tp)

        sys_cons = consolidate(pools, at, qt, _ts) if pools else cons
        div = divergence(cons, sys_cons, at)
        snippets_map = {r["url"]: r.get("snippet", "") for r in results}

        if div:
            steps.append(
                f"4. System counterfactual note: personal scores shifted result "
                f"({div['system_value']} at {div['system_confidence']}/10 -> {cons['value']} at {cons['confidence']}/10)"
            )

        # Build concise grounded answer with faithfulness gate
        wr_fallback = False
        wr_problems: list[str] = []
        used_writer = analyzer_m
        ordered_sources = sorted(
            results,
            key=lambda r: (
                not _is_section_index_url(str(r.get("url") or "")),
                r.get("capture_mode") in ("dom", "rss", "fetch"),
                r["trust_record"]["effective"],
            ),
            reverse=True,
        )[:6]
        docs_by_url = {str(d.get("url") or ""): str(d.get("text") or "") for d in docs}

        sources_for_card: list[dict[str, Any]] = []
        sources_for_faithful: list[dict[str, Any]] = []
        for idx_s, s in enumerate(ordered_sources, 1):
            t_rec = s["trust_record"]
            t_sys_rec = _ts(s["domain"])
            role_lbl = "source"
            if cons["families"] and any(f["domain"] == s["domain"] for f in cons["families"][:1]):
                role_lbl = "states it"
            elif cons["families"] and any(f["domain"] == s["domain"] for f in cons["families"][1:]):
                role_lbl = "agrees"
            elif cons["conflicts"] and any(c["domain"] == s["domain"] for c in cons["conflicts"]):
                role_lbl = "diverges"
            full_doc_txt = docs_by_url.get(s["url"], "")
            snip_txt = str(s.get("snippet") or "")
            card_item = {
                "idx": idx_s,
                "role": role_lbl,
                "domain": s["domain"],
                "url": s["url"],
                "title": s.get("title") or s["domain"],
                "snippet": (snip_txt or full_doc_txt)[:360],
                "image_url": s.get("image_url") or "",
                "trust": {
                    "system": t_sys_rec["system"],
                    "personal": t_rec["personal"],
                    "effective": t_rec["effective"],
                    "category": t_rec["category"],
                    "family": t_rec["family"],
                    "why": t_rec["why"],
                    "conflict": t_rec["conflict"],
                },
            }
            sources_for_card.append(card_item)
            sources_for_faithful.append(
                {
                    **card_item,
                    "snippet": snip_txt[:800],
                    "body_text": full_doc_txt[:6000],
                }
            )

        answer_text = ""
        is_cloud_analyzer = self.runtime._parse_cloud_model_id(analyzer_m) is not None
        if cons["value"] is not None and not is_briefing:
            tw = TemplateWriter()
            tw_res = tw.write(scrubbed_q, at, cons, snippets_map)
            answer_text = tw_res["text"]
            used_writer = "template"
            if analyzer_m != "template" and sources_for_card:
                try:
                    src_ctx = "\n".join(
                        f"[{sf['idx']}] {sf['domain']} ({sf['trust']['effective']:.1f}/10, {sf['trust']['category']}): "
                        f"{sf['title']} | {neutralize_brain_directives_in_source((sf['body_text'] or sf['snippet'])[:900])}"
                        for sf in sources_for_faithful
                    )
                    brain_block = ""
                    if not is_cloud_analyzer:
                        brain_ctx, _ = self.runtime.brain.build_model_context_with_citations(raw_q, [], max_chars=1200)
                        brain_block = brain_ctx
                    lead_hint = (
                        f"Selected factual value: {cons['value']} ({cons['confidence']}/10 {cons['band']}).\n"
                        if cons["value"]
                        else ""
                    )
                    sys_p = (
                        "Write a concise, grounded news briefing in 1-3 short sentences or bullets. "
                        "Cite sources inline as [1], [2], etc. Keep numbers and proper names strictly grounded in SOURCES."
                    )
                    usr_p = f"QUESTION: {raw_q}\n{lead_hint}\n{brain_block}\n\nNEWS SOURCES:\n{src_ctx}"
                    cand_txt = self.runtime._complete_role_prompt(
                        analyzer_m, sys_p, usr_p, temperature=0.15, max_tokens=420
                    )
                    ok_f, probs = faithful_news(
                        cand_txt,
                        raw_q,
                        sources_for_faithful,
                        required_value=None,
                        answer_type=at,
                        max_words=240,
                        allow_brief=True,
                    )
                    if ok_f:
                        answer_text = cand_txt
                        used_writer = analyzer_m
                    else:
                        wr_fallback = True
                        wr_problems = probs
                        steps.append(f"5. Faithfulness fallback ({analyzer_m}): {'; '.join(probs[:2])}")
                except Exception as exc:
                    wr_fallback = True
                    wr_problems = [str(exc)]
                    steps.append(f"5. Analyzer fallback ({analyzer_m}): {exc}")
        else:
            # Multi-story briefing / perspective overview / unresolved single span: synthesize cleanly from gathered news sources
            if sources_for_card and analyzer_m != "template":
                try:
                    src_ctx = "\n\n".join(
                        f"[{sf['idx']}] {sf['domain']} ({sf['trust']['effective']:.1f}/10, {sf['trust']['category']}) - {sf['title']} ({sf['url']}):\n"
                        f"{neutralize_brain_directives_in_source((sf['body_text'] or sf['snippet'])[:1000])}"
                        for sf in sources_for_faithful
                    )
                    sys_p = (
                        "Summarize the gathered news articles in 2-5 crisp bullet points directly answering the user's request. "
                        "For each bullet, link the headline or source as [Title](url) [n] and keep every statistic and entity strictly from SOURCES."
                    )
                    cand_txt = self.runtime._complete_role_prompt(
                        analyzer_m, sys_p, f"QUERY: {raw_q}\n\nSOURCES:\n{src_ctx}", temperature=0.15, max_tokens=560
                    )
                    ok_f, probs = faithful_news(
                        cand_txt, raw_q, sources_for_faithful, max_words=260, allow_brief=True
                    )
                    if ok_f:
                        answer_text = cand_txt
                        used_writer = analyzer_m
                    else:
                        wr_fallback = True
                        wr_problems = probs
                        steps.append(f"5. Faithfulness fallback ({analyzer_m}): {'; '.join(probs[:2])}")
                except Exception as exc:
                    wr_fallback = True
                    wr_problems = [str(exc)]
                    steps.append(f"5. Analyzer fallback ({analyzer_m}): {exc}")
            if not answer_text:
                if sources_for_card:
                    answer_text = "\n".join(
                        f"- **[{s['title']}]({s['url']})** ({s['domain']} · {s['trust']['effective']:.1f}/10) — {s['snippet'][:180]} [{s['idx']}]"
                        for s in sources_for_card[:5]
                    )
                    used_writer = "extractive (fallback)" if wr_fallback else "template"
                else:
                    answer_text = "No verified news reporting was found for this query. Try refreshing feeds or widening search terms."
                    used_writer = "none"

        passages = rank_passages(
            scrubbed_q,
            docs
            + [
                {
                    "url": r["url"],
                    "domain": r["domain"],
                    "title": r.get("title", ""),
                    "trust": r["trust"],
                    "text": r.get("snippet", ""),
                }
                for r in results
            ],
        )

        # Compute cluster-level confidence fallback if span value is None (multi-story briefing / overview)
        conf10 = cons.get("confidence")
        band_code = cons.get("band") or "none"
        band_lbl = cons.get("band_label") or "No single span extracted"
        items_math = list(cons.get("items") or [])
        if (conf10 is None or is_briefing) and sources_for_card:
            from src.planck3.qtype import PENALTY
            from src.planck3.registry import BAND_LABEL, band

            seen_f: dict[str, tuple[float, float, dict[str, Any]]] = {}
            for s in sources_for_card:
                fam = s["trust"]["family"]
                eff_v = float(s["trust"]["effective"])
                sys_v = float(s["trust"]["system"])
                if fam not in seen_f or eff_v > seen_f[fam][0]:
                    seen_f[fam] = (eff_v, sys_v, s)
            ordered_fams = sorted(seen_f.values(), key=lambda x: -x[0])
            top_e, _top_s, top_src = ordered_fams[0]
            agree_n = min(2.0, sum(1.0 for eff_v, _, _ in ordered_fams[1:] if eff_v >= 7.0))
            items_math = [
                [f"most trusted reporting family: {top_src['domain']} ({top_src['trust']['category']})", round(top_e, 2)],
                [f"{int(agree_n)} additional independent family(ies) at 7+", agree_n] if agree_n else None,
                ["news question type", -PENALTY["news"]],
            ]
            items_math = [x for x in items_math if x is not None]
            conf10 = round(max(0.0, min(10.0, sum(v for _, v in items_math))), 1)
            band_code = band(conf10)
            band_lbl = BAND_LABEL[band_code]

            # Counterfactual system-only calculation across the same source families
            if not div:
                sys_ordered = sorted(seen_f.values(), key=lambda x: -x[1])
                sys_top = sys_ordered[0][1]
                sys_agree = min(2.0, sum(1.0 for _, sv, _ in sys_ordered[1:] if sv >= 7.0))
                sys_conf10 = round(max(0.0, min(10.0, sys_top + sys_agree - PENALTY["news"])), 1)
                sys_band = band(sys_conf10)
                if abs(sys_conf10 - conf10) >= 1.0 or sys_band != band_code:
                    div = {
                        "personal_value": f"{len(ordered_fams)} families",
                        "personal_confidence": conf10,
                        "personal_band": band_code,
                        "system_value": f"{len(sys_ordered)} families",
                        "system_confidence": sys_conf10,
                        "system_band": sys_band,
                    }

        source_stats_out: list[dict[str, Any]] = []
        for idx_s, s in enumerate(ordered_sources, 1):
            u = s["url"]
            raw_body = docs_by_url.get(u, "")
            snip = str(s.get("snippet") or "")
            cap_len = max(len(raw_body), len(snip))
            sent_len = min(cap_len, 1000 if raw_body else len(snip))
            source_stats_out.append(
                {
                    "id": u,
                    "chars_captured": cap_len,
                    "chars_sent": sent_len,
                    "was_cut": cap_len > sent_len,
                    "capture_mode": str(s.get("capture_mode") or ("fetch" if raw_body else "snippet")),
                }
            )

        with self.runtime.store_lock:
            if not self.runtime.pause_learning and scrubbed_q:
                self.runtime.store.log_query(scrubbed_q, domain_of(sources_for_card[0]["url"]) if sources_for_card else scrubbed_q[:40])
                if passages:
                    self.runtime.store.add_passages(passages[:6], scrubbed_q[:40], f"[conv:conv-news] {scrubbed_q}")

        findings_out: list[dict[str, Any]] = []
        for s in sources_for_card:
            if s.get("image_url"):
                findings_out.append(
                    {
                        "image_url": s["image_url"],
                        "title": s["title"],
                        "page_url": s["url"],
                    }
                )
            else:
                for fd in self.runtime.get_source_findings(s["url"], s["url"])[:1]:
                    findings_out.append(fd)

        cloud_used = [m for m in (planner_m, reader_m, used_writer) if self.runtime._parse_cloud_model_id(m)]
        privacy_note = (
            "100% local execution (0 cloud API calls; Brain & Mail stayed on device)."
            if not cloud_used
            else f"Cloud model(s) ({', '.join(dict.fromkeys(cloud_used))}) received scrubbed query + public news excerpts only; private Brain & Mail excluded."
        )

        elapsed_ms = int((time.perf_counter() - t_start) * 1000)
        answer_meta = {
            "pipeline": "satz_news",
            "question": raw_q,
            "scrubbed_query": scrubbed_q,
            "value": cons.get("value"),
            "confidence10": conf10,
            "band": band_code,
            "band_label": band_lbl,
            "qtype": qt,
            "items": items_math,
            "candidates": cons.get("candidates") or [],
            "conflicts": cons.get("conflicts") or [],
            "divergence": div,
            "steps": steps,
            "sources": sources_for_card,
            "passages": [
                {"domain": p.get("domain", ""), "url": p.get("url", ""), "title": p.get("title", ""), "trust": round(float(p.get("trust", 0.5)), 2), "text": str(p.get("text") or "")[:360]}
                for p in passages[:8]
            ],
            "models_used": {"planner": planner_m, "reader": reader_m, "analyzer": used_writer},
            "writer_fallback": wr_fallback,
            "writer_problems": wr_problems[:3],
            "privacy_disclosure": privacy_note,
            "ms": elapsed_ms,
        }

        return {
            "ok": True,
            "answer": answer_text,
            "model": used_writer,
            "sources": [{"url": s["url"], "title": s["title"], "domain": s["domain"]} for s in sources_for_card],
            "source_stats": source_stats_out,
            "findings": findings_out[:6],
            "answer_meta": answer_meta,
        }

    def reweigh_answer_meta(self, answer_meta: dict[str, Any]) -> dict[str, Any]:
        """Instant deterministic re-computation of a card's source weights without re-searching."""
        from src.planck3.qtype import PENALTY
        from src.planck3.registry import BAND_LABEL, band

        sources = list(answer_meta.get("sources") or [])
        if not sources:
            return answer_meta
        fam_best: dict[str, dict[str, Any]] = {}
        fam_sys: dict[str, float] = {}
        for s in sources:
            dom = str(s.get("domain") or "")
            t_rec = self._trust_for_domain(dom, use_personal=True)
            t_sys = self._trust_for_domain(dom, use_personal=False)
            s["trust"] = {
                "system": t_sys["system"],
                "personal": t_rec["personal"],
                "effective": t_rec["effective"],
                "category": t_rec["category"],
                "family": t_rec["family"],
                "why": t_rec["why"],
                "conflict": t_rec["conflict"],
            }
            fam = t_rec["family"]
            if fam not in fam_best or t_rec["effective"] > fam_best[fam]["trust"]["effective"]:
                fam_best[fam] = s
            fam_sys[fam] = max(fam_sys.get(fam, 0.0), float(t_sys["system"]))

        ranked = sorted(fam_best.values(), key=lambda x: -x["trust"]["effective"])
        top = ranked[0]
        agree = [f for f in ranked[1:] if f["trust"]["effective"] >= 7.0]
        pen = PENALTY.get(str(answer_meta.get("qtype") or "news"), 2.0)
        items = [[f"most trusted source stating it: {top['domain']} ({top['trust']['category']})", round(top["trust"]["effective"], 2)]]
        if agree:
            items.append([f"{len(agree)} more independent source(s) at 7+ agree: " + ", ".join(x["domain"] for x in agree[:3]), min(2.0, float(len(agree)))])
        if answer_meta.get("conflicts"):
            items.append(["divergent high-trust reporting present", -2.0])
        if pen:
            items.append(["news question type", -pen])
        conf10 = round(max(0.0, min(10.0, sum(v for _, v in items))), 1)
        b_code = band(conf10)

        sys_top = max(fam_sys.values()) if fam_sys else 5.0
        sys_agree = min(2.0, sum(1.0 for v in sorted(fam_sys.values(), reverse=True)[1:] if v >= 7.0))
        sys_conf = round(max(0.0, min(10.0, sys_top + sys_agree - pen)), 1)
        sys_band = band(sys_conf)
        div = (
            {
                "system_value": answer_meta.get("value") or top["domain"],
                "system_confidence": sys_conf,
                "system_band": sys_band,
            }
            if sys_band != b_code or abs(sys_conf - conf10) >= 0.5
            else None
        )

        updated = dict(answer_meta)
        updated["sources"] = sources
        updated["items"] = items
        updated["confidence10"] = conf10
        updated["band"] = b_code
        updated["band_label"] = BAND_LABEL[b_code]
        updated["divergence"] = div
        return updated

    # ── M29: Topics, Watches & Explicit Brain Promotion ─────────────────────
    def list_topics(self) -> dict[str, Any]:
        with self.runtime.store_lock:
            rows = self.runtime.store.db.execute(
                "SELECT t.*, w.last_checked_at, w.changed_at, w.badge_unread, w.last_value "
                "FROM satz_news_topics t LEFT JOIN satz_watches w ON w.watch_id = t.watch_id "
                "ORDER BY t.suppressed ASC, t.created_at DESC"
            ).fetchall()
        topics = [
            {
                "topic_id": r["topic_id"],
                "name": r["name"],
                "keywords": json.loads(r["keywords_json"] or "[]"),
                "suppressed": bool(r["suppressed"]),
                "watch_id": r["watch_id"],
                "last_checked_at": float(r["last_checked_at"] or 0.0),
                "changed_at": float(r["changed_at"] or 0.0),
                "badge_unread": bool(r["badge_unread"]),
                "last_value": r["last_value"] or "",
            }
            for r in rows
        ]
        return {"ok": True, "topics": topics}

    def manage_topic(self, data: dict[str, Any]) -> dict[str, Any]:
        action = str(data.get("action") or "add").strip().lower()
        now_ts = time.time()

        if action == "delete":
            tid = str(data.get("topic_id") or "").strip()
            with self.runtime.store_lock:
                row = self.runtime.store.db.execute("SELECT watch_id FROM satz_news_topics WHERE topic_id = ?", (tid,)).fetchone()
                if row and row["watch_id"]:
                    self.runtime.delete_watch(str(row["watch_id"]))
                self.runtime.store.db.execute("DELETE FROM satz_news_topics WHERE topic_id = ?", (tid,))
                self.runtime.store.db.commit()
            return {"ok": True, "deleted": tid}

        if action == "suppress":
            name = str(data.get("name") or "").strip()
            if not name:
                raise ValueError("Topic name required")
            tid = f"topic-{slugify(name)}"
            with self.runtime.store_lock:
                self.runtime.store.db.execute(
                    """
                    INSERT INTO satz_news_topics (topic_id, name, keywords_json, suppressed, created_at)
                    VALUES (?, ?, '[]', 1, ?)
                    ON CONFLICT(name) DO UPDATE SET suppressed = 1
                    """,
                    (tid, name, now_ts),
                )
                self.runtime.store.db.commit()
            self.recluster_and_rank()
            return {"ok": True, "suppressed": name}

        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("Topic name required")
        kws = data.get("keywords") or [w for w in _tokenize_title(name)]
        if isinstance(kws, str):
            kws = [x.strip() for x in kws.split(",") if x.strip()]
        tid = f"topic-{slugify(name)}"

        watch_id = None
        if data.get("watch", True):
            clean_q = self.runtime.brain.scrub_pii_for_external_query(name) or name
            w_res = self.runtime.add_watch(
                conversation_id="conv-news",
                query_or_url=f"{clean_q} latest news",
                cadence_seconds=float(data.get("cadence_seconds") or 3600.0),
                condition="any_change",
                title=f"topic: {clean_q}",
            )
            watch_id = (w_res.get("watch") or {}).get("watch_id")

        with self.runtime.store_lock:
            self.runtime.store.db.execute(
                """
                INSERT INTO satz_news_topics (topic_id, name, keywords_json, suppressed, watch_id, created_at)
                VALUES (?, ?, ?, 0, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    keywords_json = excluded.keywords_json,
                    suppressed = 0,
                    watch_id = COALESCE(excluded.watch_id, satz_news_topics.watch_id)
                """,
                (tid, name, json.dumps(kws, ensure_ascii=False), watch_id, now_ts),
            )
            self.runtime.store.db.commit()

        if not self.runtime.brain.locked:
            try:
                self.runtime.brain.upsert_entity(
                    entity_type="topic",
                    name=name,
                    summary=f"Followed Satz News beat (keywords: {', '.join(kws[:6])})",
                    attributes={"keywords": ", ".join(kws[:6]), "$source": f"news:{tid}"},
                    tier=2,
                    actor="user/news_topic",
                )
            except Exception:
                pass

        self.recluster_and_rank()
        return {"ok": True, "topic_id": tid, "name": name, "watch_id": watch_id}

    def save_cluster_to_brain(self, cluster_id: str) -> dict[str, Any]:
        if self.runtime.brain.locked:
            raise PermissionError("unlock a profile to save stories to your Brain")
        with self.runtime.store_lock:
            cr = self.runtime.store.db.execute(
                "SELECT * FROM satz_news_clusters WHERE cluster_id = ?",
                (cluster_id,),
            ).fetchone()
            if not cr:
                raise ValueError("Story cluster not found")
            arows = self.runtime.store.db.execute(
                "SELECT url, domain, title, trust_effective FROM satz_news_articles WHERE cluster_id = ? ORDER BY trust_effective DESC LIMIT 5",
                (cluster_id,),
            ).fetchall()

        top_domains = [f"{r['domain']} ({float(r['trust_effective']):.1f})" for r in arows]
        primary_url = str(arows[0]["url"]) if arows else ""
        ent = self.runtime.brain.upsert_entity(
            entity_type="story",
            name=str(cr["headline"])[:90],
            summary=f"[{cr['band']} · {float(cr['confidence10']):.1f}/10 across {cr['independent_families']} fam] {cr['headline']}",
            attributes={
                "confidence10": float(cr["confidence10"]),
                "band": cr["band"],
                "families": int(cr["independent_families"]),
                "sources": ", ".join(top_domains[:4]),
                "$source": f"news:{cluster_id}",
            },
            content=str(cr["summary_md"] or ""),
            source_url=primary_url,
            tier=2,
            actor="user/news_save",
        )
        return {"ok": True, "entity": ent}

    def get_status(self) -> dict[str, Any]:
        with self.runtime.store_lock:
            art_cnt = self.runtime.store.db.execute("SELECT COUNT(*) FROM satz_news_articles").fetchone()[0]
            cl_cnt = self.runtime.store.db.execute("SELECT COUNT(*) FROM satz_news_clusters WHERE is_hidden = 0").fetchone()[0]
            feed_cnt = self.runtime.store.db.execute("SELECT COUNT(*) FROM satz_news_feeds WHERE enabled = 1").fetchone()[0]
            topic_cnt = self.runtime.store.db.execute("SELECT COUNT(*) FROM satz_news_topics WHERE suppressed = 0").fetchone()[0]
        return {
            "articles": int(art_cnt or 0),
            "clusters": int(cl_cnt or 0),
            "feeds_enabled": int(feed_cnt or 0),
            "topics": int(topic_cnt or 0),
        }
