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
import queue
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from satz_brain import (
    _parse_temporal_query,
    _utc_iso_from_ts,
    neutralize_brain_directives_in_source,
    slugify,
)


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


def _complete_role_fast(
    runtime: Any,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.15,
    max_tokens: int = 420,
    thinking_budget: int | None = 0,
) -> str:
    """Calls `runtime._complete_role_prompt` with optional `thinking_budget`, keeping unit-test mocks compatible."""
    try:
        return runtime._complete_role_prompt(
            model_id,
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            thinking_budget=thinking_budget,
        )
    except TypeError:
        return runtime._complete_role_prompt(
            model_id,
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )


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
        raw = _complete_role_fast(
            self.runtime,
            self.model_id,
            READER_SYSTEM,
            user_prompt,
            temperature=0.05,
            max_tokens=160,
            thinking_budget=0,
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
        want = {n.lower() for n in names}
        for ch in parent:
            if _tag_name(ch) in want:
                if ch.text and ch.text.strip():
                    return ch.text.strip()
                inner = "".join(ch.itertext()).strip()
                if inner:
                    return inner
        return ""

    def _collect_texts(parent: ET.Element, *names: str) -> list[tuple[str, str]]:
        want = {n.lower() for n in names}
        out: list[tuple[str, str]] = []
        for ch in parent:
            if _tag_name(ch) in want:
                raw = ch.text.strip() if (ch.text and ch.text.strip()) else "".join(ch.itertext()).strip()
                if raw:
                    out.append((_tag_name(ch), raw))
        return out

    def _is_valid_feed_img(img_u: str) -> bool:
        low = (img_u or "").strip().lower()
        if not low.startswith(("http://", "https://")):
            return False
        return not any(b in low for b in ("sprite", "logo", "favicon", "avatar", "pixel", "1x1", ".svg"))

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

        text_frags = _collect_texts(el, "description", "summary", "content", "encoded")
        desc_raw = text_frags[0][1] if text_frags else ""
        snippet = _strip_html(desc_raw)[:600]
        if not snippet and len(text_frags) > 1:
            for _, frag in text_frags[1:]:
                cand_s = _strip_html(frag)[:600]
                if cand_s:
                    snippet = cand_s
                    break
        author = _strip_html(_child_text(el, "author", "creator", "name"))[:120]
        pub_raw = _child_text(el, "pubDate", "published", "updated", "date")
        pub_ts = _parse_pub_date(pub_raw, now_ts)

        image_url = ""
        for ch in el.iter():
            tn = _tag_name(ch)
            if tn not in ("thumbnail", "content", "enclosure"):
                continue
            typ = (ch.attrib.get("type") or "").lower().strip()
            if tn != "thumbnail" and typ.startswith(("video/", "audio/")):
                continue
            raw_u = (ch.attrib.get("url") or ch.attrib.get("href") or "").strip()
            if not raw_u:
                continue
            u_img = urllib.parse.urljoin(link, raw_u)
            if _is_valid_feed_img(u_img):
                image_url = u_img
                break
        if not image_url:
            for _, frag in text_frags:
                for img_m in re.finditer(r'<img\b[^>]+src=["\']([^"\']+)["\']', frag or "", re.I):
                    cand_img = urllib.parse.urljoin(link, html_lib.unescape(img_m.group(1)).strip())
                    if _is_valid_feed_img(cand_img):
                        image_url = cand_img
                        break
                if image_url:
                    break

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
                last_synced_at REAL DEFAULT 0.0,
                sync_status TEXT NOT NULL DEFAULT 'pending',
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
                brain_slug TEXT,
                brain_synced_at REAL DEFAULT 0.0,
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

            CREATE TABLE IF NOT EXISTS satz_news_translations (
                article_id TEXT NOT NULL,
                target_lang TEXT NOT NULL,
                source_lang TEXT NOT NULL DEFAULT '',
                title_tr TEXT NOT NULL DEFAULT '',
                snippet_tr TEXT NOT NULL DEFAULT '',
                body_tr TEXT NOT NULL DEFAULT '',
                model_id TEXT NOT NULL DEFAULT '',
                updated_at REAL NOT NULL DEFAULT 0.0,
                PRIMARY KEY (article_id, target_lang)
            );

            CREATE TABLE IF NOT EXISTS satz_news_followed_stories (
                story_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                summary_overview TEXT NOT NULL DEFAULT '',
                summary_model TEXT NOT NULL DEFAULT '',
                keywords_json TEXT NOT NULL DEFAULT '[]',
                seed_cluster_id TEXT,
                anchor_domain TEXT,
                lead_image TEXT,
                confidence10 REAL NOT NULL DEFAULT 5.0,
                band TEXT NOT NULL DEFAULT 'good',
                independent_families INTEGER NOT NULL DEFAULT 1,
                update_count INTEGER NOT NULL DEFAULT 0,
                unread_updates INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                last_synthesized_at REAL NOT NULL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS satz_news_followed_story_updates (
                story_id TEXT NOT NULL,
                article_id TEXT NOT NULL,
                url TEXT NOT NULL,
                domain TEXT NOT NULL,
                family TEXT NOT NULL,
                title TEXT NOT NULL,
                snippet TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT 'en',
                image_url TEXT NOT NULL DEFAULT '',
                published_at REAL NOT NULL,
                added_at REAL NOT NULL,
                trust_system REAL NOT NULL,
                trust_effective REAL NOT NULL,
                conflict INTEGER NOT NULL DEFAULT 0,
                match_score REAL NOT NULL DEFAULT 0.0,
                is_seed INTEGER NOT NULL DEFAULT 0,
                is_new INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (story_id, article_id)
            );
            CREATE INDEX IF NOT EXISTS idx_news_followed_upd_story
                ON satz_news_followed_story_updates(story_id, published_at DESC);
            CREATE INDEX IF NOT EXISTS idx_news_tr_lang ON satz_news_translations(target_lang, updated_at DESC);
            """
        )
        feed_cols = {
            r[1] for r in db_conn.execute("PRAGMA table_info('satz_news_feeds')").fetchall()
        }
        if "last_synced_at" not in feed_cols:
            db_conn.execute("ALTER TABLE satz_news_feeds ADD COLUMN last_synced_at REAL DEFAULT 0.0")
        if "sync_status" not in feed_cols:
            db_conn.execute("ALTER TABLE satz_news_feeds ADD COLUMN sync_status TEXT NOT NULL DEFAULT 'pending'")

        cl_cols = {
            r[1] for r in db_conn.execute("PRAGMA table_info('satz_news_clusters')").fetchall()
        }
        if "brain_slug" not in cl_cols:
            db_conn.execute("ALTER TABLE satz_news_clusters ADD COLUMN brain_slug TEXT")
        if "brain_synced_at" not in cl_cols:
            db_conn.execute("ALTER TABLE satz_news_clusters ADD COLUMN brain_synced_at REAL DEFAULT 0.0")
        if "updated_at" not in feed_cols:
            db_conn.execute("ALTER TABLE satz_news_feeds ADD COLUMN updated_at REAL NOT NULL DEFAULT 0.0")
        topic_cols = {
            r[1] for r in db_conn.execute("PRAGMA table_info('satz_news_topics')").fetchall()
        }
        if "updated_at" not in topic_cols:
            db_conn.execute("ALTER TABLE satz_news_topics ADD COLUMN updated_at REAL NOT NULL DEFAULT 0.0")
            db_conn.execute(
                "UPDATE satz_news_topics SET updated_at = COALESCE(created_at, 0.0) WHERE updated_at = 0.0"
            )
        db_conn.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS trg_news_topics_ai_ts AFTER INSERT ON satz_news_topics
            WHEN COALESCE(NEW.updated_at, 0.0) <= 0.0
            BEGIN
                UPDATE satz_news_topics
                SET updated_at = (julianday('now') - 2440587.5) * 86400.0
                WHERE topic_id = NEW.topic_id;
            END;
            CREATE TRIGGER IF NOT EXISTS trg_news_topics_au_ts AFTER UPDATE OF name, keywords_json, suppressed, watch_id ON satz_news_topics
            WHEN COALESCE(NEW.updated_at, 0.0) <= COALESCE(OLD.updated_at, 0.0)
            BEGIN
                UPDATE satz_news_topics
                SET updated_at = (julianday('now') - 2440587.5) * 86400.0
                WHERE topic_id = NEW.topic_id;
            END;
            CREATE TRIGGER IF NOT EXISTS trg_news_feeds_ai_ts AFTER INSERT ON satz_news_feeds
            WHEN COALESCE(NEW.updated_at, 0.0) <= 0.0
            BEGIN
                UPDATE satz_news_feeds
                SET updated_at = (julianday('now') - 2440587.5) * 86400.0
                WHERE feed_id = NEW.feed_id;
            END;
            CREATE TRIGGER IF NOT EXISTS trg_news_feeds_au_ts AFTER UPDATE OF domain, feed_url, title, category, language, enabled ON satz_news_feeds
            WHEN COALESCE(NEW.updated_at, 0.0) <= COALESCE(OLD.updated_at, 0.0)
            BEGIN
                UPDATE satz_news_feeds
                SET updated_at = (julianday('now') - 2440587.5) * 86400.0
                WHERE feed_id = NEW.feed_id;
            END;
            """
        )
        db_conn.commit()

    def seed_starter_feeds(self, db_conn: sqlite3.Connection | None = None) -> None:
        feeds = self.overlay.get("starter_feeds") or []
        if not feeds:
            return
        conn = db_conn or self.runtime.store.db
        deleted_ids: set[str] = set()
        try:
            tb_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='satz_sync_tombstones'"
            ).fetchone()
            if tb_exists:
                deleted_ids = {
                    str(r[0])
                    for r in conn.execute(
                        "SELECT row_key FROM satz_sync_tombstones WHERE table_name = 'satz_news_feeds'"
                    ).fetchall()
                }
        except Exception:
            deleted_ids = set()
        for f in feeds:
            fid = str(f.get("feed_id") or slugify(str(f.get("feed_url") or "")))
            if fid in deleted_ids:
                continue
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
                "SELECT feed_id, domain, feed_url, title, category, language, enabled, last_fetched_at, last_synced_at, sync_status, error_count FROM satz_news_feeds"
            ).fetchall()

        feeds_by_domain: dict[str, list[dict[str, Any]]] = {}
        for fr in feed_rows:
            d = str(fr["domain"] or "").lower().removeprefix("www.")
            lf = float(fr["last_fetched_at"] or 0.0)
            ls = float(fr["last_synced_at"] or lf or 0.0)
            feeds_by_domain.setdefault(d, []).append(
                {
                    "feed_id": fr["feed_id"],
                    "feed_url": fr["feed_url"],
                    "title": fr["title"],
                    "language": fr["language"],
                    "enabled": bool(fr["enabled"]),
                    "last_fetched_at": lf,
                    "last_synced_at": ls,
                    "sync_status": str(fr["sync_status"] or ("synced" if (fr["enabled"] and lf > 0) else "pending")),
                    "synced": bool(fr["enabled"] and (lf > 0 or ls > 0)),
                    "error_count": int(fr["error_count"] or 0),
                }
            )

        from src.planck3.registry import trust_record

        domains_map = getattr(reg, "domains", None) or {}
        categories_map = getattr(reg, "categories", None) or {}
        trust_extra_domains: set[str] = set()
        try:
            sgs_trust_path = Path(self.runtime.sgs_root) / "config" / "planck3" / "source_trust.json"
            if sgs_trust_path.exists():
                t_raw = json.loads(sgs_trust_path.read_text(encoding="utf-8"))
                trust_extra_domains = {
                    str(k).lower().removeprefix("www.")
                    for k in (t_raw.get("domains") or {}).keys()
                    if str(k).strip()
                }
        except Exception:
            trust_extra_domains = set()
        all_domains = set(domains_map.keys())
        all_domains |= trust_extra_domains
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
        last_sync_at = self._get_meta_float("news_last_sync_at")
        interval_secs = float(getattr(self.runtime, "news_refresh_interval_secs", 3600.0))
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
            "sync_interval_seconds": interval_secs,
            "last_sync_at": last_sync_at,
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
                    "UPDATE satz_news_feeds SET enabled = ?, sync_status = ? WHERE feed_id = ?",
                    (enabled, "pending" if enabled else "paused", feed_id),
                )
                self.runtime.store.db.commit()
            if enabled and getattr(self.runtime, "news_wake_event", None) is not None:
                self.runtime.news_wake_event.set()
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
                    (feed_id, domain, feed_url, title, category, language, enabled, sync_status)
                    VALUES (?, ?, ?, ?, ?, ?, 1, 'pending')
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
            if getattr(self.runtime, "news_wake_event", None) is not None:
                self.runtime.news_wake_event.set()
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
        from satz_translate import detect_language

        url = str(item.get("url") or "").strip()
        if not url:
            return ""
        domain = str(item.get("domain") or domain_of(url) or "").lower().removeprefix("www.")
        title = str(item.get("title") or domain).strip()
        snippet = str(item.get("snippet") or "")[:1200]
        body_text = str(item.get("body_text") or snippet or "")[:30000]
        eff_lang = detect_language(f"{title}\n{snippet}\n{body_text[:1000]}", hint_lang=str(item.get("language") or language or "en"))
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
                    language = CASE WHEN excluded.language != '' THEN excluded.language ELSE satz_news_articles.language END,
                    image_url = COALESCE(NULLIF(excluded.image_url, ''), satz_news_articles.image_url),
                    family = excluded.family,
                    trust_system = excluded.trust_system,
                    trust_effective = excluded.trust_effective,
                    wire_origin = COALESCE(excluded.wire_origin, satz_news_articles.wire_origin),
                    fetched_at = excluded.fetched_at
                """,
                (
                    art_id, url, canonical_url, domain, family, title, snippet, body_text,
                    item.get("translated_text"), eff_lang, image_url, author, pub_ts, now_ts,
                    float(t_sys), float(t_eff), wire_origin,
                ),
            )
            if snippet or body_text:
                pub_iso_short = datetime.fromtimestamp(pub_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%MZ")
                safe_title = neutralize_brain_directives_in_source(title)
                safe_excerpt = neutralize_brain_directives_in_source((body_text or snippet)[:1200])
                p_txt = f"{safe_title} ({pub_iso_short}): {safe_excerpt}"
                self.runtime.store.add_passages(
                    [{"url": url, "domain": domain, "title": safe_title, "text": p_txt}],
                    entity=domain,
                    question=f"[conv:conv-news] news feed {domain}",
                )
            self.runtime.store.db.commit()
        return art_id

    def _get_meta_float(self, key: str, default: float = 0.0) -> float:
        with self.runtime.store_lock:
            try:
                row = self.runtime.store.db.execute(
                    "SELECT value FROM satz_meta WHERE key = ?",
                    (key,),
                ).fetchone()
                return float(row["value"]) if (row and row["value"] is not None) else default
            except Exception:
                return default

    def _set_meta_float(self, key: str, value: float) -> None:
        with self.runtime.store_lock:
            self.runtime.store.db.execute(
                "INSERT OR REPLACE INTO satz_meta (key, value) VALUES (?, ?)",
                (key, str(round(float(value), 3))),
            )
            self.runtime.store.db.commit()

    def _primary_translation_target(self) -> str:
        tr = getattr(self.runtime, "translator", None)
        if tr is not None:
            try:
                return str(tr.get_preferences().get("primary_language") or "en")
            except Exception:
                pass
        return "en"

    def _index_top_clusters_to_sources(self, limit: int = 24) -> int:
        t_target = self._primary_translation_target()
        with self.runtime.store_lock:
            cl_rows = self.runtime.store.db.execute(
                """
                SELECT cluster_id, headline, summary_md, confidence10, band,
                       independent_families, updated_at
                FROM satz_news_clusters
                WHERE is_hidden = 0
                ORDER BY story_rank DESC, updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            indexed = 0
            for cr in cl_rows:
                cid = str(cr["cluster_id"])
                arts = self.runtime.store.db.execute(
                    """
                    SELECT a.url, a.domain, a.title, a.snippet, a.body_text, a.image_url, a.published_at, a.trust_effective,
                           COALESCE(nt.title_tr, '') AS title_tr,
                           COALESCE(nt.snippet_tr, '') AS snippet_tr,
                           COALESCE(nt.body_tr, '') AS body_tr
                    FROM satz_news_articles a
                    LEFT JOIN satz_news_translations nt ON nt.article_id = a.article_id AND nt.target_lang = ?
                    WHERE a.cluster_id = ?
                    ORDER BY a.trust_effective DESC, a.published_at DESC
                    LIMIT 4
                    """,
                    (t_target, cid),
                ).fetchall()
                if not arts:
                    continue
                lead = arts[0]
                primary_url = str(lead["url"] or "")
                primary_dom = str(lead["domain"] or "")
                pub_ts = float(cr["updated_at"] or lead["published_at"] or time.time())
                pub_iso = _utc_iso_from_ts(pub_ts)
                eff_headline = str(lead["title_tr"] or cr["headline"] or primary_dom)
                parts = [
                    f"[{pub_iso} · {cr['band']} {float(cr['confidence10']):.1f}/10 across {int(cr['independent_families'])} fam] {eff_headline}",
                    str(cr["summary_md"] or ""),
                ]
                cluster_findings: list[dict[str, str]] = []
                for ar in arts:
                    ex_raw = ar["body_tr"] or ar["snippet_tr"] or ar["body_text"] or ar["snippet"] or ""
                    ex = str(ex_raw)[:500].strip()
                    ar_title = str(ar["title_tr"] or ar["title"] or "")
                    ar_img = str(ar["image_url"] or "").strip()
                    if ar_img.startswith(("http://", "https://")) and len(cluster_findings) < 3:
                        cluster_findings.append(
                            {
                                "image_url": ar_img,
                                "title": (ar_title or primary_dom)[:120],
                                "page_url": str(ar["url"] or primary_url),
                            }
                        )
                    if ex:
                        parts.append(f"- ({ar['domain']}) {ar_title}: {ex}")
                safe_text = neutralize_brain_directives_in_source("\n".join(parts))[:8000]
                self.runtime.store.db.execute(
                    """
                    INSERT OR REPLACE INTO satz_sources
                    (source_id, conversation_id, url, domain, title, text, extra_json, findings_json, capture_mode, updated_at)
                    VALUES (?, 'conv-news', ?, ?, ?, ?, ?, ?, 'rss', ?)
                    """,
                    (
                        f"news:cluster:{cid}",
                        primary_url,
                        primary_dom,
                        str(cr["headline"] or primary_dom)[:180],
                        safe_text,
                        json.dumps(
                            {
                                "cluster_id": cid,
                                "confidence10": float(cr["confidence10"]),
                                "band": cr["band"],
                                "families": int(cr["independent_families"]),
                                "published_at": pub_iso,
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(cluster_findings, ensure_ascii=False),
                        pub_ts,
                    ),
                )
                indexed += 1
            self.runtime.store.db.commit()
            return indexed

    def process_top_stories_to_brain(
        self,
        limit: int = 12,
        min_confidence: float = 5.5,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Processes top ranked & corroborated news clusters into SatzBrain (`News/Stories`)
        with explicit publication/sync timestamps, source provenance, and prompt-injection neutralization.
        """
        if self.runtime.brain.locked:
            return {"ok": False, "skipped_locked": True, "processed": 0, "updated": 0}

        now_ts = time.time()
        sync_iso = _utc_iso_from_ts(now_ts)
        with self.runtime.store_lock:
            candidates = self.runtime.store.db.execute(
                """
                SELECT * FROM satz_news_clusters
                WHERE is_hidden = 0
                ORDER BY story_rank DESC, updated_at DESC
                LIMIT ?
                """,
                (max(limit * 3, 24),),
            ).fetchall()

        high_conf = [c for c in candidates if float(c["confidence10"] or 0.0) >= min_confidence]
        selected = high_conf[:limit] if len(high_conf) >= min(4, limit) else list(candidates)[:limit]
        if len(high_conf) > 0 and len(high_conf) < limit:
            seen_cids = {str(c["cluster_id"]) for c in high_conf}
            selected = list(high_conf) + [c for c in candidates if str(c["cluster_id"]) not in seen_cids]
            selected = selected[:limit]

        processed = 0
        updated = 0
        stored_slugs: list[str] = []

        for cr in selected:
            cid = str(cr["cluster_id"])
            upd_ts = float(cr["updated_at"] or now_ts)
            first_ts = float(cr["first_seen_at"] or upd_ts)
            prev_slug = str(cr["brain_slug"] or "").strip()
            prev_sync = float(cr["brain_synced_at"] or 0.0)
            if not force and prev_slug and prev_sync >= upd_ts:
                continue

            with self.runtime.store_lock:
                art_rows = self.runtime.store.db.execute(
                    """
                    SELECT url, domain, family, title, snippet, body_text, published_at, trust_effective
                    FROM satz_news_articles
                    WHERE cluster_id = ?
                    ORDER BY trust_effective DESC, published_at DESC
                    """,
                    (cid,),
                ).fetchall()
            if not art_rows:
                continue

            top_domains = list(dict.fromkeys(str(a["domain"]) for a in art_rows if a["domain"]))
            primary_url = str(art_rows[0]["url"] or "")
            raw_headline = str(cr["headline"] or art_rows[0]["title"] or "Top Story").strip()
            safe_headline = neutralize_brain_directives_in_source(raw_headline)
            alt_titles = [
                neutralize_brain_directives_in_source(str(a["title"] or "").strip())[:100]
                for a in art_rows[1:4]
                if a["title"] and str(a["title"]).strip().lower() != raw_headline.lower()
            ]
            tags = [str(t).strip() for t in json.loads(cr["topic_tags_json"] or "[]") if str(t).strip()]
            reasons = [str(r).strip() for r in json.loads(cr["brain_match_reasons_json"] or "[]") if str(r).strip()]

            pub_iso = _utc_iso_from_ts(upd_ts)
            first_iso = _utc_iso_from_ts(first_ts)
            pub_short = pub_iso[:16].replace("T", " ") + "Z"

            src_lines: list[str] = []
            for ar in art_rows[:4]:
                ar_pub = _utc_iso_from_ts(float(ar["published_at"] or upd_ts))[:16].replace("T", " ") + "Z"
                ar_title = neutralize_brain_directives_in_source(str(ar["title"] or ""))
                ar_snip = neutralize_brain_directives_in_source((ar["snippet"] or ar["body_text"] or "")[:320])
                src_lines.append(
                    f"- [{ar['domain']} · {float(ar['trust_effective'] or 5.0):.1f}/10 · {ar_pub}] {ar_title}: {ar_snip} ({ar['url']})"
                )

            safe_summary_md = neutralize_brain_directives_in_source(str(cr["summary_md"] or ""))
            content_parts = [
                f"Published: {pub_iso} | Synced: {sync_iso} | Confidence: {float(cr['confidence10']):.1f}/10 ({cr['band']}) across {int(cr['independent_families'])} family(ies)",
            ]
            if tags:
                content_parts.append(f"Topics: {', '.join(tags)}")
            if reasons:
                content_parts.append(f"Relevance: {'; '.join(reasons[:3])}")
            content_parts.extend(["", "### Corroborated Summary", safe_summary_md, "", "### Synced Sources", *src_lines])

            rels: dict[str, list[str]] = {"sources": top_domains[:4]}
            if tags:
                rels["about"] = tags[:4]

            ent = self.runtime.brain.upsert_entity(
                entity_type="story",
                name=safe_headline[:90],
                summary=f"[{cr['band']} · {float(cr['confidence10']):.1f}/10 · {int(cr['independent_families'])} fam · {pub_short}] {safe_headline}",
                attributes={
                    "confidence10": float(cr["confidence10"]),
                    "band": cr["band"],
                    "families": int(cr["independent_families"]),
                    "sources": ", ".join(top_domains[:4]),
                    "topics": ", ".join(tags[:4]) if tags else "",
                    "published_at": pub_iso,
                    "first_seen_at": first_iso,
                    "synced_at": sync_iso,
                    "sync_mode": "hourly_feed",
                    "$published_ts": round(upd_ts, 3),
                    "$synced_ts": round(now_ts, 3),
                    "$cluster_id": cid,
                    "$source": f"news:{cid}",
                },
                content="\n".join(content_parts),
                relationships=rels,
                aliases=alt_titles,
                source_url=primary_url,
                tier=2,
                actor="news/hourly_sync",
            )
            slug = str(ent.get("slug") or "")
            with self.runtime.store_lock:
                self.runtime.store.db.execute(
                    "UPDATE satz_news_clusters SET brain_slug = ?, brain_synced_at = ? WHERE cluster_id = ?",
                    (slug, now_ts, cid),
                )
                self.runtime.store.db.commit()
            if prev_slug:
                updated += 1
            else:
                processed += 1
            stored_slugs.append(slug)

        self._set_meta_float("news_last_brain_sync_at", now_ts)
        return {
            "ok": True,
            "skipped_locked": False,
            "processed": processed,
            "updated": updated,
            "total_synced": processed + updated,
            "slugs": stored_slugs,
        }

    def refresh_news_feeds(
        self,
        force: bool = False,
        include_topic_search: bool = False,
        fetcher: Callable[[str, str | None, str | None], dict[str, Any]] | None = None,
        process_to_brain: bool = True,
        min_interval_secs: float | None = None,
        translate_recent: bool = True,
    ) -> dict[str, Any]:
        """
        Polls enabled RSS/Atom feeds as synced sources on an hourly cadence (`3600s` default)
        using zero LLM tokens (conditional HTTP GET), reclusters top stories, indexes them into
        local synced storage, and processes corroborated top stories into SatzBrain with timestamps.
        """
        now_ts = time.time()
        http_get = fetcher or self._fetch_feed_http
        interval_secs = float(
            min_interval_secs
            if min_interval_secs is not None
            else getattr(self.runtime, "news_refresh_interval_secs", 3600.0)
        )

        with self.runtime.store_lock:
            self.seed_starter_feeds(self.runtime.store.db)
            feeds = self.runtime.store.db.execute(
                "SELECT * FROM satz_news_feeds WHERE enabled = 1"
            ).fetchall()

        fetched_feeds = 0
        new_articles = 0
        not_modified = 0
        skipped_interval = 0
        errors: list[str] = []

        due_feeds = []
        for fr in feeds:
            last_f = float(fr["last_fetched_at"] or 0.0)
            backoff_until = float(fr["backoff_until"] or 0.0)
            if not force and backoff_until > now_ts:
                skipped_interval += 1
                continue
            if not force and last_f > 0 and (now_ts - last_f) < interval_secs:
                skipped_interval += 1
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
                        "UPDATE satz_news_feeds SET error_count = ?, backoff_until = ?, sync_status = 'backoff' WHERE feed_id = ?",
                        (err_cnt, backoff, fid),
                    )
                    self.runtime.store.db.commit()
                continue
            assert res is not None
            if res.get("not_modified"):
                not_modified += 1
                with self.runtime.store_lock:
                    self.runtime.store.db.execute(
                        "UPDATE satz_news_feeds SET last_fetched_at = ?, last_synced_at = ?, sync_status = 'unchanged_304', error_count = 0 WHERE feed_id = ?",
                        (now_ts, now_ts, fid),
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
                    SET etag = ?, last_modified = ?, last_fetched_at = ?, last_synced_at = ?,
                        sync_status = 'synced', error_count = 0, backoff_until = 0.0
                    WHERE feed_id = ?
                    """,
                    (res.get("etag"), res.get("last_modified"), now_ts, now_ts, fid),
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

        tr_stats = (
            self.translate_recent_untranslated(limit=35, recluster=False, background_indexation=True)
            if translate_recent
            else {"translated_articles": 0}
        )
        clusters_count = self.recluster_and_rank()
        sources_indexed = self._index_top_clusters_to_sources()
        brain_sync = (
            self.process_top_stories_to_brain(limit=12, force=False)
            if process_to_brain
            else {"processed": 0, "updated": 0, "total_synced": 0, "skipped_locked": self.runtime.brain.locked}
        )
        if due_feeds or fetched_feeds > 0 or not_modified > 0:
            self._set_meta_float("news_last_sync_at", now_ts)
        return {
            "ok": True,
            "fetched_feeds": fetched_feeds,
            "not_modified": not_modified,
            "skipped_interval": skipped_interval,
            "articles_ingested": new_articles,
            "articles_translated": int(tr_stats.get("translated_articles") or 0),
            "clusters": clusters_count,
            "sources_indexed": sources_indexed,
            "brain_synced": int(brain_sync.get("total_synced") or 0),
            "brain_skipped_locked": bool(brain_sync.get("skipped_locked")),
            "sync_interval_seconds": interval_secs,
            "last_sync_at": self._get_meta_float("news_last_sync_at", now_ts if due_feeds else 0.0),
            "errors": errors[:5],
        }

    def translate_recent_untranslated(
        self,
        *,
        limit: int = 35,
        recluster: bool = False,
        background_indexation: bool = False,
    ) -> dict[str, Any]:
        """
        Translates recent non-allowed-language news headlines & snippets during indexation
        using the active profile's cheapest translation model into `primary_language`.
        """
        translator = getattr(self.runtime, "translator", None)
        if translator is None:
            return {"translated_articles": 0}
        prefs = translator.get_preferences()
        if background_indexation and not prefs.get("auto_translate_news", True):
            return {"translated_articles": 0, "skipped": "disabled"}

        resolved = translator.resolve_translation_model()
        is_mocked = "_complete_role_prompt" in getattr(self.runtime, "__dict__", {})
        if (
            background_indexation
            and not resolved.get("is_cloud")
            and getattr(self.runtime, "gemma_model", None) is None
            and not is_mocked
        ):
            return {"translated_articles": 0, "skipped": "no_cloud_or_loaded_local"}

        tgt = prefs["primary_language"]
        cutoff = time.time() - 7 * 86400.0
        lim = max(1, min(100, int(limit or 35)))

        from satz_translate import detect_language, normalize_language_code

        known_bases = sorted(
            {
                normalize_language_code(k).split("-", 1)[0]
                for k in (prefs.get("known_languages") or ["en"])
                if normalize_language_code(k)
            }
            or {"en"}
        )
        kb_ph = ",".join("?" for _ in known_bases)

        with self.runtime.store_lock:
            rows = self.runtime.store.db.execute(
                f"""
                SELECT a.article_id, a.title, a.snippet, a.body_text, a.language, a.domain, a.url, a.published_at
                FROM satz_news_articles a
                LEFT JOIN satz_news_translations nt
                  ON nt.article_id = a.article_id AND nt.target_lang = ?
                WHERE a.published_at >= ?
                  AND (nt.article_id IS NULL OR (nt.title_tr = '' AND nt.snippet_tr = ''))
                ORDER BY
                  CASE WHEN LOWER(COALESCE(NULLIF(a.language, ''), 'en')) NOT IN ({kb_ph}) THEN 0 ELSE 1 END,
                  a.published_at DESC
                LIMIT ?
                """,
                (tgt, cutoff, *known_bases, max(200, lim * 6)),
            ).fetchall()

        seg_map: dict[str, str] = {}
        art_meta: dict[str, dict[str, str]] = {}
        for r in rows:
            if len(art_meta) >= lim:
                break
            aid = str(r["article_id"])
            title = str(r["title"] or "").strip()
            snippet = str(r["snippet"] or r["body_text"] or "").strip()[:800]
            eff_lang = detect_language(f"{title}\n{snippet}", hint_lang=str(r["language"] or "en"))
            if translator.is_language_allowed(eff_lang, prefs=prefs):
                continue
            art_meta[aid] = {"source_lang": eff_lang, "title": title, "snippet": snippet, "url": str(r["url"] or ""), "domain": str(r["domain"] or ""), "published_at": float(r["published_at"] or time.time())}
            if title:
                seg_map[f"t:{aid}"] = title[:400]
            if snippet:
                seg_map[f"s:{aid}"] = snippet[:800]

        if not seg_map:
            return {"translated_articles": 0, "target_lang": tgt}

        tr_res = translator.translate_segments(
            seg_map,
            target_lang=tgt,
            context_hint="news headlines and article summaries",
        )
        tr_dict = tr_res.get("translations") or {}
        model_id = str(tr_res.get("model") or resolved["model_id"])
        now_ts = time.time()
        updated = 0
        with self.runtime.store_lock:
            for aid, info in art_meta.items():
                t_tr = str(tr_dict.get(f"t:{aid}") or "").strip()
                s_tr = str(tr_dict.get(f"s:{aid}") or "").strip()
                if not t_tr and not s_tr:
                    continue
                self.runtime.store.db.execute(
                    """
                    INSERT INTO satz_news_translations
                      (article_id, target_lang, source_lang, title_tr, snippet_tr, body_tr, model_id, updated_at)
                    VALUES (?, ?, ?, ?, ?, '', ?, ?)
                    ON CONFLICT(article_id, target_lang) DO UPDATE SET
                      source_lang = excluded.source_lang,
                      title_tr = CASE WHEN LENGTH(excluded.title_tr) > 0 THEN excluded.title_tr ELSE satz_news_translations.title_tr END,
                      snippet_tr = CASE WHEN LENGTH(excluded.snippet_tr) > 0 THEN excluded.snippet_tr ELSE satz_news_translations.snippet_tr END,
                      model_id = excluded.model_id,
                      updated_at = excluded.updated_at
                    """,
                    (aid, tgt, info["source_lang"], t_tr, s_tr, model_id, now_ts),
                )
                if info["source_lang"]:
                    self.runtime.store.db.execute(
                        "UPDATE satz_news_articles SET language = ? WHERE article_id = ?",
                        (info["source_lang"], aid),
                    )
                if s_tr or t_tr:
                    pub_iso = _utc_iso_from_ts(float(info["published_at"]))
                    p_txt = neutralize_brain_directives_in_source(f"{t_tr or info['title']} ({pub_iso}): {s_tr or info['snippet']}")
                    self.runtime.store.add_passages(
                        [{"url": info["url"], "domain": info["domain"], "title": t_tr or info["title"], "text": p_txt}],
                        entity=info["domain"],
                        question=f"[conv:conv-news] news feed translated {info['source_lang']}->{tgt}",
                    )
                updated += 1
            self.runtime.store.db.commit()

        if recluster and updated > 0:
            self.recluster_and_rank()
            self._index_top_clusters_to_sources()
        return {"translated_articles": updated, "target_lang": tgt, "model": model_id}

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
        queries: list[str] = []
        with self.runtime.store_lock:
            frows = self.runtime.store.db.execute(
                "SELECT title FROM satz_news_followed_stories WHERE status = 'active' ORDER BY updated_at DESC LIMIT 2"
            ).fetchall()
        for fr in frows:
            cleaned = self.runtime.brain.scrub_pii_for_external_query(str(fr["title"] or ""))
            if len(cleaned) >= 4:
                q = f"{cleaned[:72]} update news"
                if q not in queries:
                    queries.append(q)
        signals = self.build_local_interest_signals()
        for s in signals:
            cleaned = self.runtime.brain.scrub_pii_for_external_query(s["term"])
            if len(cleaned) >= 4:
                q = f"{cleaned} latest news"
                if q not in queries:
                    queries.append(q)
            if len(queries) >= limit:
                break
        return queries[:limit]

    # ── M28: Story Clustering, Confidence Scoring & "For You" Matching ──────
    def recluster_and_rank(self) -> int:
        from src.planck3.qtype import PENALTY
        from src.planck3.registry import BAND_LABEL, band

        now_ts = time.time()
        cutoff = now_ts - 7 * 86400.0
        t_target = self._primary_translation_target()
        with self.runtime.store_lock:
            art_rows = self.runtime.store.db.execute(
                """
                SELECT a.*, COALESCE(nt.title_tr, '') AS title_tr,
                       COALESCE(nt.snippet_tr, '') AS snippet_tr,
                       COALESCE(nt.body_tr, '') AS body_tr
                FROM satz_news_articles a
                LEFT JOIN satz_news_translations nt ON nt.article_id = a.article_id AND nt.target_lang = ?
                WHERE a.published_at >= ?
                ORDER BY a.published_at DESC
                LIMIT 250
                """,
                (t_target, cutoff),
            ).fetchall()

        if not art_rows:
            return 0

        # Refresh trust scores under current profile's personal overrides
        articles: list[dict[str, Any]] = []
        for r in art_rows:
            dom = str(r["domain"])
            t_rec = self._trust_for_domain(dom, use_personal=True)
            t_sys = self._trust_for_domain(dom, use_personal=False)
            toks = _tokenize_title(f"{r['title'] or ''} {r['title_tr'] or ''}")
            articles.append(
                {
                    "article_id": r["article_id"],
                    "url": r["url"],
                    "domain": dom,
                    "family": r["family"] or t_rec["family"],
                    "title": r["title"],
                    "title_tr": r["title_tr"],
                    "snippet": r["snippet"] or "",
                    "snippet_tr": r["snippet_tr"] or "",
                    "body_text": r["body_text"] or "",
                    "translated_text": r["body_tr"] or r["translated_text"] or r["snippet_tr"] or None,
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

                # Local Brain / Mail relevance matching (uses both original & translated headlines/snippets)
                cluster_hay = " ".join(
                    f"{a['title']} {a.get('title_tr') or ''} {a['snippet'][:240]} {str(a.get('snippet_tr') or '')[:240]}"
                    for a in arts[:4]
                ).lower()
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
        try:
            self.sync_followed_stories(synthesize_new=True, allow_llm_in_bg=False)
        except Exception:
            pass
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
        t_target = self._primary_translation_target()

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
                    f"""
                    SELECT ar.*,
                           COALESCE(nt.title_tr, '') AS title_tr,
                           COALESCE(nt.snippet_tr, '') AS snippet_tr,
                           COALESCE(nt.body_tr, '') AS body_tr,
                           COALESCE(nt.source_lang, '') AS tr_source_lang,
                           COALESCE(nt.target_lang, '') AS tr_target_lang
                    FROM satz_news_articles ar
                    LEFT JOIN satz_news_translations nt ON nt.article_id = ar.article_id AND nt.target_lang = ?
                    WHERE ar.cluster_id IN ({ph})
                    ORDER BY ar.trust_effective DESC, ar.published_at DESC
                    """,
                    (t_target, *cids),
                ).fetchall()
                for ar in arows:
                    dom = str(ar["domain"])
                    t_rec = self._trust_for_domain(dom, use_personal=not explore)
                    t_sys = self._trust_for_domain(dom, use_personal=False)
                    eff_tr = str(ar["body_tr"] or ar["translated_text"] or ar["snippet_tr"] or "") or None
                    articles_by_cluster.setdefault(ar["cluster_id"], []).append(
                        {
                            "article_id": ar["article_id"],
                            "url": ar["url"],
                            "domain": dom,
                            "family": ar["family"],
                            "title": ar["title"],
                            "title_tr": str(ar["title_tr"] or ""),
                            "snippet": ar["snippet"],
                            "snippet_tr": str(ar["snippet_tr"] or ""),
                            "body_text": ar["body_text"],
                            "translated_text": eff_tr,
                            "language": ar["language"] or "en",
                            "translation_source_lang": str(ar["tr_source_lang"] or ""),
                            "translation_target_lang": str(ar["tr_target_lang"] or ""),
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
            lead_tr_title = next((a["title_tr"] for a in arts if a.get("title_tr")), "")
            tr_bullets = []
            seen_tr_fam: set[str] = set()
            tr_idx = 0
            for a in arts:
                if a["family"] in seen_tr_fam:
                    continue
                seen_tr_fam.add(a["family"])
                tr_idx += 1
                snip_tr_v = str(a.get("snippet_tr") or a.get("title_tr") or "").strip()
                if snip_tr_v:
                    if not snip_tr_v.endswith((".", "!", "?")):
                        snip_tr_v += "."
                    tr_bullets.append(f"- {snip_tr_v} [{tr_idx}]")
                if tr_idx >= 3:
                    break
            translated_summary_md = "\n".join(tr_bullets) if tr_bullets else ""
            tr_src_lang = next((a["translation_source_lang"] or a["language"] for a in arts if a.get("title_tr") or a.get("snippet_tr")), "")

            if topic_l:
                hay = f"{cr['headline']} {lead_tr_title} {' '.join(tags)} {cr['summary_md']} {translated_summary_md}".lower()
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
                "translated_headline": lead_tr_title,
                "summary_md": cr["summary_md"],
                "translated_summary_md": translated_summary_md,
                "translation_source_lang": tr_src_lang,
                "translation_target_lang": t_target if (lead_tr_title or translated_summary_md) else "",
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

    def search_stories(
        self,
        query: str = "",
        lane: str = "top",
        limit: int = 10,
    ) -> dict[str, Any]:
        """Searches synced news clusters & articles by keyword/topic and lane."""
        lane_raw = (lane or "top").strip().lower()
        eff_lane = "top" if lane_raw in ("", "stories", "all") else lane_raw
        lim = max(1, min(30, int(limit or 10)))
        q = (query or "").strip()
        base = self.get_stories(lane=eff_lane, limit=60)
        all_stories = list(base.get("stories") or [])

        if not q:
            return {
                "ok": True,
                "query": "",
                "lane": eff_lane,
                "total": len(all_stories[:lim]),
                "stories": all_stories[:lim],
            }

        q_low = q.lower()
        q_tokens = [
            t
            for t in re.findall(r"[a-z0-9äöüß]{2,}", q_low)
            if t not in {"the", "and", "for", "with", "about", "news", "latest", "recent", "today", "stories"}
        ]
        scored: list[tuple[float, dict[str, Any]]] = []
        for card in all_stories:
            art_hay = " ".join(
                f"{a.get('title') or ''} {a.get('snippet') or ''} {a.get('domain') or ''}"
                for a in (card.get("articles") or [])[:6]
            )
            hay = f"{card.get('headline') or ''} {card.get('summary_md') or ''} {' '.join(card.get('topic_tags') or [])} {art_hay}".lower()
            sc = 0.0
            if q_low in hay:
                sc += 5.0
            for tok in q_tokens:
                if tok in hay:
                    sc += 2.0
            if sc > 0.0:
                sc += min(1.5, float(card.get("story_rank") or 0.0) * 0.1)
                scored.append((sc, card))

        scored.sort(key=lambda pair: (-pair[0], -float(pair[1].get("updated_at") or 0.0)))
        matched = [c for _, c in scored[:lim]]
        return {
            "ok": True,
            "query": q,
            "lane": eff_lane,
            "total": len(matched),
            "stories": matched,
        }

    # ── M28 + Content Translation: Non-Allowed Article Translation ────────────
    def translate_article(self, article_id: str, target_lang: str = "") -> dict[str, Any]:
        from satz_translate import detect_language, normalize_language_code

        translator = getattr(self.runtime, "translator", None)
        eff_target = normalize_language_code(target_lang) or self._primary_translation_target()

        with self.runtime.store_lock:
            row = self.runtime.store.db.execute(
                "SELECT * FROM satz_news_articles WHERE article_id = ?",
                (article_id,),
            ).fetchone()
            if not row:
                raise ValueError("Article not found")
            tr_row = self.runtime.store.db.execute(
                "SELECT * FROM satz_news_translations WHERE article_id = ? AND target_lang = ?",
                (article_id, eff_target),
            ).fetchone()

        raw_src = (row["body_text"] or row["snippet"] or "").strip()[:3500]
        src_lang = detect_language(f"{row['title']}\n{raw_src[:1200]}", hint_lang=str(row["language"] or "en"))

        if tr_row and tr_row["body_tr"]:
            return {
                "ok": True,
                "article_id": article_id,
                "language": src_lang,
                "target_lang": eff_target,
                "title_tr": str(tr_row["title_tr"] or row["title"]),
                "snippet_tr": str(tr_row["snippet_tr"] or ""),
                "translated_text": str(tr_row["body_tr"]),
                "original_text": raw_src,
                "model": str(tr_row["model_id"] or ""),
                "cached": True,
            }
        if not raw_src:
            return {"ok": False, "error": "Article text is empty"}

        safe_src = neutralize_brain_directives_in_source(raw_src)
        safe_title = neutralize_brain_directives_in_source(str(row["title"] or ""))
        if translator is not None:
            seg_map: dict[str, str] = {"body": safe_src}
            if safe_title:
                seg_map["title"] = safe_title[:400]
            if row["snippet"]:
                seg_map["snippet"] = neutralize_brain_directives_in_source(str(row["snippet"] or ""))[:800]
            tr_res = translator.translate_segments(
                seg_map,
                target_lang=eff_target,
                source_lang=src_lang,
                context_hint=f"news article from {row['domain']}",
            )
            tr_dict = tr_res.get("translations") or {}
            translated = str(tr_dict.get("body") or "").strip()
            title_tr = str(tr_dict.get("title") or (tr_row["title_tr"] if tr_row else "") or safe_title).strip()
            snippet_tr = str(tr_dict.get("snippet") or (tr_row["snippet_tr"] if tr_row else "") or "").strip()
            model_used = str(tr_res.get("model") or "")
        else:
            model_used = "gemma-4-e4b"
            sys_p = (
                f"You translate news reporting accurately into {eff_target}. "
                "Preserve all numbers, dates, quotes, and proper nouns faithfully. Do not summarize or invent facts."
            )
            usr_p = f"HEADLINE: {safe_title}\nDOMAIN: {row['domain']}\nTEXT:\n{safe_src}"
            translated = self.runtime._complete_role_prompt(
                model_used,
                sys_p,
                usr_p,
                temperature=0.1,
                max_tokens=1400,
            )
            title_tr = safe_title
            snippet_tr = ""

        now_ts = time.time()
        with self.runtime.store_lock:
            self.runtime.store.db.execute(
                "UPDATE satz_news_articles SET translated_text = ?, language = ? WHERE article_id = ?",
                (translated, src_lang, article_id),
            )
            self.runtime.store.db.execute(
                """
                INSERT INTO satz_news_translations
                  (article_id, target_lang, source_lang, title_tr, snippet_tr, body_tr, model_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(article_id, target_lang) DO UPDATE SET
                  source_lang = excluded.source_lang,
                  title_tr = CASE WHEN LENGTH(excluded.title_tr) > 0 THEN excluded.title_tr ELSE satz_news_translations.title_tr END,
                  snippet_tr = CASE WHEN LENGTH(excluded.snippet_tr) > 0 THEN excluded.snippet_tr ELSE satz_news_translations.snippet_tr END,
                  body_tr = excluded.body_tr,
                  model_id = excluded.model_id,
                  updated_at = excluded.updated_at
                """,
                (article_id, eff_target, src_lang, title_tr, snippet_tr, translated, model_used, now_ts),
            )
            self.runtime.store.db.commit()
        return {
            "ok": True,
            "article_id": article_id,
            "language": src_lang,
            "target_lang": eff_target,
            "title_tr": title_tr,
            "snippet_tr": snippet_tr,
            "translated_text": translated,
            "original_text": raw_src,
            "model": model_used,
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

    def _collect_topic_perspective_articles(
        self,
        topic: str,
        cluster_id: str = "",
        followed_story_id: str = "",
        limit_families: int = 8,
    ) -> dict[str, Any]:
        """Finds matching articles across independent news source families for a topic, cluster, or followed story."""
        from src.planck3.web import domain_of

        clean_topic = (topic or "").strip()
        cid = (cluster_id or "").strip()
        fsid = (followed_story_id or "").strip()
        t_target = self._primary_translation_target()
        topic_keywords: list[str] = []
        cluster_headline = ""
        seed_rows: list[dict[str, Any]] = []

        with self.runtime.store_lock:
            if fsid:
                fsr = self.runtime.store.db.execute(
                    "SELECT * FROM satz_news_followed_stories WHERE story_id = ?",
                    (fsid,),
                ).fetchone()
                if fsr:
                    cluster_headline = str(fsr["title"] or "").strip()
                    if not cid and fsr["seed_cluster_id"]:
                        cid = str(fsr["seed_cluster_id"])
                    try:
                        topic_keywords.extend(str(k).lower() for k in json.loads(fsr["keywords_json"] or "[]"))
                    except Exception:
                        pass
                    urows = self.runtime.store.db.execute(
                        """
                        SELECT u.article_id, u.url, u.domain, u.family, u.title, u.snippet, u.language,
                               u.image_url, u.published_at,
                               COALESCE(a.body_text, u.snippet) AS body_text,
                               COALESCE(nt.title_tr, '') AS title_tr,
                               COALESCE(nt.snippet_tr, '') AS snippet_tr,
                               COALESCE(nt.body_tr, '') AS body_tr
                        FROM satz_news_followed_story_updates u
                        LEFT JOIN satz_news_articles a ON a.article_id = u.article_id
                        LEFT JOIN satz_news_translations nt ON nt.article_id = u.article_id AND nt.target_lang = ?
                        WHERE u.story_id = ?
                        ORDER BY u.trust_effective DESC, u.published_at DESC
                        """,
                        (t_target, fsid),
                    ).fetchall()
                    for ur in urows:
                        seed_rows.append(dict(ur))
            if cid:
                cr = self.runtime.store.db.execute(
                    "SELECT * FROM satz_news_clusters WHERE cluster_id = ?",
                    (cid,),
                ).fetchone()
                if cr:
                    if not cluster_headline:
                        cluster_headline = str(cr["headline"] or "").strip()
                    arows = self.runtime.store.db.execute(
                        """
                        SELECT a.*,
                               COALESCE(nt.title_tr, '') AS title_tr,
                               COALESCE(nt.snippet_tr, '') AS snippet_tr,
                               COALESCE(nt.body_tr, '') AS body_tr
                        FROM satz_news_articles a
                        LEFT JOIN satz_news_translations nt ON nt.article_id = a.article_id AND nt.target_lang = ?
                        WHERE a.cluster_id = ?
                        ORDER BY a.trust_effective DESC, a.published_at DESC
                        """,
                        (t_target, cid),
                    ).fetchall()
                    seen_seed_urls = {str(r.get("url") or "") for r in seed_rows}
                    for ar in arows:
                        d_ar = dict(ar)
                        if str(d_ar.get("url") or "") not in seen_seed_urls:
                            seed_rows.append(d_ar)

            # Expand keywords from matching tracked topic if any
            top_rows = self.runtime.store.db.execute(
                "SELECT name, keywords_json FROM satz_news_topics WHERE suppressed = 0"
            ).fetchall()
            eff_q_low = (clean_topic or cluster_headline).lower()
            for tr in top_rows:
                tname = str(tr["name"] or "").strip().lower()
                if tname and (tname == eff_q_low or tname in eff_q_low or eff_q_low in tname):
                    try:
                        topic_keywords.extend(str(k).lower() for k in json.loads(tr["keywords_json"] or "[]"))
                    except Exception:
                        pass

            eff_query = clean_topic or cluster_headline
            q_terms = list(dict.fromkeys([*_tokenize_title(eff_query), *_tokenize_title(" ".join(topic_keywords))]))
            all_rows = self.runtime.store.db.execute(
                """
                SELECT a.*,
                       COALESCE(nt.title_tr, '') AS title_tr,
                       COALESCE(nt.snippet_tr, '') AS snippet_tr,
                       COALESCE(nt.body_tr, '') AS body_tr
                FROM satz_news_articles a
                LEFT JOIN satz_news_translations nt ON nt.article_id = a.article_id AND nt.target_lang = ?
                ORDER BY a.published_at DESC
                LIMIT 260
                """,
                (t_target,),
            ).fetchall()

        scored_local: list[tuple[float, dict[str, Any]]] = []
        seen_urls = {str(r.get("url") or "") for r in seed_rows}
        for sr in seed_rows:
            scored_local.append((100.0 + float(sr.get("trust_effective") or 5.0), sr))
        for ar in all_rows:
            d = dict(ar)
            u = str(d.get("url") or "")
            if not u or u in seen_urls:
                continue
            title_hay = f"{d.get('title_tr') or ''} {d.get('title') or ''}".lower()
            body_hay = f"{d.get('snippet_tr') or ''} {d.get('snippet') or ''} {d.get('body_tr') or ''} {d.get('body_text') or ''}".lower()
            t_hits = sum(1 for tok in q_terms if tok in title_hay)
            b_hits = sum(1 for tok in q_terms if tok in body_hay)
            if q_terms and (t_hits == 0 and b_hits == 0):
                continue
            score = t_hits * 8.0 + b_hits * 2.5 + float(d.get("trust_effective") or 5.0) * 0.4
            scored_local.append((score, d))

        # Translate top local candidates if non-allowed language lacks translation yet
        scored_local.sort(key=lambda x: -x[0])
        web_cand_dicts: list[dict[str, Any]] = []
        distinct_local_fams = {str(x[1].get("family") or x[1].get("domain") or "") for x in scored_local[:12]}
        web_obj = getattr(self.runtime, "web", None)
        can_web = bool(web_obj is not None and (getattr(getattr(web_obj, "cache", None), "online", False) or "search" in getattr(web_obj, "__dict__", {})))
        if len(distinct_local_fams) < 2 and clean_topic and can_web:
            try:
                search_hits = web_obj.search(f"{clean_topic} news") or []
                for h in search_hits[:6]:
                    hu = str(h.get("url") or "").strip()
                    if not hu or hu in seen_urls or _is_landing_url(hu):
                        continue
                    seen_urls.add(hu)
                    hdom = str(h.get("domain") or domain_of(hu) or "").lower().removeprefix("www.")
                    fam, wire_org = self.resolve_article_family(hdom, str(h.get("snippet") or ""))
                    web_cand_dicts.append(
                        {
                            "article_id": f"web-{hashlib.sha1(hu.encode('utf-8')).hexdigest()[:12]}",
                            "url": hu,
                            "domain": hdom,
                            "family": fam,
                            "wire_origin": wire_org,
                            "title": str(h.get("title") or hdom),
                            "snippet": str(h.get("snippet") or ""),
                            "body_text": str(h.get("snippet") or ""),
                            "image_url": "",
                            "published_at": time.time(),
                        }
                    )
            except Exception:
                pass

        combined_rows = [x[1] for x in scored_local[:24]] + web_cand_dicts
        seen_fam: set[str] = set()
        fam_articles: list[dict[str, Any]] = []
        collapsed_wire = 0
        for ar in combined_rows:
            dom = str(ar.get("domain") or "").lower().removeprefix("www.")
            fam = str(ar.get("family") or dom)
            if fam in seen_fam:
                collapsed_wire += 1
                continue
            seen_fam.add(fam)
            t_rec = self._trust_for_domain(dom, use_personal=True)
            t_sys = self._trust_for_domain(dom, use_personal=False)
            eff_title = str(ar.get("title_tr") or ar.get("title") or dom)
            eff_snip = str(ar.get("snippet_tr") or ar.get("snippet") or ar.get("body_tr") or ar.get("body_text") or "")[:500]
            eff_body = str(ar.get("body_tr") or ar.get("translated_text") or ar.get("body_text") or eff_snip)[:2000]
            fam_articles.append(
                {
                    "idx": len(fam_articles) + 1,
                    "role": "news",
                    "article_id": str(ar.get("article_id") or ""),
                    "url": str(ar.get("url") or ""),
                    "domain": dom,
                    "family": fam,
                    "title": eff_title,
                    "snippet": eff_snip,
                    "body_text": eff_body,
                    "image_url": str(ar.get("image_url") or ""),
                    "published_at": float(ar.get("published_at") or time.time()),
                    "category": str(t_rec["category"] or ""),
                    "why": str(t_rec["why"] or ""),
                    "trust": {
                        "system": round(float(t_sys["system"]), 2),
                        "personal": round(float(t_rec["personal"]), 2) if t_rec["personal"] is not None else None,
                        "effective": round(float(t_rec["effective"]), 2),
                        "category": str(t_rec["category"] or ""),
                        "family": str(t_rec["family"] or fam),
                        "why": str(t_rec["why"] or ""),
                        "conflict": bool(t_rec["conflict"]),
                    },
                    "trust_system": round(float(t_sys["system"]), 2),
                    "trust_effective": round(float(t_rec["effective"]), 2),
                    "conflict": bool(t_rec["conflict"]),
                }
            )
            if len(fam_articles) >= limit_families:
                break

        cats_present = {a["category"] for a in fam_articles}
        blind_spots: list[str] = []
        if fam_articles and "primary_official" not in cats_present and "eu_gov" not in cats_present and "us_agency" not in cats_present:
            blind_spots.append("missing: no primary official government or agency filing (trust 9.0) retrieved")
        if collapsed_wire > 0:
            blind_spots.append(f"deduped: {collapsed_wire} syndicated/wire duplicate article(s) collapsed into origin family")
        sys_top = sorted(fam_articles, key=lambda a: -a["trust_system"])[0]["domain"] if fam_articles else ""
        eff_top = fam_articles[0]["domain"] if fam_articles else ""
        counterfactual = (
            f"Personal trust overrides elevated {eff_top} over system top choice {sys_top}."
            if sys_top and eff_top and sys_top != eff_top
            else "System-only trust weights preserve the same primary source ordering."
        )
        return {
            "topic_label": clean_topic or cluster_headline,
            "cluster_id": cid,
            "fam_articles": fam_articles,
            "blind_spots": blind_spots,
            "collapsed_wire": collapsed_wire,
            "counterfactual": counterfactual,
            "sys_top_domain": sys_top,
        }

    def stream_topic_perspectives(
        self,
        topic: str = "",
        cluster_id: str = "",
        followed_story_id: str = "",
        roles_override: dict[str, str] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
    ):
        """SSE generator finding relevant articles across sources for a user topic or followed story and streaming a comparison."""
        from src.planck3.qtype import PENALTY
        from src.planck3.registry import BAND_LABEL, band

        t0 = time.perf_counter()
        topic_label_in = (topic or "").strip() or "current top news"
        yield {"status": f"searching articles on '{topic_label_in[:48]}' across sources...", "phase": "searching"}

        data = self._collect_topic_perspective_articles(
            topic_label_in,
            cluster_id=cluster_id,
            followed_story_id=followed_story_id,
            limit_families=8,
        )
        topic_label = data["topic_label"] or topic_label_in
        fam_articles = data["fam_articles"]
        blind_spots = data["blind_spots"]
        counterfactual = data["counterfactual"]

        roles = dict(self.runtime.get_model_management_config()["roles"])
        if roles_override:
            roles.update({k: v for k, v in roles_override.items() if v})
        analyzer_m = roles.get("news_analyzer") or roles.get("chat") or "gemma-4-e4b"

        findings_out: list[dict[str, Any]] = []
        seen_imgs: set[str] = set()
        if fam_articles and hasattr(self.runtime, "merge_previews_into_sources"):
            try:
                self.runtime.merge_previews_into_sources(
                    fam_articles,
                    findings_out,
                    seen_imgs,
                    max_items=8,
                    max_findings=6,
                )
            except Exception:
                pass

        source_stats_out = [
            {
                "id": a["url"],
                "chars_captured": len(a["body_text"] or a["snippet"]),
                "chars_sent": len(a["body_text"] or a["snippet"]),
                "was_cut": False,
                "capture_mode": "rss",
                "context_tier": "full",
            }
            for a in fam_articles
        ]
        early_sources = [
            {
                "url": a["url"],
                "title": a["title"],
                "domain": a["domain"],
                "snippet": str(a.get("snippet") or "")[:240],
                "image_url": str(a.get("image_url") or ""),
                **({"favicon_url": a["favicon_url"]} if a.get("favicon_url") else {}),
            }
            for a in fam_articles
        ]

        yield {
            "source_stats": source_stats_out,
            "sources": early_sources,
            "status": f"comparing reporting across {len(fam_articles)} independent source(s) via {analyzer_m}...",
            "phase": "comparing",
        }

        if not fam_articles:
            empty_msg = (
                f"No articles matching **{topic_label}** were found across your current news sources. "
                "Try broadening the topic, adding relevant feeds in **News Settings**, or syncing your feeds."
            )
            yield {"delta": empty_msg}
            yield {
                "done": True,
                "ok": True,
                "topic": topic_label,
                "cluster_id": data["cluster_id"],
                "answer": empty_msg,
                "model": "none",
                "sources": [],
                "source_stats": [],
                "findings": [],
            }
            return

        # Compute trust audit card (30% personal cap + counterfactual)
        pen = PENALTY.get("news", 2.0)
        top = fam_articles[0]
        agree = [a for a in fam_articles[1:] if a["trust_effective"] >= 7.0]
        items = [[f"most trusted source covering topic: {top['domain']} ({top['category']})", round(top["trust_effective"], 2)]]
        if agree:
            items.append([f"{len(agree)} more independent source(s) at 7+: " + ", ".join(x["domain"] for x in agree[:3]), min(2.0, float(len(agree)))])
        if pen:
            items.append(["news question type", -pen])
        conf10 = round(max(0.0, min(10.0, sum(v for _, v in items))), 1)
        b_code = band(conf10)
        sys_top_domain = str(data.get("sys_top_domain") or top["domain"])
        sys_top_score = max(a["trust_system"] for a in fam_articles)
        sys_agree = min(2.0, sum(1.0 for a in fam_articles[1:] if a["trust_system"] >= 7.0))
        sys_conf = round(max(0.0, min(10.0, sys_top_score + sys_agree - pen)), 1)
        sys_band = band(sys_conf)

        # Deterministic extractive comparison fallback
        fb_lines = [
            f"### Perspectives on: {topic_label}",
            "",
            "**Sources compared:**",
            *[
                f"- **[{a['title']}]({a['url']})** ({a['domain']} · {a['category']} · {a['trust_effective']:.1f}/10) — {a['snippet'][:200]} [{a['idx']}]"
                for a in fam_articles[:6]
            ],
            "",
            "**Blind spots & trust check:**",
            *[f"- {bs}" for bs in blind_spots],
            f"- {counterfactual}",
        ]
        fb_answer = "\n".join(fb_lines)
        answer_text = fb_answer
        used_writer = "template"

        if analyzer_m != "template":
            src_ctx = "\n\n".join(
                f"[{a['idx']}] {a['domain']} (cat={a['category']}, eff={a['trust_effective']:.1f}/10, sys={a['trust_system']:.1f}/10, fam={a['family']}): "
                f"{a['title']} ({a['url']})\n{neutralize_brain_directives_in_source((a['body_text'] or a['snippet'])[:900])}"
                for a in fam_articles
            )
            hist_lines = []
            for pm in (prior_messages or [])[-4:]:
                r = str(pm.get("role") or "")
                c = str(pm.get("content") or "")[:300]
                if r in ("user", "assistant") and c:
                    hist_lines.append(f"{r.upper()}: {c}")
            hist_blk = ("PRIOR DISCUSSION:\n" + "\n".join(hist_lines) + "\n\n") if hist_lines else ""
            t_target = self._primary_translation_target()
            sys_p = (
                "Compare reporting on the selected news topic objectively across the provided independent sources. "
                "Structure clearly in markdown with:\n"
                "1. **Shared facts & consensus**\n"
                "2. **Outlet angles & framing differences** (contrast how different outlets/regions frame claims)\n"
                "3. **Gaps & blind spots**\n"
                "Cite every claim inline as [1], [2], etc. Never invent sources, facts, quotes, or numbers outside SOURCES. "
                f"Respond in the user's preferred language ({t_target}), translating foreign excerpts cleanly."
            )
            usr_p = (
                f"TOPIC: {topic_label}\n"
                f"BLIND SPOTS DETECTED: {'; '.join(blind_spots) or 'none'}\n"
                f"TRUST CHECK: {counterfactual}\n\n"
                f"{hist_blk}SOURCES:\n{src_ctx}"
            )
            cand_txt = ""
            try:
                is_mocked_complete = "_complete_role_prompt" in getattr(self.runtime, "__dict__", {})
                stream_fn = getattr(self.runtime, "_stream_role_prompt", None)
                if callable(stream_fn) and not is_mocked_complete:
                    started = False
                    for sev in stream_fn(
                        analyzer_m,
                        sys_p,
                        usr_p,
                        temperature=0.15,
                        max_tokens=720,
                        thinking_budget=0,
                    ):
                        if "__full_raw" in sev:
                            cand_txt = str(sev.get("__full_raw") or "")
                        elif sev.get("delta"):
                            if not started:
                                yield {"status": "streaming perspectives comparison...", "phase": "streaming"}
                                started = True
                            yield {"delta": sev["delta"]}
                        elif sev.get("phase") == "heartbeat":
                            yield sev
                else:
                    cand_txt = _complete_role_fast(
                        self.runtime,
                        analyzer_m,
                        sys_p,
                        usr_p,
                        temperature=0.15,
                        max_tokens=720,
                        thinking_budget=0,
                    )
                    if cand_txt:
                        yield {"delta": cand_txt}

                max_idx = len(fam_articles)
                if cand_txt.strip():
                    # Guard against out-of-range numeric citation tags
                    cleaned_c = re.sub(
                        r"\[(\d+)\]",
                        lambda m: m.group(0) if 1 <= int(m.group(1)) <= max_idx else "",
                        cand_txt,
                    ).strip()
                    if cleaned_c != cand_txt.strip():
                        yield {"replace_text": cleaned_c, "fallback": False}
                    answer_text = cleaned_c
                    used_writer = analyzer_m
                else:
                    yield {"replace_text": fb_answer, "fallback": True}
            except Exception as exc:
                ctx_err = str(exc)
                yield {"status": f"using structured fallback comparison ({ctx_err[:40]})", "phase": "fallback"}
                if cand_txt:
                    yield {"replace_text": fb_answer, "fallback": True}
                else:
                    yield {"delta": fb_answer}
        else:
            yield {"delta": fb_answer}

        is_cloud_m = self.runtime._parse_cloud_model_id(used_writer) is not None
        answer_meta = {
            "pipeline": "perspectives_stream",
            "question": topic_label,
            "confidence10": conf10,
            "band": b_code,
            "band_label": BAND_LABEL[b_code],
            "qtype": "news",
            "items": items,
            "divergence": (
                {"system_value": sys_top_domain, "system_confidence": sys_conf, "system_band": sys_band}
                if (sys_band != b_code or abs(sys_conf - conf10) >= 0.5)
                else None
            ),
            "steps": [
                f"1. Searched sources for topic '{topic_label}'",
                f"2. Collapsed syndicated wires ({data['collapsed_wire']} deduped) -> {len(fam_articles)} independent families",
                f"3. Weighed personal overrides (30% cap) · {conf10:.1f}/10 {b_code}",
                f"4. Streamed comparison via {used_writer}",
            ],
            "sources": fam_articles,
            "models_used": {
                "planner": roles.get("news_planner") or "local",
                "reader": roles.get("news_reader") or "heuristic",
                "analyzer": used_writer,
            },
            "privacy_disclosure": (
                f"Sent {len(fam_articles)} public article excerpts to {used_writer}; Brain & Mail omitted."
                if is_cloud_m
                else "100% local execution (0 cloud calls)."
            ),
            "ms": int((time.perf_counter() - t0) * 1000),
        }

        yield {
            "done": True,
            "ok": True,
            "topic": topic_label,
            "cluster_id": data["cluster_id"],
            "answer": answer_text,
            "model": used_writer,
            "sources": early_sources,
            "source_stats": source_stats_out,
            "findings": findings_out[:6],
            "answer_meta": answer_meta,
            "blind_spots": blind_spots,
            "system_counterfactual": counterfactual,
        }

    # ── M25: Audited read -> weigh -> write News Chat Pipeline ──────────────
    def _build_reader(self, model_id: str):
        if model_id in ("hertz (reader)", "planck (reader)"):
            candidates = (model_id, "planck (reader)") if model_id == "hertz (reader)" else (model_id,)
            for cand in candidates:
                try:
                    return self.runtime.ensure_reader(cand)
                except Exception:
                    continue
            from src.planck3.readers import HeuristicReader

            return HeuristicReader()
        if model_id == "heuristic":
            from src.planck3.readers import HeuristicReader

            return HeuristicReader()
        return SatzLLMReader(self.runtime, model_id, role_key="news_reader", max_cands=20)

    def _iter_news_evidence(
        self,
        question: str,
        open_sources: list[dict[str, Any]] | None = None,
        roles_override: dict[str, str] | None = None,
    ):
        """
        Shared Stages 1-4 builder for both `answer_news_question` and `stream_news_question`:
        yields `{'status': ..., 'phase': ...}` updates and concludes with `{'__ctx': ctx}`.
        """
        from src.planck3.candidates import snippet_candidates, span_candidates, title_aboutness
        from src.planck3.chat import infer_answer_type
        from src.planck3.consolidate import consolidate, divergence
        from src.planck3.qtype import classify
        from src.planck3.web import domain_of, extract_jsonld, extract_main_text

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
        yield {"status": f"planning news query ({planned_q[:42]})...", "phase": "news_weigh"}

        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        docs: list[dict[str, Any]] = []

        if open_sources:
            cached_src_texts: dict[str, str] = {}
            open_urls = [str(src.get("url") or "").strip() for src in open_sources if str(src.get("url") or "").strip()]
            open_sids = [str(src.get("id") or "").strip() for src in open_sources if str(src.get("id") or "").strip()]
            if open_urls or open_sids:
                with self.runtime.store_lock:
                    if open_sids:
                        ph_s = ",".join("?" for _ in open_sids)
                        for r in self.runtime.store.db.execute(
                            f"SELECT source_id, url, text FROM satz_sources WHERE source_id IN ({ph_s}) AND LENGTH(TRIM(COALESCE(text, ''))) > 0",
                            open_sids,
                        ).fetchall():
                            cached_src_texts[str(r["source_id"])] = str(r["text"])
                            if r["url"]:
                                cached_src_texts.setdefault(str(r["url"]), str(r["text"]))
                    if open_urls:
                        ph_u = ",".join("?" for _ in open_urls)
                        for r in self.runtime.store.db.execute(
                            f"SELECT url, text FROM satz_sources WHERE url IN ({ph_u}) AND LENGTH(TRIM(COALESCE(text, ''))) > 0 ORDER BY updated_at DESC",
                            open_urls,
                        ).fetchall():
                            cached_src_texts.setdefault(str(r["url"]), str(r["text"]))
            for src in open_sources:
                u = str(src.get("url") or "").strip()
                if not u or u in seen_urls:
                    continue
                sid_s = str(src.get("id") or u)
                txt = str(src.get("text") or cached_src_texts.get(sid_s) or cached_src_texts.get(u) or "").strip()
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

        yield {"status": "checking synced local news index...", "phase": "news_weigh"}
        with self.runtime.store_lock:
            art_cnt = self.runtime.store.db.execute("SELECT COUNT(*) FROM satz_news_articles").fetchone()[0]
        if art_cnt == 0 and getattr(self.runtime.web.cache, "online", True):
            try:
                yield {"status": "warming starter RSS news feeds...", "phase": "news_weigh"}
                try:
                    rf = self.refresh_news_feeds(force=False, process_to_brain=False, translate_recent=False)
                except TypeError:
                    rf = self.refresh_news_feeds(force=False)
                if rf.get("articles_ingested"):
                    steps.append(f"1b. Auto-warmed synced RSS feeds ({rf['fetched_feeds']} feed(s), {rf['articles_ingested']} article(s), bg Brain/translation queued)")
                    def _bg_warm_news():
                        try:
                            self.translate_recent_untranslated(limit=35, recluster=True, background_indexation=True)
                        except Exception:
                            pass
                        try:
                            self.process_top_stories_to_brain(limit=12, force=False)
                        except Exception:
                            pass
                    threading.Thread(target=_bg_warm_news, daemon=True, name="satz-news-warm").start()
            except Exception:
                pass

        temporal = _parse_temporal_query(scrubbed_q)
        interval_secs = float(getattr(self.runtime, "news_refresh_interval_secs", 3600.0))
        last_sync_at = self._get_meta_float("news_last_sync_at")
        has_fresh_sync = bool(last_sync_at > 0 and (time.time() - last_sync_at) <= max(interval_secs, 3600.0))

        q_toks = _expand_news_topic_tokens(_tokenize_title(scrubbed_q))
        t_target = self._primary_translation_target()
        with self.runtime.store_lock:
            local_arts = self.runtime.store.db.execute(
                """
                SELECT ar.article_id, ar.url, ar.domain, ar.title, ar.snippet, ar.body_text,
                       ar.image_url, ar.published_at, ar.trust_effective, ar.language,
                       COALESCE(nt.title_tr, '') AS title_tr,
                       COALESCE(nt.snippet_tr, '') AS snippet_tr,
                       COALESCE(nt.body_tr, '') AS body_tr
                FROM satz_news_articles ar
                LEFT JOIN satz_news_translations nt
                  ON nt.article_id = ar.article_id AND nt.target_lang = ?
                ORDER BY ar.published_at DESC, ar.trust_effective DESC
                LIMIT 200
                """,
                (t_target,),
            ).fetchall()

        scored_local: list[tuple[int, float, float, sqlite3.Row]] = []
        now_news = time.time()
        for ar in local_arts:
            a_toks = _tokenize_title(f"{ar['title']} {ar['title_tr']} {ar['snippet']} {ar['snippet_tr']}")
            pub_ts = float(ar["published_at"] or 0.0)
            if temporal["start_ts"] is not None and pub_ts > 0:
                end_b = temporal["end_ts"] if temporal["end_ts"] is not None else (now_news + 600.0)
                if not (temporal["start_ts"] <= pub_ts <= end_b) and not is_briefing:
                    continue
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
                age_h = max(0.0, (now_news - pub_ts) / 3600.0) if pub_ts > 0 else 48.0
                rec_bonus = math.exp(-age_h / 24.0) * 2.0 + float(ar["trust_effective"] or 5.0) * 0.25
                scored_local.append((overlap, rec_bonus, pub_ts, ar))

        scored_local.sort(key=lambda item: (-item[0], -item[1], -item[2]))
        high_overlap_rss = 0
        for ov, _rec, pub_ts, ar in scored_local:
            if not is_briefing and ov == 0:
                continue
            if len(results) >= (8 if is_briefing else 6):
                break
            u = ar["url"]
            if u in seen_urls:
                continue
            seen_urls.add(u)
            eff_title = str(ar["title_tr"] or "").strip() or str(ar["title"] or "")
            eff_snip_raw = str(ar["snippet_tr"] or "").strip() or str(ar["snippet"] or "")
            eff_body_raw = str(ar["body_tr"] or "").strip() or str(ar["body_text"] or "")
            body_or_snip = eff_body_raw or eff_snip_raw or ""
            pub_lbl = _utc_iso_from_ts(pub_ts)[:16].replace("T", " ") + "Z" if pub_ts > 0 else ""
            raw_snip = eff_snip_raw or body_or_snip[:400]
            dated_snip = f"[{pub_lbl}] {raw_snip}" if (pub_lbl and raw_snip) else raw_snip
            results.append(
                {
                    "article_id": str(ar["article_id"] or ""),
                    "url": u,
                    "domain": ar["domain"],
                    "title": eff_title,
                    "snippet": dated_snip,
                    "image_url": ar["image_url"] or "",
                    "published_at": pub_ts,
                    "language": str(ar["language"] or "en"),
                    "already_translated": bool(str(ar["title_tr"] or "").strip() or str(ar["snippet_tr"] or "").strip()),
                    "capture_mode": "rss",
                }
            )
            if body_or_snip:
                docs.append(
                    {
                        "url": u,
                        "domain": ar["domain"],
                        "title": eff_title,
                        "text": f"[{pub_lbl}] {body_or_snip}" if pub_lbl else body_or_snip,
                        "capture_mode": "rss",
                    }
                )
                if ov >= 2:
                    high_overlap_rss += 1

        need_live_web = not (
            (is_briefing and len(docs) >= 4 and (has_fresh_sync or not getattr(self.runtime.web.cache, "online", True)))
            or (not is_briefing and high_overlap_rss >= 2 and len(docs) >= 2)
        )
        if need_live_web:
            yield {"status": f"searching web for '{search_queries[0][:40]}'...", "phase": "web_search"}
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
        else:
            steps.append(f"2. Fast synced news cache hit ({len(docs)} pre-indexed local article(s), last sync active)")

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

        reader = self._build_reader(reader_m)
        pools: list[dict[str, Any]] = []
        if results and not is_briefing:
            scands = snippet_candidates(scrubbed_q, results, at)
            if scands:
                yield {"status": f"scoring {len(scands)} news snippet candidate(s)...", "phase": "reading"}
                pools.append({"name": "snippets", "cands": scands, "snippet": True, "r": []})
                pools[-1]["r"] = reader.read(scrubbed_q, at, pools[-1])
                steps.append(f"3. Extracted & scored {len(scands)} snippet candidate(s) with {reader_m} (trust-blind)")

        cons = consolidate(pools, at, qt, _tp)
        if results and (not (is_briefing and len(docs) >= 3)) and (is_briefing or cons["value"] is None or cons["confidence"] < 7.0):
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
            fetch_cap = 3 if is_briefing else 2
            to_fetch: list[dict[str, Any]] = []
            already_eval: list[dict[str, Any]] = []
            for r in order:
                if r["url"] in already_docs:
                    already_eval.append(r)
                elif len(to_fetch) < fetch_cap:
                    to_fetch.append(r)

            fetched_pages: dict[str, dict[str, Any]] = {}
            if to_fetch:
                yield {"status": f"fetching {len(to_fetch)} full article(s) in parallel...", "phase": "reading"}
            if len(to_fetch) == 1:
                r0 = to_fetch[0]
                try:
                    fetched_pages[r0["url"]] = self.runtime.web.fetch(r0["url"])
                except Exception:
                    fetched_pages[r0["url"]] = {}
            elif len(to_fetch) > 1:
                def _fetch_article(art_row: dict[str, Any]) -> dict[str, Any]:
                    try:
                        return self.runtime.web.fetch(art_row["url"])
                    except Exception:
                        return {}

                with ThreadPoolExecutor(max_workers=min(3, len(to_fetch))) as pool:
                    fut_map = {pool.submit(_fetch_article, ar): ar["url"] for ar in to_fetch}
                    for fut in as_completed(fut_map):
                        u_key = fut_map[fut]
                        try:
                            fetched_pages[u_key] = fut.result() or {}
                        except Exception:
                            fetched_pages[u_key] = {}

            batched_page_cands: list[dict[str, Any]] = []
            opened_domains: list[str] = []
            for r in already_eval:
                doc_obj = next((d for d in docs if d["url"] == r["url"]), None)
                text = doc_obj["text"] if doc_obj else ""
                if text and not is_briefing:
                    pc = span_candidates(scrubbed_q, text, at, url=r["url"], extra_lines=[])
                    if pc:
                        batched_page_cands.extend(pc[:12])
                        opened_domains.append(f"{r['domain']} ({r['trust_record']['effective']:.1f}/10)")

            for r in to_fetch:
                page = fetched_pages.get(r["url"]) or {}
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
                        batched_page_cands.extend(pc[:12])
                        opened_domains.append(f"{r['domain']} ({r['trust_record']['effective']:.1f}/10)")

            if batched_page_cands and not is_briefing:
                p_obj = {"name": "pages:batch", "cands": batched_page_cands, "snippet": False, "r": []}
                p_obj["r"] = reader.read(scrubbed_q, at, p_obj)
                pools.append(p_obj)
                steps.append(
                    f"3b. Opened {', '.join(opened_domains[:3])}: {len(batched_page_cands)} candidate(s) (batched)"
                )
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

        translator = getattr(self.runtime, "translator", None)
        is_mocked_complete = "_complete_role_prompt" in getattr(self.runtime, "__dict__", {})
        if translator is not None and ordered_sources:
            try:
                prefs_tr = translator.get_preferences()
                res_tr_m = translator.resolve_translation_model(prefs_tr["model_preference"])
                can_tr = bool(
                    prefs_tr.get("unlocked", True)
                    and prefs_tr.get("auto_translate_news", True)
                    and (
                        res_tr_m.get("is_cloud")
                        or getattr(self.runtime, "gemma_model", None) is not None
                        or is_mocked_complete
                    )
                )
                if can_tr and (analyzer_m == "template" or is_mocked_complete):
                    from satz_translate import detect_language

                    tgt_lang = prefs_tr["primary_language"]
                    tr_segs: dict[str, str] = {}
                    tr_meta: dict[int, tuple[str, str, str]] = {}
                    for idx_o, src_o in enumerate(ordered_sources):
                        if src_o.get("already_translated"):
                            continue
                        orig_title = str(src_o.get("title") or "").strip()
                        orig_snip = str(src_o.get("snippet") or "").strip()
                        pub_prefix = ""
                        m_dt = re.match(r"^(\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}Z\])\s*(.*)$", orig_snip, re.S)
                        if m_dt:
                            pub_prefix = m_dt.group(1)
                            orig_snip_body = m_dt.group(2).strip()
                        else:
                            orig_snip_body = orig_snip
                        eff_l = detect_language(
                            f"{orig_title}\n{orig_snip_body}",
                            hint_lang=str(src_o.get("language") or "en"),
                        )
                        if not translator.is_language_allowed(eff_l, prefs=prefs_tr):
                            tr_meta[idx_o] = (eff_l, pub_prefix, str(src_o.get("article_id") or ""))
                            if orig_title:
                                tr_segs[f"ot:{idx_o}"] = orig_title[:400]
                            if orig_snip_body:
                                tr_segs[f"os:{idx_o}"] = orig_snip_body[:800]
                    if tr_segs:
                        yield {"status": "translating non-English news sources...", "phase": "reading"}
                        tr_out = translator.translate_segments(
                            tr_segs,
                            target_lang=tgt_lang,
                            context_hint="news headlines and article summaries",
                        )
                        tr_map = tr_out.get("translations") or {}
                        tr_model_id = str(tr_out.get("model") or res_tr_m["model_id"])
                        now_tr = time.time()
                        db_updates: list[tuple[str, str, str, str, str, str, float]] = []
                        for idx_o, (src_l, pub_pfx, aid) in tr_meta.items():
                            new_t = str(tr_map.get(f"ot:{idx_o}") or "").strip()
                            new_s = str(tr_map.get(f"os:{idx_o}") or "").strip()
                            src_o = ordered_sources[idx_o]
                            if new_t:
                                src_o["title"] = new_t
                            if new_s:
                                formatted_s = f"{pub_pfx} {new_s}".strip() if pub_pfx else new_s
                                src_o["snippet"] = formatted_s
                                docs_by_url[str(src_o.get("url") or "")] = formatted_s
                                for d_item in docs:
                                    if d_item.get("url") == src_o.get("url"):
                                        d_item["title"] = new_t or d_item.get("title") or ""
                                        d_item["text"] = formatted_s
                            if aid and (new_t or new_s):
                                db_updates.append((aid, tgt_lang, src_l, new_t, new_s, tr_model_id, now_tr))
                        if db_updates:
                            with self.runtime.store_lock:
                                for upd in db_updates:
                                    self.runtime.store.db.execute(
                                        """
                                        INSERT INTO satz_news_translations
                                          (article_id, target_lang, source_lang, title_tr, snippet_tr, body_tr, model_id, updated_at)
                                        VALUES (?, ?, ?, ?, ?, '', ?, ?)
                                        ON CONFLICT(article_id, target_lang) DO UPDATE SET
                                          source_lang = excluded.source_lang,
                                          title_tr = CASE WHEN LENGTH(excluded.title_tr) > 0 THEN excluded.title_tr ELSE satz_news_translations.title_tr END,
                                          snippet_tr = CASE WHEN LENGTH(excluded.snippet_tr) > 0 THEN excluded.snippet_tr ELSE satz_news_translations.snippet_tr END,
                                          model_id = excluded.model_id,
                                          updated_at = excluded.updated_at
                                        """,
                                        upd,
                                    )
                                self.runtime.store.db.commit()
                elif can_tr and any(src_o.get("article_id") and not src_o.get("already_translated") for src_o in ordered_sources):
                    def _bg_translate_news() -> None:
                        try:
                            self.translate_recent_untranslated(limit=12, recluster=False, background_indexation=True)
                        except Exception:
                            pass

                    threading.Thread(
                        target=_bg_translate_news,
                        daemon=True,
                        name="satz-news-bg-tr",
                    ).start()
            except Exception as exc:
                steps.append(f"4b. On-demand translation skipped: {exc}")

        sources_for_card: list[dict[str, Any]] = []
        sources_for_faithful: list[dict[str, Any]] = []
        source_stats_out: list[dict[str, Any]] = []
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
            u = s["url"]
            cap_len = max(len(full_doc_txt), len(snip_txt))
            sent_len = min(cap_len, 1000 if full_doc_txt else len(snip_txt))
            source_stats_out.append(
                {
                    "id": u,
                    "chars_captured": cap_len,
                    "chars_sent": sent_len,
                    "was_cut": cap_len > sent_len,
                    "capture_mode": str(s.get("capture_mode") or ("fetch" if full_doc_txt else "snippet")),
                }
            )

        yield {
            "__ctx": {
                "t_start": t_start,
                "raw_q": raw_q,
                "scrubbed_q": scrubbed_q,
                "is_briefing": is_briefing,
                "at": at,
                "qt": qt,
                "steps": steps,
                "planner_m": planner_m,
                "reader_m": reader_m,
                "analyzer_m": analyzer_m,
                "results": results,
                "docs": docs,
                "cons": cons,
                "div": div,
                "snippets_map": snippets_map,
                "sources_for_card": sources_for_card,
                "sources_for_faithful": sources_for_faithful,
                "source_stats_out": source_stats_out,
            }
        }

    def _build_news_writer_spec(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """Constructs writer prompt + deterministic fallback text for Stage 5."""
        from src.planck3.writer import TemplateWriter

        cons = ctx["cons"]
        is_briefing = ctx["is_briefing"]
        scrubbed_q = ctx["scrubbed_q"]
        raw_q = ctx["raw_q"]
        at = ctx["at"]
        snippets_map = ctx["snippets_map"]
        sources_for_card = ctx["sources_for_card"]
        sources_for_faithful = ctx["sources_for_faithful"]
        analyzer_m = ctx["analyzer_m"]
        is_cloud_analyzer = self.runtime._parse_cloud_model_id(analyzer_m) is not None

        if cons["value"] is not None and not is_briefing:
            tw = TemplateWriter()
            tw_res = tw.write(scrubbed_q, at, cons, snippets_map)
            fb_answer = tw_res["text"]
            fb_writer = "template"
            if analyzer_m == "template" or not sources_for_card:
                return {"skip_llm": True, "fallback_answer": fb_answer, "fallback_writer": fb_writer}
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
                "Answer in the language of the question, translating any non-English source facts cleanly. "
                "Cite sources inline as [1], [2], etc. Keep numbers and proper names strictly grounded in SOURCES."
            )
            usr_p = f"QUESTION: {raw_q}\n{lead_hint}\n{brain_block}\n\nNEWS SOURCES:\n{src_ctx}"
            return {
                "skip_llm": False,
                "sys_p": sys_p,
                "usr_p": usr_p,
                "max_tokens": 420,
                "max_words": 240,
                "answer_type": at,
                "fallback_answer": fb_answer,
                "fallback_writer": "template",
            }

        if sources_for_card:
            fb_answer = "\n".join(
                f"- **[{s['title']}]({s['url']})** ({s['domain']} · {s['trust']['effective']:.1f}/10) — {s['snippet'][:180]} [{s['idx']}]"
                for s in sources_for_card[:5]
            )
        else:
            fb_answer = "No verified news reporting was found for this query. Try refreshing feeds or widening search terms."

        if not sources_for_card or analyzer_m == "template":
            return {
                "skip_llm": True,
                "fallback_answer": fb_answer,
                "fallback_writer": "template" if sources_for_card else "none",
            }

        src_ctx = "\n\n".join(
            f"[{sf['idx']}] {sf['domain']} ({sf['trust']['effective']:.1f}/10, {sf['trust']['category']}) - {sf['title']} ({sf['url']}):\n"
            f"{neutralize_brain_directives_in_source((sf['body_text'] or sf['snippet'])[:1000])}"
            for sf in sources_for_faithful
        )
        briefing_brain = ""
        if not is_cloud_analyzer:
            b_ctx, _ = self.runtime.brain.build_model_context_with_citations(raw_q, [], max_chars=1200)
            if b_ctx and "No entities stored yet" not in b_ctx:
                briefing_brain = f"{b_ctx}\n\n"
        sys_p = (
            "Summarize the gathered news articles in 2-5 crisp bullet points directly answering the user's request. "
            "Answer in the language of the request, translating any non-English source headlines or facts accurately. "
            "For each bullet, link the headline or source as [Title](url) [n] and keep every statistic and entity strictly from SOURCES."
        )
        return {
            "skip_llm": False,
            "sys_p": sys_p,
            "usr_p": f"QUERY: {raw_q}\n\n{briefing_brain}SOURCES:\n{src_ctx}",
            "max_tokens": 560,
            "max_words": 260,
            "answer_type": "text",
            "fallback_answer": fb_answer,
            "fallback_writer": "extractive (fallback)",
        }

    def _finalize_news_payload(
        self,
        ctx: dict[str, Any],
        *,
        answer_text: str,
        used_writer: str,
        wr_fallback: bool,
        wr_problems: list[str],
    ) -> dict[str, Any]:
        """Computes audit scores, passages, findings, and standard News chat result payload."""
        from src.planck3.candidates import rank_passages
        from src.planck3.web import domain_of

        scrubbed_q = ctx["scrubbed_q"]
        raw_q = ctx["raw_q"]
        is_briefing = ctx["is_briefing"]
        qt = ctx["qt"]
        docs = ctx["docs"]
        results = ctx["results"]
        cons = ctx["cons"]
        div = ctx["div"]
        steps = ctx["steps"]
        sources_for_card = ctx["sources_for_card"]
        source_stats_out = ctx["source_stats_out"]
        planner_m = ctx["planner_m"]
        reader_m = ctx["reader_m"]
        t_start = ctx["t_start"]

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

        with self.runtime.store_lock:
            if not self.runtime.pause_learning and scrubbed_q:
                self.runtime.store.log_query(scrubbed_q, domain_of(sources_for_card[0]["url"]) if sources_for_card else scrubbed_q[:40])
                if passages:
                    self.runtime.store.add_passages(passages[:6], scrubbed_q[:40], f"[conv:conv-news] {scrubbed_q}")

        findings_out: list[dict[str, Any]] = []
        seen_finding_imgs: set[str] = set()
        for s in sources_for_card:
            if s.get("image_url"):
                img_u = str(s["image_url"]).strip()
                seen_finding_imgs.add(img_u)
                findings_out.append(
                    {
                        "image_url": img_u,
                        "title": s["title"],
                        "page_url": s["url"],
                    }
                )
            else:
                for fd in self.runtime.get_source_findings(s["url"], s["url"])[:1]:
                    img_u = str(fd.get("image_url") or "").strip()
                    if img_u:
                        seen_finding_imgs.add(img_u)
                        if not s.get("image_url"):
                            s["image_url"] = img_u
                    findings_out.append(fd)

        if sources_for_card and hasattr(self.runtime, "merge_previews_into_sources"):
            try:
                self.runtime.merge_previews_into_sources(
                    sources_for_card,
                    findings_out,
                    seen_finding_imgs,
                    max_items=8,
                    max_findings=6,
                )
            except Exception:
                pass

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
            "sources": [
                {
                    "url": s["url"],
                    "title": s["title"],
                    "domain": s["domain"],
                    "snippet": str(s.get("snippet") or "")[:240],
                    "image_url": str(s.get("image_url") or ""),
                    **({"favicon_url": str(s["favicon_url"])} if s.get("favicon_url") else {}),
                }
                for s in sources_for_card
            ],
            "source_stats": source_stats_out,
            "findings": findings_out[:6],
            "answer_meta": answer_meta,
        }

    def answer_news_question(
        self,
        question: str,
        open_sources: list[dict[str, Any]] | None = None,
        roles_override: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Full Planck 3.0 audited pipeline for News chat:
        1. `news_planner` decomposes + scrubs query (PII Scrubber Gate)
        2. `news_capture` gathers local articles + open tabs + parallel web results
        3. Trust-blind `news_reader` scores candidates (batched)
        4. `consolidate()` runs twice (`personal` vs `system_only`) for counterfactual diff
        5. `news_analyzer` writes concise summary guarded by `faithful_news` (template fallback)
        """
        ctx: dict[str, Any] = {}
        for ev in self._iter_news_evidence(question, open_sources=open_sources, roles_override=roles_override):
            if "__ctx" in ev:
                ctx = ev["__ctx"]

        spec = self._build_news_writer_spec(ctx)
        wr_fallback = False
        wr_problems: list[str] = []
        answer_text = spec["fallback_answer"]
        used_writer = spec["fallback_writer"]
        analyzer_m = ctx["analyzer_m"]

        if not spec["skip_llm"]:
            try:
                cand_txt = _complete_role_fast(
                    self.runtime,
                    analyzer_m,
                    spec["sys_p"],
                    spec["usr_p"],
                    temperature=0.15,
                    max_tokens=spec["max_tokens"],
                    thinking_budget=0,
                )
                ok_f, probs = faithful_news(
                    cand_txt,
                    ctx["raw_q"],
                    ctx["sources_for_faithful"],
                    required_value=None,
                    answer_type=spec["answer_type"],
                    max_words=spec["max_words"],
                    allow_brief=True,
                )
                if ok_f:
                    answer_text = cand_txt
                    used_writer = analyzer_m
                else:
                    wr_fallback = True
                    wr_problems = probs
                    ctx["steps"].append(f"5. Faithfulness fallback ({analyzer_m}): {'; '.join(probs[:2])}")
            except Exception as exc:
                wr_fallback = True
                wr_problems = [str(exc)]
                ctx["steps"].append(f"5. Analyzer fallback ({analyzer_m}): {exc}")

        return self._finalize_news_payload(
            ctx,
            answer_text=answer_text,
            used_writer=used_writer,
            wr_fallback=wr_fallback,
            wr_problems=wr_problems,
        )

    def stream_news_question(
        self,
        question: str,
        open_sources: list[dict[str, Any]] | None = None,
        roles_override: dict[str, str] | None = None,
    ):
        """
        SSE streaming generator for News chat: emits live phase updates, early `source_stats`,
        incremental writer `delta` tokens, post-stream `faithful_news` check, and final `done` payload.
        """
        ctx: dict[str, Any] = {}
        ev_q: queue.Queue[dict[str, Any]] = queue.Queue()
        ev_err: list[Exception] = []

        def _gather_ev() -> None:
            try:
                for ev in self._iter_news_evidence(question, open_sources=open_sources, roles_override=roles_override):
                    ev_q.put(ev)
            except Exception as exc:
                ev_err.append(exc)
            finally:
                ev_q.put({"__ev_done": True})

        gt = threading.Thread(target=_gather_ev, daemon=True, name="satz-news-evidence")
        gt.start()
        while True:
            try:
                ev = ev_q.get(timeout=4.0)
            except queue.Empty:
                yield {"phase": "heartbeat"}
                continue
            if "__ev_done" in ev:
                break
            if "__ctx" in ev:
                ctx = ev["__ctx"]
            else:
                yield ev
        gt.join(timeout=2.0)
        if ev_err:
            raise ev_err[0]
        if not ctx:
            raise RuntimeError("News evidence assembly produced no context")

        early_sources = [
            {"url": s["url"], "title": s["title"], "domain": s["domain"]}
            for s in ctx["sources_for_card"]
        ]
        yield {
            "source_stats": ctx["source_stats_out"],
            "sources": early_sources,
            "status": f"synthesizing from {len(early_sources)} weighed news source(s) via {ctx['analyzer_m']}...",
            "phase": "generating",
        }

        spec = self._build_news_writer_spec(ctx)
        wr_fallback = False
        wr_problems: list[str] = []
        answer_text = spec["fallback_answer"]
        used_writer = spec["fallback_writer"]
        analyzer_m = ctx["analyzer_m"]

        if spec["skip_llm"]:
            if answer_text:
                yield {"delta": answer_text}
        else:
            cand_txt = ""
            try:
                is_mocked_complete = "_complete_role_prompt" in getattr(self.runtime, "__dict__", {})
                stream_fn = getattr(self.runtime, "_stream_role_prompt", None)
                if callable(stream_fn) and not is_mocked_complete:
                    started_stream = False
                    for sev in stream_fn(
                        analyzer_m,
                        spec["sys_p"],
                        spec["usr_p"],
                        temperature=0.15,
                        max_tokens=spec["max_tokens"],
                        thinking_budget=0,
                    ):
                        if "__full_raw" in sev:
                            cand_txt = str(sev.get("__full_raw") or "")
                        elif sev.get("delta"):
                            if not started_stream:
                                yield {"status": "streaming response tokens...", "phase": "streaming"}
                                started_stream = True
                            yield {"delta": sev["delta"]}
                        elif sev.get("phase") == "heartbeat":
                            yield sev
                else:
                    cand_txt = _complete_role_fast(
                        self.runtime,
                        analyzer_m,
                        spec["sys_p"],
                        spec["usr_p"],
                        temperature=0.15,
                        max_tokens=spec["max_tokens"],
                        thinking_budget=0,
                    )
                    if cand_txt:
                        yield {"delta": cand_txt}

                ok_f, probs = faithful_news(
                    cand_txt,
                    ctx["raw_q"],
                    ctx["sources_for_faithful"],
                    required_value=None,
                    answer_type=spec["answer_type"],
                    max_words=spec["max_words"],
                    allow_brief=True,
                )
                if ok_f:
                    answer_text = cand_txt
                    used_writer = analyzer_m
                else:
                    wr_fallback = True
                    wr_problems = probs
                    ctx["steps"].append(f"5. Faithfulness fallback ({analyzer_m}): {'; '.join(probs[:2])}")
                    if cand_txt:
                        yield {"replace_text": answer_text, "fallback": True}
                    else:
                        yield {"delta": answer_text}
            except Exception as exc:
                wr_fallback = True
                wr_problems = [str(exc)]
                ctx["steps"].append(f"5. Analyzer fallback ({analyzer_m}): {exc}")
                if cand_txt:
                    yield {"replace_text": answer_text, "fallback": True}
                else:
                    yield {"delta": answer_text}

        final_payload = self._finalize_news_payload(
            ctx,
            answer_text=answer_text,
            used_writer=used_writer,
            wr_fallback=wr_fallback,
            wr_problems=wr_problems,
        )
        done_ev = {"done": True, **final_payload}
        if wr_fallback:
            done_ev["annotated_text"] = answer_text
            done_ev["fallback"] = True
        yield done_ev

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

        now_ts = time.time()
        upd_ts = float(cr["updated_at"] or now_ts)
        pub_iso = _utc_iso_from_ts(upd_ts)
        sync_iso = _utc_iso_from_ts(now_ts)
        safe_headline = neutralize_brain_directives_in_source(str(cr["headline"] or ""))
        safe_summary_md = neutralize_brain_directives_in_source(str(cr["summary_md"] or ""))
        top_domains = [f"{r['domain']} ({float(r['trust_effective']):.1f})" for r in arows]
        primary_url = str(arows[0]["url"]) if arows else ""
        ent = self.runtime.brain.upsert_entity(
            entity_type="story",
            name=safe_headline[:90],
            summary=f"[{cr['band']} · {float(cr['confidence10']):.1f}/10 across {cr['independent_families']} fam] {safe_headline}",
            attributes={
                "confidence10": float(cr["confidence10"]),
                "band": cr["band"],
                "families": int(cr["independent_families"]),
                "sources": ", ".join(top_domains[:4]),
                "published_at": pub_iso,
                "synced_at": sync_iso,
                "$published_ts": round(upd_ts, 3),
                "$synced_ts": round(now_ts, 3),
                "$cluster_id": cluster_id,
                "$source": f"news:{cluster_id}",
            },
            content=safe_summary_md,
            source_url=primary_url,
            tier=2,
            actor="user/news_save",
        )
        slug = str(ent.get("slug") or "")
        with self.runtime.store_lock:
            self.runtime.store.db.execute(
                "UPDATE satz_news_clusters SET brain_slug = ?, brain_synced_at = ? WHERE cluster_id = ?",
                (slug, now_ts, cluster_id),
            )
            self.runtime.store.db.commit()
        return {"ok": True, "entity": ent}

    def get_status(self) -> dict[str, Any]:
        with self.runtime.store_lock:
            art_cnt = self.runtime.store.db.execute("SELECT COUNT(*) FROM satz_news_articles").fetchone()[0]
            cl_cnt = self.runtime.store.db.execute("SELECT COUNT(*) FROM satz_news_clusters WHERE is_hidden = 0").fetchone()[0]
            feed_cnt = self.runtime.store.db.execute("SELECT COUNT(*) FROM satz_news_feeds WHERE enabled = 1").fetchone()[0]
            topic_cnt = self.runtime.store.db.execute("SELECT COUNT(*) FROM satz_news_topics WHERE suppressed = 0").fetchone()[0]
            brain_cl_cnt = self.runtime.store.db.execute(
                "SELECT COUNT(*) FROM satz_news_clusters WHERE is_hidden = 0 AND brain_slug IS NOT NULL AND brain_slug != ''"
            ).fetchone()[0]
            followed_cnt = self.runtime.store.db.execute(
                "SELECT COUNT(*) FROM satz_news_followed_stories WHERE status = 'active'"
            ).fetchone()[0]
            unread_updates_cnt = self.runtime.store.db.execute(
                "SELECT COALESCE(SUM(unread_updates), 0) FROM satz_news_followed_stories WHERE status = 'active'"
            ).fetchone()[0]
        interval_secs = float(getattr(self.runtime, "news_refresh_interval_secs", 3600.0))
        last_sync_at = self._get_meta_float("news_last_sync_at")
        last_brain_sync_at = self._get_meta_float("news_last_brain_sync_at")
        return {
            "articles": int(art_cnt or 0),
            "clusters": int(cl_cnt or 0),
            "feeds_enabled": int(feed_cnt or 0),
            "topics": int(topic_cnt or 0),
            "brain_stories": int(brain_cl_cnt or 0),
            "followed_stories": int(followed_cnt or 0),
            "unread_story_updates": int(unread_updates_cnt or 0),
            "sync_interval_seconds": interval_secs,
            "last_sync_at": last_sync_at,
            "next_sync_at": (last_sync_at + interval_secs) if last_sync_at > 0 else 0.0,
            "last_brain_sync_at": last_brain_sync_at,
            "syncing": bool(getattr(self.runtime, "news_sync_in_progress", False)),
        }

    # ── Evolving Followed Stories (Pin + Auto-Index Evolution) ───────────────
    @staticmethod
    def _extract_story_keywords(title: str, extra_texts: list[str] | None = None, limit: int = 12) -> list[str]:
        noise = {
            "reuters", "apnews", "associated", "press", "latest", "update", "updates",
            "report", "reports", "reporting", "says", "said", "amid", "after", "over",
            "under", "against", "between", "through", "world", "europe", "european",
            "today", "yesterday", "week", "month", "year", "news", "story", "stories",
        }
        primary = [t for t in _tokenize_title(title) if t not in noise]
        seen: set[str] = set()
        out: list[str] = []
        for tok in primary:
            if tok not in seen:
                seen.add(tok)
                out.append(tok)
        if extra_texts:
            freq: dict[str, int] = {}
            for txt in extra_texts:
                for tok in _tokenize_title(txt):
                    if tok not in noise and tok not in seen:
                        freq[tok] = freq.get(tok, 0) + 1
            for tok, _cnt in sorted(freq.items(), key=lambda x: (-x[1], x[0])):
                seen.add(tok)
                out.append(tok)
                if len(out) >= limit:
                    break
        return out[:limit]

    def _synthesize_followed_story_overview(
        self,
        title: str,
        updates: list[dict[str, Any]],
        *,
        allow_llm: bool = True,
    ) -> tuple[str, str]:
        if not updates:
            return (f"Tracking updates for **{title}** across configured sources.", "none")

        # Collapse identical wire copies so overview cites distinct reporting families
        seen_fam: set[str] = set()
        fam_updates: list[dict[str, Any]] = []
        for u in updates:
            fk = str(u.get("family") or u.get("domain") or "")
            if fk in seen_fam:
                continue
            seen_fam.add(fk)
            fam_updates.append(u)

        chrono = sorted(fam_updates, key=lambda u: float(u.get("published_at") or 0.0))
        latest_first = sorted(fam_updates, key=lambda u: (-float(u.get("published_at") or 0.0), -float(u.get("trust_effective") or 0.0)))

        lines: list[str] = [
            f"**Evolution overview** ({len(updates)} update(s) across {len(fam_updates)} independent source family/families):"
        ]
        if len(chrono) == 1:
            u0 = chrono[0]
            ts0 = _utc_iso_from_ts(float(u0.get("published_at") or time.time()))
            t0 = str(u0.get("title_tr") or u0.get("title") or title)
            s0 = str(u0.get("snippet_tr") or u0.get("snippet") or "")[:200]
            lines.append(f"- **Initial report ({ts0}, {u0['domain']} · {float(u0['trust_effective']):.1f}/10):** {t0} — {s0}")
        else:
            earliest = chrono[0]
            ts_e = _utc_iso_from_ts(float(earliest.get("published_at") or time.time()))
            lines.append(
                f"- **Origin ({ts_e}, {earliest['domain']} · {float(earliest['trust_effective']):.1f}/10):** "
                f"{str(earliest.get('title_tr') or earliest.get('title') or '')}"
            )
            for idx_u, u in enumerate(latest_first[:4], 1):
                ts_u = _utc_iso_from_ts(float(u.get("published_at") or time.time()))
                tag = "New update" if u.get("is_new") else "Development"
                u_t = str(u.get("title_tr") or u.get("title") or "")
                u_s = str(u.get("snippet_tr") or u.get("snippet") or "")[:180]
                lines.append(
                    f"- **{tag} ({ts_u}, {u['domain']} · {float(u['trust_effective']):.1f}/10) [{idx_u}]:** {u_t}"
                    + (f" — {u_s}" if u_s else "")
                )

        fb_text = "\n".join(lines)
        cfg = self.runtime.get_model_management_config()
        analyzer_m = str(cfg["roles"].get("news_analyzer") or cfg["roles"].get("news_reader") or "template")
        is_mocked_complete = "_complete_role_prompt" in getattr(self.runtime, "__dict__", {})
        can_run_llm = (
            allow_llm
            and analyzer_m != "template"
            and (":" in analyzer_m or getattr(self.runtime, "gemma_model", None) is not None or is_mocked_complete)
        )
        if not can_run_llm:
            return (fb_text, "extractive")

        ctx_lines = []
        for idx_u, u in enumerate(latest_first[:8], 1):
            ts_u = _utc_iso_from_ts(float(u.get("published_at") or time.time()))
            utitle = neutralize_brain_directives_in_source(str(u.get("title_tr") or u.get("title") or ""))
            usnip = neutralize_brain_directives_in_source(str(u.get("snippet_tr") or u.get("snippet") or "")[:360])
            ctx_lines.append(
                f"[{idx_u}] ({ts_u}) {u['domain']} (trust={float(u['trust_effective']):.1f}/10): {utitle} | {usnip}"
            )
        t_target = self._primary_translation_target()
        sys_p = (
            "Synthesize an evolving news story overview strictly from the chronological source updates provided. "
            "Write 3-5 concise bullets covering: (1) how the story started, (2) what changed in later updates, "
            "and (3) current status or points of disagreement. Cite source indices like [1], [2]. "
            f"Never invent facts outside the updates. Write in {t_target}."
        )
        usr_p = f"STORY: {title}\nUPDATES (newest first):\n" + "\n".join(ctx_lines)
        try:
            cand = _complete_role_fast(
                self.runtime,
                analyzer_m,
                sys_p,
                usr_p,
                temperature=0.1,
                max_tokens=360,
                thinking_budget=0,
            ).strip()
            if cand and len(cand) >= 24:
                return (cand, analyzer_m)
        except Exception:
            pass
        return (fb_text, "extractive")

    def pin_followed_story(
        self,
        *,
        cluster_id: str = "",
        title: str = "",
        url: str = "",
        article_id: str = "",
        keywords: list[str] | None = None,
    ) -> dict[str, Any]:
        from src.planck3.registry import BAND_LABEL

        now_ts = time.time()
        cid = (cluster_id or "").strip()
        raw_title = (title or "").strip()
        raw_url = (url or "").strip()
        aid = (article_id or "").strip()
        t_target = self._primary_translation_target()

        seed_articles: list[dict[str, Any]] = []
        anchor_domain = ""
        lead_image = ""
        conf10 = 6.0
        band_code = "good"
        indep = 1

        with self.runtime.store_lock:
            if cid:
                cr = self.runtime.store.db.execute(
                    "SELECT * FROM satz_news_clusters WHERE cluster_id = ?",
                    (cid,),
                ).fetchone()
                if cr:
                    if not raw_title:
                        raw_title = str(cr["headline"] or "").strip()
                    conf10 = float(cr["confidence10"] or 6.0)
                    band_code = str(cr["band"] or "good")
                    indep = int(cr["independent_families"] or 1)
                arows = self.runtime.store.db.execute(
                    """
                    SELECT a.*, COALESCE(nt.title_tr, '') AS title_tr, COALESCE(nt.snippet_tr, '') AS snippet_tr
                    FROM satz_news_articles a
                    LEFT JOIN satz_news_translations nt ON nt.article_id = a.article_id AND nt.target_lang = ?
                    WHERE a.cluster_id = ?
                    ORDER BY a.trust_effective DESC, a.published_at DESC
                    """,
                    (t_target, cid),
                ).fetchall()
                seed_articles = [dict(r) for r in arows]
            elif aid or raw_url:
                ar = self.runtime.store.db.execute(
                    """
                    SELECT a.*, COALESCE(nt.title_tr, '') AS title_tr, COALESCE(nt.snippet_tr, '') AS snippet_tr
                    FROM satz_news_articles a
                    LEFT JOIN satz_news_translations nt ON nt.article_id = a.article_id AND nt.target_lang = ?
                    WHERE a.article_id = ? OR a.url = ?
                    LIMIT 1
                    """,
                    (t_target, aid, raw_url),
                ).fetchone()
                if ar:
                    d_ar = dict(ar)
                    seed_articles = [d_ar]
                    if not raw_title:
                        raw_title = str(d_ar.get("title_tr") or d_ar.get("title") or "").strip()
                    cid = str(d_ar.get("cluster_id") or "")

            if cid:
                existing = self.runtime.store.db.execute(
                    "SELECT story_id FROM satz_news_followed_stories WHERE seed_cluster_id = ? AND status = 'active'",
                    (cid,),
                ).fetchone()
                if existing:
                    st_id = str(existing["story_id"])
                    stories = self.list_followed_stories()["stories"]
                    found = next((s for s in stories if s["story_id"] == st_id), None)
                    return {"ok": True, "already_pinned": True, "story": found}

        if not raw_title:
            raise ValueError("Cannot pin story without headline/cluster/article")

        # Prefer translated headline if primary language differs cleanly
        best_title = raw_title
        if seed_articles and seed_articles[0].get("title_tr"):
            best_title = str(seed_articles[0]["title_tr"]).strip() or raw_title

        seed_key = cid or raw_url or raw_title.lower()
        story_id = f"story-{hashlib.sha1(seed_key.encode('utf-8')).hexdigest()[:12]}"
        extra_snips = [
            f"{a.get('title_tr') or a.get('title') or ''} {a.get('snippet_tr') or a.get('snippet') or ''}"
            for a in seed_articles[:5]
        ]
        kws = [str(k).strip().lower() for k in (keywords or []) if str(k).strip()] or self._extract_story_keywords(
            best_title, extra_snips
        )
        if raw_title.lower() != best_title.lower():
            for tk in _tokenize_title(raw_title):
                if tk not in kws and len(kws) < 16:
                    kws.append(tk)

        if seed_articles:
            anchor_domain = str(seed_articles[0].get("domain") or "")
            lead_image = next((str(a.get("image_url") or "") for a in seed_articles if a.get("image_url")), "")

        max_pub = max((float(a.get("published_at") or now_ts) for a in seed_articles), default=now_ts)

        with self.runtime.store_lock:
            self.runtime.store.db.execute(
                """
                INSERT INTO satz_news_followed_stories
                (story_id, title, summary_overview, summary_model, keywords_json, seed_cluster_id,
                 anchor_domain, lead_image, confidence10, band, independent_families,
                 update_count, unread_updates, status, created_at, updated_at, last_synthesized_at)
                VALUES (?, ?, '', '', ?, ?, ?, ?, ?, ?, ?, ?, 0, 'active', ?, ?, 0.0)
                ON CONFLICT(story_id) DO UPDATE SET
                    status = 'active',
                    keywords_json = excluded.keywords_json,
                    seed_cluster_id = COALESCE(excluded.seed_cluster_id, satz_news_followed_stories.seed_cluster_id),
                    updated_at = MAX(satz_news_followed_stories.updated_at, excluded.updated_at)
                """,
                (
                    story_id,
                    best_title,
                    json.dumps(kws, ensure_ascii=False),
                    cid or None,
                    anchor_domain,
                    lead_image,
                    conf10,
                    band_code,
                    indep,
                    len(seed_articles),
                    now_ts,
                    max_pub,
                ),
            )
            for sa in seed_articles:
                dom = str(sa.get("domain") or "")
                trec = self._trust_for_domain(dom, use_personal=True)
                tsys = self._trust_for_domain(dom, use_personal=False)
                self.runtime.store.db.execute(
                    """
                    INSERT OR IGNORE INTO satz_news_followed_story_updates
                    (story_id, article_id, url, domain, family, title, snippet, language, image_url,
                     published_at, added_at, trust_system, trust_effective, conflict, match_score, is_seed, is_new)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 10.0, 1, 0)
                    """,
                    (
                        story_id,
                        str(sa.get("article_id") or ""),
                        str(sa.get("url") or ""),
                        dom,
                        str(sa.get("family") or trec["family"] or dom),
                        str(sa.get("title") or ""),
                        str(sa.get("snippet") or "")[:450],
                        str(sa.get("language") or "en"),
                        str(sa.get("image_url") or ""),
                        float(sa.get("published_at") or now_ts),
                        now_ts,
                        round(float(tsys["system"]), 2),
                        round(float(trec["effective"]), 2),
                        int(bool(trec.get("conflict"))),
                    ),
                )
            self.runtime.store.db.commit()

        # Sweep related already-indexed articles across sources and synthesize initial evolving overview
        self.sync_followed_stories(synthesize_new=True, force_story_id=story_id, allow_llm_in_bg=False)
        stories = self.list_followed_stories()["stories"]
        found = next((s for s in stories if s["story_id"] == story_id), None)
        return {"ok": True, "already_pinned": False, "story": found}

    def unpin_followed_story(self, story_id: str) -> dict[str, Any]:
        sid = (story_id or "").strip()
        if not sid:
            return {"ok": False, "error": "story_id required"}
        with self.runtime.store_lock:
            self.runtime.store.db.execute("DELETE FROM satz_news_followed_story_updates WHERE story_id = ?", (sid,))
            self.runtime.store.db.execute("DELETE FROM satz_news_followed_stories WHERE story_id = ?", (sid,))
            self.runtime.store.db.commit()
        return {"ok": True, "unpinned": sid}

    def mark_followed_story_read(self, story_id: str) -> dict[str, Any]:
        sid = (story_id or "").strip()
        if not sid:
            return {"ok": False, "error": "story_id required"}
        with self.runtime.store_lock:
            self.runtime.store.db.execute("UPDATE satz_news_followed_story_updates SET is_new = 0 WHERE story_id = ?", (sid,))
            self.runtime.store.db.execute("UPDATE satz_news_followed_stories SET unread_updates = 0 WHERE story_id = ?", (sid,))
            self.runtime.store.db.commit()
        return {"ok": True, "story_id": sid}

    def sync_followed_stories(
        self,
        *,
        synthesize_new: bool = True,
        force_story_id: str = "",
        allow_llm_in_bg: bool = False,
    ) -> dict[str, Any]:
        """
        Matches newly indexed articles across all configured/synced sources against pinned stories,
        records chronological updates, and refreshes each story's evolving overview.
        """
        from src.planck3.qtype import PENALTY
        from src.planck3.registry import band

        now_ts = time.time()
        t_target = self._primary_translation_target()
        cutoff = now_ts - 30 * 86400.0

        with self.runtime.store_lock:
            story_rows = self.runtime.store.db.execute(
                "SELECT * FROM satz_news_followed_stories WHERE status = 'active' ORDER BY updated_at DESC"
            ).fetchall()
            if not story_rows:
                return {"ok": True, "stories_checked": 0, "new_updates_added": 0}
            art_rows = self.runtime.store.db.execute(
                """
                SELECT a.*, COALESCE(nt.title_tr, '') AS title_tr, COALESCE(nt.snippet_tr, '') AS snippet_tr
                FROM satz_news_articles a
                LEFT JOIN satz_news_translations nt ON nt.article_id = a.article_id AND nt.target_lang = ?
                WHERE a.published_at >= ?
                ORDER BY a.published_at DESC
                LIMIT 400
                """,
                (t_target, cutoff),
            ).fetchall()

        noise_toks = {
            "reuters", "apnews", "latest", "update", "report", "says", "said",
            "amid", "after", "over", "europe", "european", "today", "news",
        }
        articles = [dict(r) for r in art_rows]
        total_new_added = 0
        updated_story_ids: list[str] = []

        for sr in story_rows:
            sid = str(sr["story_id"])
            if force_story_id and sid != force_story_id:
                continue
            seed_cid = str(sr["seed_cluster_id"] or "")
            try:
                kws = [str(k).lower() for k in json.loads(sr["keywords_json"] or "[]")]
            except Exception:
                kws = []
            title_anchor_toks = {t for t in _tokenize_title(str(sr["title"] or "")) if t not in noise_toks}
            kw_toks = set(title_anchor_toks) | {t for t in kws[:8] if t not in noise_toks}
            if not title_anchor_toks and kw_toks:
                title_anchor_toks = set(kw_toks)

            with self.runtime.store_lock:
                existing_rows = self.runtime.store.db.execute(
                    "SELECT article_id, url FROM satz_news_followed_story_updates WHERE story_id = ?",
                    (sid,),
                ).fetchall()
            seen_aids = {str(er["article_id"]) for er in existing_rows}
            seen_urls = {str(er["url"]) for er in existing_rows}

            matched_new: list[tuple[float, dict[str, Any]]] = []
            for art in articles:
                aid = str(art.get("article_id") or "")
                aurl = str(art.get("url") or "")
                if not aid or aid in seen_aids or aurl in seen_urls:
                    continue
                same_cluster = bool(seed_cid and str(art.get("cluster_id") or "") == seed_cid)
                art_title_toks = {
                    t
                    for t in _tokenize_title(f"{art.get('title') or ''} {art.get('title_tr') or ''}")
                    if t not in noise_toks
                }
                art_snip_toks = _tokenize_title(f"{art.get('snippet') or ''} {art.get('snippet_tr') or ''}")
                title_inter = title_anchor_toks & art_title_toks
                all_inter = kw_toks & (art_title_toks | art_snip_toks)
                ratio_title = len(title_inter) / max(1, len(title_anchor_toks))
                score = float(len(title_inter)) * 2.0 + float(len(all_inter)) * 0.75 + (10.0 if same_cluster else 0.0)
                is_match = (
                    same_cluster
                    or len(title_inter) >= 3
                    or (len(title_inter) >= 2 and (ratio_title >= 0.34 or len(all_inter) >= 3))
                    or len(all_inter) >= 4
                )
                if not is_match:
                    continue
                seen_aids.add(aid)
                seen_urls.add(aurl)
                matched_new.append((score, art))

            if matched_new:
                with self.runtime.store_lock:
                    for sc, art in matched_new:
                        dom = str(art.get("domain") or "")
                        trec = self._trust_for_domain(dom, use_personal=True)
                        tsys = self._trust_for_domain(dom, use_personal=False)
                        self.runtime.store.db.execute(
                            """
                            INSERT OR IGNORE INTO satz_news_followed_story_updates
                            (story_id, article_id, url, domain, family, title, snippet, language, image_url,
                             published_at, added_at, trust_system, trust_effective, conflict, match_score, is_seed, is_new)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1)
                            """,
                            (
                                sid,
                                str(art["article_id"]),
                                str(art["url"]),
                                dom,
                                str(art.get("family") or trec["family"] or dom),
                                str(art.get("title") or ""),
                                str(art.get("snippet") or "")[:450],
                                str(art.get("language") or "en"),
                                str(art.get("image_url") or ""),
                                float(art.get("published_at") or now_ts),
                                now_ts,
                                round(float(tsys["system"]), 2),
                                round(float(trec["effective"]), 2),
                                int(bool(trec.get("conflict"))),
                                round(sc, 2),
                            ),
                        )
                    self.runtime.store.db.commit()
                total_new_added += len(matched_new)
                updated_story_ids.append(sid)

            # Recompute aggregate metrics and overview whenever new updates arrived or forced
            with self.runtime.store_lock:
                all_upds_rows = self.runtime.store.db.execute(
                    """
                    SELECT u.*, COALESCE(nt.title_tr, '') AS title_tr, COALESCE(nt.snippet_tr, '') AS snippet_tr
                    FROM satz_news_followed_story_updates u
                    LEFT JOIN satz_news_translations nt ON nt.article_id = u.article_id AND nt.target_lang = ?
                    WHERE u.story_id = ?
                    ORDER BY u.published_at DESC
                    """,
                    (t_target, sid),
                ).fetchall()
            all_upds = [dict(ur) for ur in all_upds_rows]
            # Refresh effective trust under current profile rules
            fam_best: dict[str, dict[str, Any]] = {}
            for u in all_upds:
                trec = self._trust_for_domain(str(u["domain"]), use_personal=True)
                u["trust_effective"] = round(float(trec["effective"]), 2)
                fk = str(u.get("family") or u["domain"])
                if fk not in fam_best or u["trust_effective"] > fam_best[fk]["trust_effective"]:
                    fam_best[fk] = u
            fams_sorted = sorted(fam_best.values(), key=lambda x: -float(x["trust_effective"]))
            indep_cnt = max(1, len(fams_sorted))
            top_tr = float(fams_sorted[0]["trust_effective"]) if fams_sorted else float(sr["confidence10"] or 5.0)
            agree_b = min(2.0, sum(1.0 for f in fams_sorted[1:] if float(f["trust_effective"]) >= 7.0))
            conf10 = round(max(0.0, min(10.0, top_tr + agree_b - PENALTY["news"])), 1)
            band_c = band(conf10)
            unread_cnt = sum(1 for u in all_upds if u.get("is_new"))
            latest_pub = max((float(u["published_at"]) for u in all_upds), default=float(sr["updated_at"] or now_ts))
            lead_img = str(sr["lead_image"] or "") or next((str(u.get("image_url") or "") for u in all_upds if u.get("image_url")), "")

            need_synth = bool(matched_new) or not str(sr["summary_overview"] or "").strip() or (force_story_id == sid)
            new_ov = str(sr["summary_overview"] or "")
            new_mod = str(sr["summary_model"] or "")
            new_synth_ts = float(sr["last_synthesized_at"] or 0.0)
            if need_synth and all_upds:
                new_ov, new_mod = self._synthesize_followed_story_overview(
                    str(sr["title"]),
                    all_upds,
                    allow_llm=synthesize_new and (allow_llm_in_bg or bool(force_story_id)),
                )
                new_synth_ts = now_ts

            with self.runtime.store_lock:
                self.runtime.store.db.execute(
                    """
                    UPDATE satz_news_followed_stories
                    SET summary_overview = ?, summary_model = ?, lead_image = ?,
                        confidence10 = ?, band = ?, independent_families = ?,
                        update_count = ?, unread_updates = ?, updated_at = ?, last_synthesized_at = ?
                    WHERE story_id = ?
                    """,
                    (
                        new_ov,
                        new_mod,
                        lead_img,
                        conf10,
                        band_c,
                        indep_cnt,
                        len(all_upds),
                        unread_cnt,
                        latest_pub,
                        new_synth_ts,
                        sid,
                    ),
                )
                self.runtime.store.db.commit()

        return {
            "ok": True,
            "stories_checked": len(story_rows),
            "new_updates_added": total_new_added,
            "updated_story_ids": updated_story_ids,
        }

    def list_followed_stories(self, include_updates: bool = True) -> dict[str, Any]:
        from src.planck3.registry import BAND_LABEL

        t_target = self._primary_translation_target()
        with self.runtime.store_lock:
            story_rows = self.runtime.store.db.execute(
                """
                SELECT * FROM satz_news_followed_stories
                WHERE status = 'active'
                ORDER BY (unread_updates > 0) DESC, updated_at DESC
                """
            ).fetchall()

            updates_by_story: dict[str, list[dict[str, Any]]] = {}
            if include_updates and story_rows:
                sids = [str(r["story_id"]) for r in story_rows]
                ph = ",".join("?" for _ in sids)
                urows = self.runtime.store.db.execute(
                    f"""
                    SELECT u.*,
                           COALESCE(nt.title_tr, '') AS title_tr,
                           COALESCE(nt.snippet_tr, '') AS snippet_tr,
                           COALESCE(nt.body_tr, '') AS body_tr,
                           COALESCE(nt.source_lang, '') AS tr_source_lang,
                           COALESCE(nt.target_lang, '') AS tr_target_lang
                    FROM satz_news_followed_story_updates u
                    LEFT JOIN satz_news_translations nt ON nt.article_id = u.article_id AND nt.target_lang = ?
                    WHERE u.story_id IN ({ph})
                    ORDER BY u.published_at DESC
                    """,
                    (t_target, *sids),
                ).fetchall()
                for ur in urows:
                    trec = self._trust_for_domain(str(ur["domain"]), use_personal=True)
                    updates_by_story.setdefault(str(ur["story_id"]), []).append(
                        {
                            "article_id": ur["article_id"],
                            "url": ur["url"],
                            "domain": ur["domain"],
                            "family": ur["family"],
                            "title": ur["title"],
                            "title_tr": ur["title_tr"] or None,
                            "snippet": ur["snippet"] or "",
                            "snippet_tr": ur["snippet_tr"] or None,
                            "translated_text": ur["body_tr"] or ur["snippet_tr"] or None,
                            "translation_source_lang": ur["tr_source_lang"] or None,
                            "translation_target_lang": ur["tr_target_lang"] or None,
                            "language": ur["language"] or "en",
                            "image_url": ur["image_url"] or "",
                            "published_at": float(ur["published_at"] or 0.0),
                            "added_at": float(ur["added_at"] or 0.0),
                            "trust_system": float(ur["trust_system"] or 5.0),
                            "trust_effective": round(float(trec["effective"]), 2),
                            "conflict": bool(trec.get("conflict")),
                            "is_seed": bool(ur["is_seed"]),
                            "is_new": bool(ur["is_new"]),
                        }
                    )

        stories_out: list[dict[str, Any]] = []
        for sr in story_rows:
            sid = str(sr["story_id"])
            b_code = str(sr["band"] or "good")
            upds = updates_by_story.get(sid, [])
            stories_out.append(
                {
                    "story_id": sid,
                    "title": sr["title"],
                    "summary_overview": sr["summary_overview"] or "",
                    "summary_model": sr["summary_model"] or "extractive",
                    "keywords": json.loads(sr["keywords_json"] or "[]"),
                    "seed_cluster_id": sr["seed_cluster_id"] or "",
                    "anchor_domain": sr["anchor_domain"] or "",
                    "lead_image": sr["lead_image"] or "",
                    "confidence10": float(sr["confidence10"] or 5.0),
                    "band": b_code,
                    "band_label": BAND_LABEL.get(b_code, b_code),
                    "independent_families": int(sr["independent_families"] or 1),
                    "update_count": int(sr["update_count"] or len(upds)),
                    "unread_updates": int(sr["unread_updates"] or 0),
                    "status": sr["status"] or "active",
                    "created_at": float(sr["created_at"] or 0.0),
                    "updated_at": float(sr["updated_at"] or 0.0),
                    "last_synthesized_at": float(sr["last_synthesized_at"] or 0.0),
                    "updates": upds[:25],
                }
            )
        return {"ok": True, "stories": stories_out}
