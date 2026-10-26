"""
Satz v0.3 Local Model Sidecar (stdlib http.server on 127.0.0.1:8020).

Imports Planck 3.0 and local readers/Gemma from the sibling read-only `../sgs`
repository without modifying `../sgs` or adding new Python dependencies.

Endpoints:
    GET  /health                     Model states + ingest queue status
    POST /chat                       Gemma 4 E4B SSE streaming chat over checked sources
    POST /answer                     Planck 3.0 web search -> read -> weigh -> write
    POST /read                       Hertz / Planck cross-reader over conversation sources
    POST /ingest                     Extract main text (DOM html or Web.fetch fallback) + queue KB ingest
    GET  /digest                     "For you" items from the Satz-owned Planck Store
    GET  /knowledge                  Knowledge base summary (domains, topics, passages, pause state)
    POST /knowledge/pause            Toggle pause_learning
    POST /knowledge/delete_passage   Delete a single passage from the store
    POST /forget                     Delete all passages and cached sources for a conversation_id
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def resolve_default_store_path() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "com.satz.browser" / "planck_store.sqlite"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "com.satz.browser" / "planck_store.sqlite"
    return Path.home() / ".local" / "share" / "com.satz.browser" / "planck_store.sqlite"


NON_FACTUAL_PATTERNS = re.compile(
    r"^\s*(?:hi|hello|hey|yo|thanks|thank you|ok|okay|cool|great|good morning|good evening|"
    r"how are you|who are you|what can you do|help\b|write a poem|write code|brainstorm|"
    r"tell me a joke|translate\b|rewrite\b|draft an email|summarize everything)\b",
    re.I,
)

FACTUAL_CUE_PATTERNS = re.compile(
    r"\b(?:what|when|where|who|whom|which|how many|how much|how old|how tall|how long|"
    r"how far|how big|how fast|in what year|what year|what date|capital|founded|founder|"
    r"ceo|president|population|price|cost|height|born|died|headquarters|located|score|winner)\b",
    re.I,
)


def is_factual_question(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) < 4:
        return False
    if NON_FACTUAL_PATTERNS.search(t):
        return False
    if FACTUAL_CUE_PATTERNS.search(t):
        return True
    if t.endswith("?") and len(t.split()) >= 3:
        return True
    return False


class SatzSidecarRuntime:
    def __init__(
        self,
        sgs_root: Path,
        store_path: Path,
        gemma_rel_path: str = "models/gemma-4-e4b-it",
        open_tab_char_budget: int = 14000,
        total_context_char_budget: int = 32000,
    ):
        self.sgs_root = sgs_root.resolve()
        self.store_path = store_path.resolve()
        self.gemma_rel_path = gemma_rel_path
        self.open_tab_char_budget = open_tab_char_budget
        self.total_context_char_budget = total_context_char_budget

        sidecar_dir = str(Path(__file__).resolve().parent)
        if sidecar_dir not in sys.path:
            sys.path.insert(0, sidecar_dir)
        if str(self.sgs_root) not in sys.path:
            sys.path.insert(0, str(self.sgs_root))

        from satz_brain import SatzBrain
        from satz_passwords import ProfilePasswordManager

        # Import SGS modules after adding sgs_root to sys.path
        from src.planck3.store import Store
        from src.planck3.util import load_env
        from src.planck3.web import Web, WebCache

        orig_cwd = os.getcwd()
        try:
            os.chdir(self.sgs_root)
            load_env()
        finally:
            os.chdir(orig_cwd)

        self.store_lock = threading.RLock()
        self.model_lock = threading.RLock()

        self.store = Store(self.store_path)
        self.passwords = ProfilePasswordManager(self.store_path.parent)
        self.brain = SatzBrain(self.passwords.get_profile_brain_dir())
        self._init_satz_tables()

        sgs_cache_dir = self.sgs_root / "data" / "planck3_cache"
        cache_dir = sgs_cache_dir if sgs_cache_dir.exists() else (self.store_path.parent / "web_cache")
        self.web = Web(WebCache(cache_dir, mode="live"), search_backend="ddgs")
        if os.environ.get("BRAVE_API_KEY"):
            self.web.backend = "brave"
            self.web.secondary = ["ddgs"]

        # Model states and lazy instances
        self.gemma_tok = None
        self.gemma_model = None
        self.gemma_loading = False

        self.answerer = None
        self.answer_sessions: dict[str, Any] = {}
        self.planck3_loading = False

        self.readers: dict[str, Any] = {}
        self.reader_loading: dict[str, bool] = {"hertz (reader)": False, "planck (reader)": False}

        # Background ingest worker & continuous bookmark indexer
        self.ingest_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.pause_learning = self._load_pause_learning()
        self.bookmark_wake_event = threading.Event()
        self.bookmark_Refresh_interval_secs = 180.0
        self.worker_thread = threading.Thread(target=self._ingest_worker_loop, daemon=True)
        self.worker_thread.start()
        self.bookmark_thread = threading.Thread(target=self._bookmark_indexer_loop, daemon=True)
        self.bookmark_thread.start()

    def _refresh_active_profile_brain(self) -> None:
        from satz_brain import SatzBrain

        self.brain = SatzBrain(self.passwords.get_profile_brain_dir())

    def _init_satz_tables(self):
        with self.store_lock:
            self.store.db.executescript(
                """
                CREATE TABLE IF NOT EXISTS satz_sources (
                    source_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    title TEXT NOT NULL,
                    text TEXT NOT NULL,
                    extra_json TEXT,
                    capture_mode TEXT NOT NULL DEFAULT 'dom',
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_satz_sources_conv ON satz_sources(conversation_id);
                CREATE INDEX IF NOT EXISTS idx_satz_sources_url ON satz_sources(url);

                CREATE TABLE IF NOT EXISTS satz_conv_passages (
                    conversation_id TEXT NOT NULL,
                    text_norm TEXT NOT NULL,
                    url TEXT NOT NULL,
                    PRIMARY KEY (conversation_id, text_norm)
                );

                CREATE TABLE IF NOT EXISTS satz_domain_visits (
                    domain TEXT PRIMARY KEY,
                    visits INTEGER NOT NULL DEFAULT 0,
                    dwell_seconds REAL NOT NULL DEFAULT 0.0,
                    last_visited REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS satz_bookmarks (
                    bookmark_id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    title TEXT NOT NULL,
                    last_indexed_at REAL NOT NULL DEFAULT 0.0,
                    text_chars INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending'
                );

                CREATE TABLE IF NOT EXISTS satz_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            # Purge any historical source rows where unclosed <style> blocks polluted trafilatura fallback with raw CSS
            self.store.db.execute(
                "DELETE FROM satz_sources WHERE text LIKE '%.J-J5-Ji{%' OR text LIKE '%{position:relative;display:%'"
            )
            self.store.db.commit()

    def _load_pause_learning(self) -> bool:
        with self.store_lock:
            row = self.store.db.execute(
                "SELECT value FROM satz_meta WHERE key = 'pause_learning'"
            ).fetchone()
            return bool(row and row["value"] == "1")

    def set_pause_learning(self, paused: bool) -> bool:
        self.pause_learning = bool(paused)
        with self.store_lock:
            self.store.db.execute(
                "INSERT OR REPLACE INTO satz_meta (key, value) VALUES ('pause_learning', ?)",
                ("1" if self.pause_learning else "0",),
            )
            self.store.db.commit()
        if self.pause_learning:
            while not self.ingest_queue.empty():
                try:
                    self.ingest_queue.get_nowait()
                    self.ingest_queue.task_done()
                except queue.Empty:
                    break
        return self.pause_learning

    # ── Checkpoint resolution ────────────────────────────────────────────
    def _gemma_dir(self) -> Path:
        p = Path(self.gemma_rel_path)
        return p if p.is_absolute() else (self.sgs_root / p)

    def _hertz_reader_ckpt(self) -> Path | None:
        for rel in (
            "checkpoints/xreader_hertz_rc/reader.pt",
            "checkpoints/xreader_hertz/reader.pt",
            "checkpoints/xreader_hertz_r7/reader.pt",
        ):
            cand = self.sgs_root / rel
            if cand.exists():
                return cand
        return None

    def _planck_reader_ckpt(self) -> Path | None:
        for rel in (
            "checkpoints/xreader_planck_rc/reader.pt",
            "checkpoints/xreader_planck_p15rc/reader.pt",
            "checkpoints/xreader_planck/reader.pt",
            "checkpoints/xreader_planck_r7/reader.pt",
        ):
            cand = self.sgs_root / rel
            if cand.exists():
                return cand
        return None

    def get_health(self) -> dict[str, Any]:
        gemma_dir = self._gemma_dir()
        hertz_ckpt = self._hertz_reader_ckpt()
        planck_ckpt = self._planck_reader_ckpt()

        def gemma_status():
            if self.gemma_model is not None:
                return {"id": "gemma-4-e4b", "state": "ready", "detail": str(gemma_dir.name)}
            if self.gemma_loading:
                return {"id": "gemma-4-e4b", "state": "loading", "detail": "loading into GPU..."}
            if gemma_dir.exists():
                return {"id": "gemma-4-e4b", "state": "not_loaded", "detail": str(gemma_dir.name)}
            return {"id": "gemma-4-e4b", "state": "missing", "detail": f"missing {gemma_dir}"}

        def planck3_status():
            if self.answerer is not None:
                return {"id": "planck3 (web)", "state": "ready", "detail": "x-hertz + template"}
            if self.planck3_loading:
                return {"id": "planck3 (web)", "state": "loading", "detail": "loading pipeline..."}
            if hertz_ckpt is not None:
                return {"id": "planck3 (web)", "state": "not_loaded", "detail": "hertz int8 + template"}
            return {"id": "planck3 (web)", "state": "missing", "detail": "missing reader checkpoint"}

        def reader_status(model_id: str, ckpt: Path | None):
            if model_id in self.readers:
                return {"id": model_id, "state": "ready", "detail": ckpt.parent.name if ckpt else "loaded"}
            if self.reader_loading.get(model_id):
                return {"id": model_id, "state": "loading", "detail": "loading reader..."}
            if ckpt is not None and ckpt.exists():
                return {"id": model_id, "state": "not_loaded", "detail": f"{ckpt.parent.name}/reader.pt"}
            return {"id": model_id, "state": "missing", "detail": f"missing {model_id} checkpoint"}

        return {
            "online": True,
            "models": [
                gemma_status(),
                planck3_status(),
                reader_status("hertz (reader)", hertz_ckpt),
                reader_status("planck (reader)", planck_ckpt),
            ],
            "ingest_queue_len": self.ingest_queue.qsize(),
            "pause_learning": self.pause_learning,
        }

    # ── Lazy Model Loaders ───────────────────────────────────────────────
    def ensure_gemma(self):
        if self.gemma_model is not None:
            return self.gemma_tok, self.gemma_model
        with self.model_lock:
            if self.gemma_model is not None:
                return self.gemma_tok, self.gemma_model
            gemma_dir = self._gemma_dir()
            if not gemma_dir.exists():
                raise RuntimeError(f"Gemma checkpoint not found at {gemma_dir}")
            self.gemma_loading = True
            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer

                print(f"[satz-sidecar] loading Gemma 4 E4B from {gemma_dir} ...", flush=True)
                tok = AutoTokenizer.from_pretrained(str(gemma_dir))
                model = AutoModelForCausalLM.from_pretrained(
                    str(gemma_dir),
                    dtype=torch.bfloat16,
                    device_map="auto" if torch.cuda.is_available() else None,
                )
                model.eval()
                self.gemma_tok = tok
                self.gemma_model = model
                return self.gemma_tok, self.gemma_model
            finally:
                self.gemma_loading = False

    def ensure_reader(self, model_id: str):
        if model_id in self.readers:
            return self.readers[model_id]
        with self.model_lock:
            if model_id in self.readers:
                return self.readers[model_id]
            self.reader_loading[model_id] = True
            try:
                from src.planck3.xreader import CrossReader

                if model_id == "hertz (reader)":
                    ckpt = self._hertz_reader_ckpt()
                    if not ckpt:
                        raise RuntimeError("Hertz reader checkpoint missing")
                else:
                    ckpt = self._planck_reader_ckpt()
                    if not ckpt:
                        raise RuntimeError("Planck reader checkpoint missing")

                orig_cwd = os.getcwd()
                try:
                    os.chdir(self.sgs_root)
                    # Section 4.3: Gemma on GPU, readers on CPU with int8 so both fit at once
                    reader = CrossReader(
                        str(ckpt),
                        device="cpu",
                        quant="int8",
                        max_cands=16,
                    )
                finally:
                    os.chdir(orig_cwd)
                self.readers[model_id] = reader
                return reader
            finally:
                self.reader_loading[model_id] = False

    def ensure_answerer(self):
        if self.answerer is not None:
            return self.answerer
        with self.model_lock:
            if self.answerer is not None:
                return self.answerer
            self.planck3_loading = True
            try:
                from src.planck3.answer import Answerer
                from src.planck3.writer import TemplateWriter

                reader = self.ensure_reader("hertz (reader)")
                writer = TemplateWriter()
                self.answerer = Answerer(self.web, self.store, reader, writer)
                return self.answerer
            finally:
                self.planck3_loading = False

    # ── Ingest & Background Knowledge Base ───────────────────────────────
    def ingest_page(
        self,
        conversation_id: str,
        source_id: str,
        url: str,
        title: str,
        html: str | None,
        dwell_seconds: float = 0.0,
        visible_text: str | None = None,
    ) -> dict[str, Any]:
        from src.planck3.web import domain_of, extract_jsonld, extract_main_text

        domain = domain_of(url) if url else ""
        capture_mode = "dom"
        text = ""
        extra_lines: list[str] = []

        clean_visible = ""
        if visible_text and visible_text.strip():
            # Preserve line structure for web apps / email clients / tables while collapsing blank runs
            lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in visible_text.splitlines()]
            non_empty = [ln for ln in lines if ln]
            clean_visible = "\n".join(non_empty)[:120000]

        trafilatura_text = ""
        if html and html.strip():
            raw_traf = extract_main_text(html, url) or ""
            # Guard against unclosed <style> blocks in truncated SPA outerHTML producing raw CSS
            if raw_traf.count("{") > 25 and raw_traf.count("}") > 25 and (
                len(raw_traf) / max(1, raw_traf.count("{")) < 180
            ):
                trafilatura_text = ""
            else:
                trafilatura_text = raw_traf
            extra_lines = extract_jsonld(html)

        # Authenticated web apps (e.g. mail.google.com, dashboards, SPAs) always have their live
        # visible text captured directly from the WebView2 DOM (`clean_visible`). Always place
        # `clean_visible` first so CSS or boilerplate from `html` never pushes live tab rows out.
        if clean_visible and trafilatura_text:
            if len(clean_visible) >= 200:
                text = f"{clean_visible}\n\n{trafilatura_text}"[:120000]
            else:
                text = f"{clean_visible}\n\n{trafilatura_text}"[:120000]
        elif clean_visible:
            text = clean_visible
        elif trafilatura_text:
            text = trafilatura_text

        # Only fall back to unauthenticated python web.fetch if no DOM html or visible_text was provided
        if not text and not html and not clean_visible and url and url.startswith(("http://", "https://")):
            capture_mode = "fetch"
            page = self.web.fetch(url)
            if page.get("html"):
                text = extract_main_text(page["html"], url)
                extra_lines = extract_jsonld(page["html"])

        effective_title = (title or domain or url or "untitled").strip()
        now = time.time()

        with self.store_lock:
            if source_id:
                # Never overwrite non-empty authenticated DOM text with an empty capture
                if not text:
                    existing = self.store.db.execute(
                        "SELECT text FROM satz_sources WHERE source_id = ?",
                        (source_id,),
                    ).fetchone()
                    if existing and existing["text"]:
                        text = existing["text"]

                self.store.db.execute(
                    """
                    INSERT OR REPLACE INTO satz_sources
                    (source_id, conversation_id, url, domain, title, text, extra_json, capture_mode, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        conversation_id or "default",
                        url,
                        domain,
                        effective_title,
                        text,
                        json.dumps(extra_lines, ensure_ascii=False),
                        capture_mode,
                        now,
                    ),
                )
            if domain:
                self.store.db.execute(
                    """
                    INSERT INTO satz_domain_visits (domain, visits, dwell_seconds, last_visited)
                    VALUES (?, 1, ?, ?)
                    ON CONFLICT(domain) DO UPDATE SET
                        visits = visits + 1,
                        dwell_seconds = dwell_seconds + excluded.dwell_seconds,
                        last_visited = excluded.last_visited
                    """,
                    (domain, float(dwell_seconds or 0.0), now),
                )
            self.store.db.commit()

        queued = False
        if not self.pause_learning and text and len(text) >= 20:
            self.ingest_queue.put(
                {
                    "conversation_id": conversation_id or "default",
                    "source_id": source_id,
                    "url": url,
                    "domain": domain,
                    "title": effective_title,
                    "text": text,
                }
            )
            queued = True

        return {
            "ok": True,
            "source_id": source_id,
            "capture_mode": capture_mode,
            "text_chars": len(text),
            "queued": queued,
            "queue_len": self.ingest_queue.qsize(),
        }

    def _ingest_worker_loop(self):
        from src.planck3.candidates import main_entity, rank_passages
        from src.planck3.util import norm_text

        while True:
            item = self.ingest_queue.get()
            try:
                if self.pause_learning:
                    continue
                url = item["url"]
                domain = item["domain"]
                title = item["title"]
                text = item["text"]
                conv_id = item["conversation_id"]

                # 1. Enrich the Satz Brain knowledge graph (accounts, entities, domains)
                try:
                    self.brain.enrich_from_page(
                        url=url,
                        domain=domain,
                        title=title,
                        text=text,
                        conversation_id=conv_id,
                    )
                except Exception as be:
                    print(f"[satz-sidecar] brain enrich error: {be}", flush=True)

                entity = main_entity(title) or title[:60]
                query_str = f"{title} {domain}".strip()

                with self.store_lock:
                    trust = self.store.domain_prior(domain) if domain else 0.5
                    doc = {
                        "url": url,
                        "domain": domain,
                        "title": title,
                        "trust": trust,
                        "text": text,
                    }
                    passages = rank_passages(query_str, [doc], k=6, per_source=6, min_score=0.1)
                    if not passages and text:
                        # Keep lead sentences if rank_passages found no high-IDF query match
                        from src.planck3.candidates import split_sentences

                        sents = [s for s in split_sentences(text) if len(s) >= 25][:6]
                        passages = [
                            {
                                "text": s[:420],
                                "url": url,
                                "domain": domain,
                                "title": title,
                                "trust": trust,
                                "score": 0.5,
                            }
                            for s in sents
                        ]
                    if passages:
                        self.store.log_query(title, entity)
                        self.store.add_passages(passages, entity, f"[conv:{conv_id}] {title}")
                        for p in passages:
                            self.store.db.execute(
                                "INSERT OR IGNORE INTO satz_conv_passages (conversation_id, text_norm, url) VALUES (?, ?, ?)",
                                (conv_id, norm_text(p["text"]), url),
                            )
                        self.store.db.commit()
            except Exception as e:
                print(f"[satz-sidecar] ingest worker error: {e}", flush=True)
            finally:
                self.ingest_queue.task_done()

    # ── Continuous Background Bookmark Indexer ───────────────────────────
    def sync_bookmarks(self, bookmarks: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Syncs the active bookmark list into `satz_bookmarks` and wakes the background
        bookmark indexer so bookmarked sources are continuously indexed and updated.
        """
        from src.planck3.web import domain_of

        incoming_ids: set[str] = set()
        with self.store_lock:
            for b in bookmarks or []:
                bid = str(b.get("id") or "").strip()
                url = str(b.get("url") or "").strip()
                title = str(b.get("title") or url).strip()
                if not bid or not url:
                    continue
                if not url.startswith(("http://", "https://")):
                    url = f"https://{url}"
                incoming_ids.add(bid)
                dom = domain_of(url) or url
                self.store.db.execute(
                    """
                    INSERT INTO satz_bookmarks (bookmark_id, url, domain, title, last_indexed_at, text_chars, status)
                    VALUES (?, ?, ?, ?, 0.0, 0, 'queued')
                    ON CONFLICT(bookmark_id) DO UPDATE SET
                        url = excluded.url,
                        domain = excluded.domain,
                        title = excluded.title
                    """,
                    (bid, url, dom, title),
                )
            if incoming_ids:
                placeholders = ",".join("?" for _ in incoming_ids)
                self.store.db.execute(
                    f"DELETE FROM satz_bookmarks WHERE bookmark_id NOT IN ({placeholders})",
                    tuple(incoming_ids),
                )
            else:
                self.store.db.execute("DELETE FROM satz_bookmarks")
            self.store.db.commit()

        self.bookmark_wake_event.set()
        return {"ok": True, "bookmarks_count": len(incoming_ids)}

    def get_bookmarks_status(self) -> list[dict[str, Any]]:
        with self.store_lock:
            rows = self.store.db.execute(
                "SELECT bookmark_id, url, domain, title, last_indexed_at, text_chars, status FROM satz_bookmarks ORDER BY last_indexed_at DESC"
            ).fetchall()
            return [
                {
                    "id": r["bookmark_id"],
                    "url": r["url"],
                    "domain": r["domain"],
                    "title": r["title"],
                    "last_indexed_at": float(r["last_indexed_at"] or 0.0),
                    "text_chars": int(r["text_chars"] or 0),
                    "status": r["status"],
                }
                for r in rows
            ]

    def _bookmark_indexer_loop(self):
        from src.planck3.web import domain_of, extract_main_text

        while True:
            self.bookmark_wake_event.wait(timeout=30.0)
            self.bookmark_wake_event.clear()
            if self.pause_learning:
                continue

            try:
                now = time.time()
                with self.store_lock:
                    rows = self.store.db.execute(
                        "SELECT bookmark_id, url, domain, title, last_indexed_at FROM satz_bookmarks"
                    ).fetchall()

                for r in rows:
                    if self.pause_learning:
                        break
                    bid = r["bookmark_id"]
                    url = r["url"]
                    dom = r["domain"] or domain_of(url)
                    title = r["title"] or dom or url
                    last_ts = float(r["last_indexed_at"] or 0.0)

                    # Re-index immediately if never indexed (last_ts == 0) or older than refresh interval
                    if last_ts > 0 and (now - last_ts) < self.bookmark_Refresh_interval_secs:
                        continue

                    extracted_text = ""
                    extracted_html = None

                    # 1. If the active profile is unlocked and has .env credentials for this bookmark, use them!
                    try:
                        auth_res = self.passwords.extract_with_profile_credentials(url)
                        if auth_res:
                            if auth_res.get("text"):
                                extracted_text = str(auth_res["text"])
                            if auth_res.get("html"):
                                extracted_html = str(auth_res["html"])
                                main_t = extract_main_text(extracted_html, url)
                                if main_t:
                                    extracted_text = f"{extracted_text}\n\n{main_t}".strip() if extracted_text else main_t
                    except Exception as ae:
                        print(f"[satz-sidecar] bookmark auth extract note for {url}: {ae}", flush=True)

                    # 2. Check if there is fresh DOM text captured from a live tab for this URL
                    if not extracted_text:
                        with self.store_lock:
                            src_row = self.store.db.execute(
                                "SELECT text FROM satz_sources WHERE url = ? AND capture_mode = 'dom' ORDER BY updated_at DESC LIMIT 1",
                                (url,),
                            ).fetchone()
                            if src_row and src_row["text"]:
                                extracted_text = src_row["text"]

                    # 3. Otherwise fetch the live page in the background
                    if not extracted_text and url.startswith(("http://", "https://")):
                        page = self.web.fetch(url)
                        if page.get("html"):
                            extracted_html = page["html"]
                            extracted_text = extract_main_text(extracted_html, url) or ""

                    res = self.ingest_page(
                        conversation_id="bookmarks",
                        source_id=f"bookmark:{bid}",
                        url=url,
                        title=f"[Bookmark] {title}",
                        html=extracted_html,
                        visible_text=extracted_text or None,
                    )
                    chars = int(res.get("text_chars") or len(extracted_text))
                    status_str = "indexed" if chars > 0 else "empty"

                    with self.store_lock:
                        self.store.db.execute(
                            "UPDATE satz_bookmarks SET last_indexed_at = ?, text_chars = ?, status = ? WHERE bookmark_id = ?",
                            (time.time(), chars, status_str, bid),
                        )
                        self.store.db.commit()
            except Exception as e:
                print(f"[satz-sidecar] bookmark indexer error: {e}", flush=True)

    def get_source_text(self, source_id: str, url: str, title: str = "") -> tuple[str, list[str]]:
        with self.store_lock:
            row = None
            if source_id:
                row = self.store.db.execute(
                    "SELECT text, extra_json FROM satz_sources WHERE source_id = ?",
                    (source_id,),
                ).fetchone()
            if (row is None or not row["text"]) and url:
                row = self.store.db.execute(
                    "SELECT text, extra_json FROM satz_sources WHERE url = ? ORDER BY updated_at DESC LIMIT 1",
                    (url,),
                ).fetchone()
            if row and row["text"]:
                extra = json.loads(row["extra_json"] or "[]")
                return row["text"], extra

        # Fallback: fetch live if not yet captured
        if url and url.startswith(("http://", "https://")):
            self.ingest_page("default", source_id or url, url, title, None)
            with self.store_lock:
                row = self.store.db.execute(
                    "SELECT text, extra_json FROM satz_sources WHERE url = ? ORDER BY updated_at DESC LIMIT 1",
                    (url,),
                ).fetchone()
                if row and row["text"]:
                    return row["text"], json.loads(row["extra_json"] or "[]")
        return "", []

    # ── /answer (Planck 3.0 web pipeline) ────────────────────────────────
    def run_answer(self, question: str, session_id: str = "default") -> dict[str, Any]:
        from src.planck3.candidates import main_entity
        from src.planck3.chat import ChatSession, chat_answer

        answerer = self.ensure_answerer()
        orig_cwd = os.getcwd()
        try:
            os.chdir(self.sgs_root)
            with self.store_lock:
                sess = self.answer_sessions.setdefault(session_id, ChatSession(answerer))
                turn = sess.ask(question)
                if not self.pause_learning:
                    self.store.log_query(turn.question, main_entity(turn.question))
        finally:
            os.chdir(orig_cwd)

        res = turn.result
        ex = res.get("explain") or {}
        band_label = ex.get("band_label") or ex.get("band") or res.get("tier") or "none"
        conf10 = ex.get("confidence10")
        band_str = f"{conf10:.1f}/10 ({band_label})" if conf10 is not None else str(band_label)

        raw_sources = (res.get("depth") or {}).get("sources") or ex.get("sources") or []
        seen_urls: set[str] = set()
        sources_out = []
        for s in raw_sources:
            u = s.get("url")
            if not u or u in seen_urls:
                continue
            seen_urls.add(u)
            sources_out.append(
                {
                    "url": u,
                    "title": s.get("title") or s.get("domain") or u,
                    "domain": s.get("domain") or "",
                }
            )
            if len(sources_out) >= 6:
                break

        return {
            "answer": res.get("answer_text") or chat_answer(turn),
            "value": res.get("value"),
            "band": band_str,
            "confidence10": conf10,
            "sources": sources_out,
            "explain": ex,
        }

    # ── /read (Hertz / Planck cross-reader over conversation sources) ────
    def run_read(
        self,
        model_id: str,
        question: str,
        sources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        short_name = "hertz" if "hertz" in model_id else "planck"
        if not is_factual_question(question):
            return {
                "answer": f"{short_name} reads facts from sources; switch to gemma for chat",
                "source_ids": [],
            }
        if not sources:
            return {
                "answer": f"no checked sources in context for {short_name} to read. open a tab or check a source.",
                "source_ids": [],
            }

        from src.planck3.candidates import span_candidates
        from src.planck3.chat import infer_answer_type
        from src.planck3.consolidate import consolidate
        from src.planck3.qtype import classify
        from src.planck3.web import domain_of

        reader = self.ensure_reader(model_id)
        at = infer_answer_type(question)
        qt = classify(question)

        pools = []
        url_to_source_id: dict[str, str] = {}
        url_to_idx: dict[str, int] = {}

        for idx, src in enumerate(sources, 1):
            sid = str(src.get("id") or f"src-{idx}")
            url = str(src.get("url") or f"local://source-{idx}")
            title = str(src.get("title") or url)
            url_to_source_id[url] = sid
            url_to_idx[url] = idx

            text, extra_lines = self.get_source_text(sid, url, title)
            if not text and src.get("text"):
                text = str(src["text"])
            if not text:
                continue
            cands = span_candidates(question, text, at, url=url, extra_lines=extra_lines)
            if cands:
                pool = {"name": f"page:{domain_of(url) or idx}", "cands": cands, "snippet": False}
                pool["r"] = reader.read(question, at, pool)
                pools.append(pool)

        if not pools:
            return {
                "answer": f"could not find a candidate {at} answer in the {len(sources)} checked source(s).",
                "source_ids": [str(s.get("id", "")) for s in sources],
            }

        with self.store_lock:
            cons = consolidate(pools, at, qt, lambda dom: self.store.trust(dom))

        if cons.get("value") is None:
            return {
                "answer": f"no confident answer found in the checked sources ({cons.get('band_label', 'none')}).",
                "source_ids": [str(s.get("id", "")) for s in sources],
            }

        val = cons["value"]
        conf = cons.get("confidence", 0.0)
        band_label = cons.get("band_label", "")
        fams = cons.get("families") or []
        cites = []
        used_source_ids = [str(s.get("id", "")) for s in sources]
        for f in fams[:2]:
            u = f.get("url", "")
            cite_num = url_to_idx.get(u, 1)
            cites.append(f"{f.get('domain') or 'source'} [{cite_num}]")

        cite_str = ", ".join(cites) if cites else "[1]"
        context_snip = fams[0].get("context", "") if fams else ""
        answer_str = f"{val} (according to {cite_str}, confidence {conf:.1f}/10 {band_label})."
        if context_snip:
            answer_str += f'\n"{context_snip}"'

        return {
            "answer": answer_str,
            "source_ids": used_source_ids,
        }

    # ── /chat Context Assembly & Streaming with Gemma 4 E4B ──────────────
    def assemble_chat_context(
        self,
        question: str,
        sources: list[dict[str, Any]],
    ) -> tuple[str, list[str], list[dict[str, Any]]]:
        """
        Assembles context from:
        1. Open authenticated browser tabs in full (up to open_tab_char_budget each)
        2. Additional web/checked sources (best 3 passages each)
        3. Relevant historical passages from the local Planck SQLite store
        Returns (context_str, used_source_ids, hydrated_sources).
        """
        from src.planck3.candidates import rank_passages, split_sentences
        from src.planck3.util import norm_text
        from src.planck3.web import domain_of, query_keys

        keys = query_keys(question)
        total_chars = 0
        blocks: list[str] = []
        used_source_ids: list[str] = []
        hydrated_sources: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for src in sources:
            if total_chars >= self.total_context_char_budget:
                break
            sid = str(src.get("id") or "")
            url = str(src.get("url") or "")
            title = str(src.get("title") or url)
            domain = str(src.get("domain") or domain_of(url) or "source")
            is_open_tab = bool(src.get("is_open_tab", True))

            text = str(src.get("text") or "")
            if not text:
                text, _ = self.get_source_text(sid, url, title)
            if not text:
                continue

            if url:
                seen_urls.add(url)

            remaining = self.total_context_char_budget - total_chars
            if is_open_tab:
                snippet = text[: min(self.open_tab_char_budget, remaining)]
            else:
                doc = {"url": url, "domain": domain, "title": title, "trust": 0.7, "text": text}
                ranked = rank_passages(question, [doc], k=3, per_source=3, min_score=0.05)
                if ranked:
                    snippet = "\n".join(p["text"] for p in ranked)
                else:
                    sents = split_sentences(text)
                    if keys:
                        scored = sorted(
                            sents,
                            key=lambda s: sum(1 for k in keys if k in norm_text(s).split()),
                            reverse=True,
                        )
                        snippet = "\n".join(scored[:3])
                    else:
                        snippet = "\n".join(sents[:3])
                snippet = snippet[: min(2400, remaining)]

            if not snippet.strip():
                continue

            cite_num = len(used_source_ids) + 1
            used_source_ids.append(sid)
            hydrated_sources.append(
                {
                    "id": sid,
                    "url": url,
                    "title": title,
                    "domain": domain,
                    "text": snippet,
                    "is_open_tab": is_open_tab,
                }
            )
            tab_tag = "LIVE OPEN BROWSER TAB" if is_open_tab else "WEB SOURCE"
            block = f"[{cite_num}] ({tab_tag}) {domain} ({title}) - {url}\n{snippet}"
            blocks.append(block)
            total_chars += len(block)

        # 2. If active profile is unlocked, check if stored .env credentials can extract live data for the query or open tabs
        if question and self.passwords.unlocked:
            targets_to_check = [question] + [str(s.get("url") or "") for s in sources if s.get("url")]
            checked_services: set[str] = set()
            for tgt in targets_to_check:
                if not tgt:
                    continue
                creds = self.passwords.find_credentials_for_target(tgt)
                if not creds or creds["service"] in checked_services:
                    continue
                checked_services.add(creds["service"])
                try:
                    auth_data = self.passwords.extract_with_profile_credentials(tgt)
                    if auth_data and auth_data.get("text"):
                        blocks.append(
                            f"[PROFILE .ENV CREDENTIAL EXTRACTION - {auth_data['service']} ({auth_data.get('username', '')})]\n"
                            f"{str(auth_data['text'])[:4000]}"
                        )
                except Exception as pe:
                    print(f"[satz-sidecar] profile credential extraction note: {pe}", flush=True)

        # 3. Also pull relevant passages from persistent SQLite knowledge store & continuously-indexed bookmarks
        if question and total_chars < self.total_context_char_budget - 1000:
            kb_lines: list[str] = []
            try:
                with self.store_lock:
                    stored_hits = self.store.local_passages(question, k=4)
                    bm_rows = self.store.db.execute(
                        "SELECT url, domain, title, text FROM satz_sources WHERE source_id LIKE 'bookmark:%' ORDER BY updated_at DESC LIMIT 12"
                    ).fetchall()
                for hp in stored_hits:
                    hurl = str(hp.get("url") or "")
                    htext = str(hp.get("text") or "").strip()
                    if not htext or (hurl and hurl in seen_urls):
                        continue
                    hdom = str(hp.get("domain") or domain_of(hurl) or "local")
                    htitle = str(hp.get("title") or hurl)
                    kb_lines.append(f"- ({hdom} · {htitle}): {htext}")
                for bmr in bm_rows:
                    burl = str(bmr["url"] or "")
                    btext = str(bmr["text"] or "").strip()
                    if not btext or (burl and burl in seen_urls):
                        continue
                    bdom = str(bmr["domain"] or domain_of(burl) or "bookmark")
                    btitle = str(bmr["title"] or burl)
                    if any(k in norm_text(f"{btitle} {bdom} {btext[:600]}") for k in keys) or bdom.lower() in question.lower():
                        kb_lines.append(f"- (BOOKMARK INDEXED: {bdom} · {btitle} - {burl}): {btext[:600]}")
            except Exception as kbe:
                print(f"[satz-sidecar] local_passages lookup note: {kbe}", flush=True)
            if kb_lines:
                blocks.append("STORED PASSAGES & CONTINUOUSLY INDEXED BOOKMARKS:\n" + "\n".join(kb_lines[:6]))

        return "\n\n".join(blocks), used_source_ids, hydrated_sources

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        sources: list[dict[str, Any]],
        web_enabled: bool = False,
    ):
        """Generator yielding SSE dicts: {'delta': ...} then {'done': True, 'source_ids': [...], 'ms': ...}."""
        from src.planck3.candidates import main_entity
        from src.planck3.web import domain_of

        t0 = time.perf_counter()
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = str(m.get("content") or "").strip()
                break

        if user_msg and not self.pause_learning:
            with self.store_lock:
                self.store.log_query(user_msg, main_entity(user_msg))

        combined_sources = list(sources)
        cited_web_sources: list[dict[str, str]] = []

        # Avoid running a generic public web search when the user is asking about
        # their open tab / email / account / inbox / page or asking to summarize / store something.
        has_mail_or_app_tab = any(
            any(
                tok in str(s.get("url") or "").lower() or tok in str(s.get("domain") or "").lower()
                for tok in ("mail.google.com", "gmail", "outlook", "proton.me", "calendar.google.com")
            )
            for s in combined_sources
        )
        is_personal_or_tab_query = bool(
            has_mail_or_app_tab
            or re.search(
                r"\b(my\s+(?:latest\s+)?(?:email|inbox|mail|account|calendar|messages|address|tab|page)|"
                r"(?:latest|newest|recent|unread|first|last)\s+(?:email|emails|mail|mails|message|messages|thread)|"
                r"(?:summarize|summary|read|check|get\s+me)\s+(?:my\s+|the\s+)?(?:latest\s+|recent\s+)?(?:email|emails|mail|inbox|page|tab|article|thread)|"
                r"this\s+(?:email|page|tab|article|site|screen|message|thread)|"
                r"store\s+the|save\s+the|in\s+the\s+knowledge\s*base|in\s+my\s+brain)\b",
                user_msg,
                re.IGNORECASE,
            )
        )

        # Detect when the user is asking to find/search items on a site (e.g. "find me some hats on zalando")
        is_site_discovery_query = bool(
            re.search(
                r"\b(find\s+(?:me\s+)?|search\s+(?:for\s+)?|look\s+for\s+|show\s+me\s+some\s+)",
                user_msg,
                re.IGNORECASE,
            )
        )

        should_run_web = (web_enabled and not (is_personal_or_tab_query and len(combined_sources) > 0)) or (
            is_site_discovery_query and not is_personal_or_tab_query
        )

        yield {
            "status": f"reading {len(combined_sources)} open tab source(s) & local brain...",
            "phase": "context",
        }

        if should_run_web and user_msg:
            try:
                search_q = user_msg
                if is_site_discovery_query and combined_sources:
                    open_dom = str(combined_sources[0].get("domain") or domain_of(str(combined_sources[0].get("url") or "")) or "")
                    if open_dom and open_dom.split(".")[0].lower() not in user_msg.lower():
                        search_q = f"{open_dom} {user_msg}"
                yield {
                    "status": f"searching web sources for '{search_q[:48]}'...",
                    "phase": "web_search",
                }
                ans = self.run_answer(search_q, session_id="chat-web")
                existing_urls = {s.get("url") for s in combined_sources}
                for ws in ans.get("sources", [])[:3]:
                    wurl = ws.get("url")
                    if wurl and wurl not in existing_urls:
                        existing_urls.add(wurl)
                        combined_sources.append(
                            {
                                "id": wurl,
                                "url": wurl,
                                "title": ws.get("title") or wurl,
                                "domain": ws.get("domain") or "",
                                "is_open_tab": False,
                            }
                        )
                        cited_web_sources.append({"url": wurl, "title": ws.get("title") or wurl})
            except Exception as e:
                print(f"[satz-sidecar] web pre-search failed: {e}", flush=True)
                yield {
                    "status": f"web search warning: {e} (continuing with local tabs)",
                    "phase": "warning",
                }

        context_str, used_source_ids, hydrated_sources = self.assemble_chat_context(user_msg, combined_sources)
        brain_context = self.brain.build_model_context(user_msg, hydrated_sources or combined_sources)

        yield {
            "status": f"assembled {len(used_source_ids)} source(s) ({len(context_str):,} chars) + brain index",
            "phase": "context_ready",
        }

        system_prompt = (
            "You are the local AI assistant inside the Satz browser, connected directly to:\n"
            "1. The user's LIVE OPEN BROWSER TABS (numbered [1], [2], ... in SOURCES), including their authenticated accounts, webmail (e.g. Gmail), and active pages.\n"
            "2. The user's persistent local SATZ BRAIN KNOWLEDGE BASE (BRAIN.md index + entity files on disk).\n\n"
            "CRITICAL RULES:\n"
            "- You HAVE full access to the live content of the user's open tabs in SOURCES and full read/write access to the local Satz Brain knowledge base.\n"
            "- NEVER say 'I am a language model and cannot store information' or 'I do not have a personal knowledge base'.\n"
            "- When the user asks about their emails, inbox, account, or open page (e.g. 'give me my latest email'), read the LIVE OPEN BROWSER TAB in SOURCES [1] directly and give the exact sender, subject, time/snippet, or content shown on the page.\n"
            "- When the user asks to store, save, or remember any information (such as an address on an email, a contact, a person, an account, a project, or a note) into the knowledge base / Brain, confirm clearly what you are storing AND output a <brain_store> JSON block at the very end of your response in this exact format:\n"
            '<brain_store>{"type": "place", "name": "Short Entity Name", "summary": "One-line summary", "attributes": {"address": "...", "email": "..."}, "content": "Full details"}</brain_store>\n'
            "  Valid types: 'place', 'person', 'account', 'organization', 'project', 'note', 'decision'.\n"
            "- Every time you use a fact from a numbered source, cite it inline as [1], [2], etc.\n"
            "- Keep answers concise and never use em dashes."
        )

        prompt_sections: list[str] = []
        if brain_context:
            prompt_sections.append(f"SATZ BRAIN KNOWLEDGE BASE:\n{brain_context}")
        if context_str:
            prompt_sections.append(f"SOURCES (OPEN TABS & RETRIEVED CONTEXT):\n{context_str}")
        prompt_sections.append(f"USER REQUEST: {user_msg}")
        user_prompt = "\n\n".join(prompt_sections)

        chat_msgs: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        prior = [m for m in messages[:-1] if m.get("role") in ("user", "assistant")][-6:]
        for pm in prior:
            chat_msgs.append({"role": pm["role"], "content": str(pm.get("content") or "")})
        chat_msgs.append({"role": "user", "content": user_prompt})

        if self.gemma_model is None:
            yield {
                "status": "loading gemma-4-e4b into GPU memory...",
                "phase": "model_load",
            }
        tok, model = self.ensure_gemma()
        import torch
        from transformers import TextIteratorStreamer

        yield {
            "status": f"running gemma-4-e4b prefill over {len(used_source_ids)} source(s) ({len(context_str):,} chars)...",
            "phase": "generating",
        }

        inputs = tok.apply_chat_template(
            chat_msgs,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        ).to(model.device)

        streamer = TextIteratorStreamer(tok, skip_prompt=True, skip_special_tokens=True)
        gen_kwargs = dict(
            **inputs,
            streamer=streamer,
            max_new_tokens=1024,
            do_sample=False,
        )

        gen_errors: list[str] = []

        def _generate():
            try:
                with torch.no_grad():
                    model.generate(**gen_kwargs)
            except Exception as exc:
                gen_errors.append(str(exc))
                try:
                    streamer.end()
                except Exception:
                    pass

        gen_thread = threading.Thread(target=_generate, daemon=True)
        gen_thread.start()

        full_raw = ""
        emitted_len = 0
        in_brain_tag = False
        first_token_seen = False

        for chunk in streamer:
            if not chunk:
                continue
            if not first_token_seen:
                first_token_seen = True
                yield {
                    "status": "streaming response tokens...",
                    "phase": "streaming",
                }
            cleaned = chunk.replace("\u2014", "-")
            full_raw += cleaned

            if not in_brain_tag:
                tag_pos = full_raw.find("<brain_store")
                if tag_pos != -1:
                    in_brain_tag = True
                    if tag_pos > emitted_len:
                        delta_out = full_raw[emitted_len:tag_pos]
                        emitted_len = tag_pos
                        if delta_out:
                            yield {"delta": delta_out}
                else:
                    # Hold back a small tail in case '<brain_store' is being split across tokens
                    safe_end = max(emitted_len, len(full_raw) - 14)
                    if safe_end > emitted_len:
                        delta_out = full_raw[emitted_len:safe_end]
                        emitted_len = safe_end
                        if delta_out:
                            yield {"delta": delta_out}

        gen_thread.join(timeout=5.0)
        if gen_errors:
            raise RuntimeError(gen_errors[0])

        # Flush any remaining text and execute any <brain_store> directives
        primary_url = str(hydrated_sources[0].get("url") or "") if hydrated_sources else ""
        cleaned_final, stored_entities = self.brain.extract_and_execute_brain_directives(
            full_raw,
            source_url=primary_url,
        )

        if not in_brain_tag and len(full_raw) > emitted_len:
            tail = full_raw[emitted_len:]
            if tail:
                yield {"delta": tail}

        # Guarantee fulfillment if user explicitly asked to store/save/remember something
        if not self.pause_learning:
            stored_entities = self.brain.ensure_explicit_store_fulfilled(
                user_msg=user_msg,
                assistant_msg=cleaned_final,
                sources=hydrated_sources,
                already_stored=stored_entities,
            )

        if stored_entities:
            confirm_lines = [
                f"\n\n[brain: stored {e['type']} '{e['name']}' -> {e['path']}]"
                for e in stored_entities
            ]
            yield {"delta": "".join(confirm_lines)}

        ms = int((time.perf_counter() - t0) * 1000)
        done_payload: dict[str, Any] = {
            "done": True,
            "source_ids": used_source_ids,
            "ms": ms,
        }
        if cited_web_sources:
            done_payload["cited_sources"] = cited_web_sources
        if stored_entities:
            done_payload["stored_entities"] = stored_entities
        yield done_payload

    # ── /digest, /knowledge, /forget ─────────────────────────────────────
    def get_digest(self) -> dict[str, Any]:
        from src.planck3.digest import build_digest

        with self.store_lock:
            raw = build_digest(self.store)
            items = []
            for sec in raw.get("interests", []):
                ent = sec["entity"]
                for p in sec.get("recent", [])[:2]:
                    items.append(
                        {
                            "entity": ent,
                            "reason": f"recent ({p.get('domain', 'local')})",
                            "title": p.get("title") or p.get("text", "")[:80],
                            "url": p.get("url", ""),
                            "domain": p.get("domain", ""),
                        }
                    )
                for adj in sec.get("adjacent", [])[:2]:
                    ap = adj.get("passage")
                    if ap:
                        items.append(
                            {
                                "entity": adj["entity"],
                                "reason": f"adjacent to {ent}",
                                "title": ap.get("title") or ap.get("text", "")[:80],
                                "url": ap.get("url", ""),
                                "domain": ap.get("domain", ""),
                            }
                        )
            if not items:
                rows = self.store.db.execute(
                    "SELECT id, url, domain, title, text, entity FROM passages ORDER BY ts DESC LIMIT 6"
                ).fetchall()
                for r in rows:
                    items.append(
                        {
                            "entity": r["entity"] or r["domain"] or "recent",
                            "reason": f"browsed on {r['domain']}",
                            "title": r["title"] or r["text"][:80],
                            "url": r["url"],
                            "domain": r["domain"],
                        }
                    )
            return {"items": items[:8], "digest": raw}

    def get_knowledge_summary(self) -> dict[str, Any]:
        with self.store_lock:
            dom_rows = self.store.db.execute(
                "SELECT domain, visits, dwell_seconds FROM satz_domain_visits ORDER BY visits DESC, last_visited DESC LIMIT 12"
            ).fetchall()
            top_domains = [
                {
                    "domain": r["domain"],
                    "visits": int(r["visits"]),
                    "dwell_seconds": round(float(r["dwell_seconds"]), 1),
                    "trust": round(self.store.domain_prior(r["domain"]) * 10, 1),
                }
                for r in dom_rows
            ]

            top_topics = [
                {"entity": ent, "score": round(sc, 3)}
                for ent, sc in self.store.interests(12)
            ]

            p_rows = self.store.db.execute(
                "SELECT id, url, domain, title, text, entity, ts FROM passages ORDER BY ts DESC LIMIT 50"
            ).fetchall()
            passages = [
                {
                    "id": str(r["id"]),
                    "url": r["url"],
                    "domain": r["domain"],
                    "title": r["title"],
                    "text": r["text"],
                    "entity": r["entity"],
                    "ts": r["ts"],
                }
                for r in p_rows
            ]

            return {
                "pause_learning": self.pause_learning,
                "queue_len": self.ingest_queue.qsize(),
                "brain": self.brain.get_brain_summary(),
                "bookmarks_indexed": self.get_bookmarks_status(),
                "profile": self.passwords.list_profiles(),
                "vault": self.passwords.get_active_vault_summary(include_raw_env=True),
                "top_domains": top_domains,
                "top_topics": top_topics,
                "passages": passages,
            }

    def delete_passage(self, passage_id: str) -> dict[str, Any]:
        with self.store_lock:
            before = self.store.db.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
            self.store.db.execute("DELETE FROM passages WHERE id = ?", (passage_id,))
            self.store.db.commit()
            after = self.store.db.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
            return {"ok": True, "before": before, "after": after}

    def delete_brain_entity(self, slug: str) -> dict[str, Any]:
        deleted = self.brain.delete_entity(slug)
        return {"ok": deleted, "slug": slug}

    def forget_conversation(self, conversation_id: str) -> dict[str, Any]:
        with self.store_lock:
            before = self.store.db.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
            tag_prefix = f"[conv:{conversation_id}]%"
            self.store.db.execute(
                "DELETE FROM passages WHERE question LIKE ?",
                (tag_prefix,),
            )
            self.store.db.execute(
                """
                DELETE FROM passages
                WHERE text_norm IN (
                    SELECT text_norm FROM satz_conv_passages WHERE conversation_id = ?
                )
                """,
                (conversation_id,),
            )
            self.store.db.execute(
                "DELETE FROM satz_conv_passages WHERE conversation_id = ?",
                (conversation_id,),
            )
            self.store.db.execute(
                "DELETE FROM satz_sources WHERE conversation_id = ?",
                (conversation_id,),
            )
            self.store.db.commit()
            after = self.store.db.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
            return {
                "ok": True,
                "conversation_id": conversation_id,
                "passages_before": before,
                "passages_after": after,
                "deleted": before - after,
            }


def make_sidecar_server(runtime: SatzSidecarRuntime, host: str = "127.0.0.1", port: int = 8020):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send_cors_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def _json(self, obj: Any, code: int = 200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(204)
            self._send_cors_headers()
            self.end_headers()

        def do_GET(self):
            if self.path == "/health":
                return self._json(runtime.get_health())
            if self.path == "/digest":
                return self._json(runtime.get_digest())
            if self.path == "/knowledge":
                return self._json(runtime.get_knowledge_summary())
            if self.path == "/profile/status":
                return self._json(runtime.passwords.list_profiles())
            if self.path == "/passwords":
                return self._json(runtime.passwords.get_active_vault_summary(include_raw_env=True))
            return self._json({"error": "not found"}, 404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                data = json.loads(raw_body or b"{}")
            except json.JSONDecodeError:
                return self._json({"error": "invalid json"}, 400)

            if self.path == "/ingest":
                res = runtime.ingest_page(
                    conversation_id=str(data.get("conversation_id") or "default"),
                    source_id=str(data.get("source_id") or ""),
                    url=str(data.get("url") or ""),
                    title=str(data.get("title") or ""),
                    html=data.get("html"),
                    dwell_seconds=float(data.get("dwell_seconds") or 0.0),
                    visible_text=data.get("visible_text"),
                )
                return self._json(res)

            if self.path == "/answer":
                question = str(data.get("question") or "").strip()
                session_id = str(data.get("session") or "default")
                if not question:
                    return self._json({"error": "question required"}, 400)
                try:
                    return self._json(runtime.run_answer(question, session_id=session_id))
                except Exception as e:
                    return self._json({"error": str(e)}, 500)

            if self.path == "/read":
                model_id = str(data.get("model") or "hertz (reader)")
                question = str(data.get("question") or "").strip()
                sources = data.get("sources") or []
                if not sources and data.get("source_ids"):
                    sources = [{"id": sid, "url": "", "title": ""} for sid in data["source_ids"]]
                try:
                    return self._json(runtime.run_read(model_id, question, sources))
                except Exception as e:
                    return self._json({"error": str(e)}, 500)

            if self.path == "/knowledge/pause":
                paused = bool(data.get("pause_learning", False))
                return self._json({"ok": True, "pause_learning": runtime.set_pause_learning(paused)})

            if self.path == "/knowledge/delete_passage":
                pid = str(data.get("passage_id") or "")
                return self._json(runtime.delete_passage(pid))

            if self.path == "/knowledge/delete_entity":
                slug = str(data.get("slug") or "")
                return self._json(runtime.delete_brain_entity(slug))

            if self.path == "/knowledge/upsert_entity":
                ent = runtime.brain.upsert_entity(
                    entity_type=str(data.get("type") or "note"),
                    name=str(data.get("name") or "Note"),
                    summary=str(data.get("summary") or ""),
                    attributes=data.get("attributes") if isinstance(data.get("attributes"), dict) else {},
                    content=str(data.get("content") or ""),
                    relationships=data.get("relationships"),
                    aliases=data.get("aliases") if isinstance(data.get("aliases"), list) else [],
                    source_url=str(data.get("source_url") or ""),
                    tier=int(data.get("tier") or 1),
                    actor=str(data.get("actor") or "api/manual"),
                )
                return self._json({"ok": True, "entity": ent})

            if self.path == "/forget":
                cid = str(data.get("conversation_id") or "")
                return self._json(runtime.forget_conversation(cid))

            if self.path == "/bookmarks/sync":
                bookmarks = data.get("bookmarks") or []
                return self._json(runtime.sync_bookmarks(bookmarks))

            if self.path == "/profile/create":
                try:
                    res = runtime.passwords.create_profile(
                        name=str(data.get("name") or ""),
                        pin=str(data.get("pin") or ""),
                    )
                    runtime._refresh_active_profile_brain()
                    return self._json({"ok": True, **res})
                except Exception as e:
                    return self._json({"ok": False, "error": str(e)}, 400)

            if self.path == "/profile/unlock":
                try:
                    res = runtime.passwords.unlock_profile(
                        profile_id=str(data.get("profile_id") or ""),
                        pin=str(data.get("pin") or ""),
                    )
                    runtime._refresh_active_profile_brain()
                    runtime.bookmark_wake_event.set()
                    return self._json({"ok": True, **res})
                except Exception as e:
                    return self._json({"ok": False, "error": str(e)}, 400)

            if self.path == "/profile/lock":
                res = runtime.passwords.lock_profile()
                runtime._refresh_active_profile_brain()
                return self._json({"ok": True, **res})

            if self.path == "/profile/delete":
                try:
                    res = runtime.passwords.delete_profile(
                        profile_id=str(data.get("profile_id") or ""),
                        pin=str(data.get("pin") or ""),
                    )
                    runtime._refresh_active_profile_brain()
                    return self._json({"ok": True, **res})
                except Exception as e:
                    return self._json({"ok": False, "error": str(e)}, 400)

            if self.path == "/passwords/upsert":
                try:
                    vault = runtime.passwords.upsert_service_credential(
                        service_or_domain=str(data.get("service") or ""),
                        username=str(data.get("username") or ""),
                        password=str(data.get("password") or ""),
                        token=str(data.get("token") or ""),
                        cookie=str(data.get("cookie") or ""),
                        url=str(data.get("url") or ""),
                    )
                    runtime.bookmark_wake_event.set()
                    return self._json({"ok": True, "vault": vault})
                except Exception as e:
                    return self._json({"ok": False, "error": str(e)}, 400)

            if self.path == "/passwords/save_env":
                try:
                    vault = runtime.passwords.save_raw_env(str(data.get("raw_env") or ""))
                    runtime.bookmark_wake_event.set()
                    return self._json({"ok": True, "vault": vault})
                except Exception as e:
                    return self._json({"ok": False, "error": str(e)}, 400)

            if self.path == "/passwords/import_env":
                try:
                    vault = runtime.passwords.import_env_file(str(data.get("path") or ""))
                    runtime.bookmark_wake_event.set()
                    return self._json({"ok": True, "vault": vault})
                except Exception as e:
                    return self._json({"ok": False, "error": str(e)}, 400)

            if self.path == "/passwords/delete":
                try:
                    vault = runtime.passwords.delete_service_credential(str(data.get("service") or ""))
                    return self._json({"ok": True, "vault": vault})
                except Exception as e:
                    return self._json({"ok": False, "error": str(e)}, 400)

            if self.path == "/passwords/match":
                target = str(data.get("target") or "")
                creds = runtime.passwords.find_credentials_for_target(target)
                return self._json({"ok": True, "credentials": creds})

            if self.path == "/chat":
                messages = data.get("messages") or []
                sources = data.get("sources") or []
                web_enabled = bool(data.get("web", False))

                self.send_response(200)
                self._send_cors_headers()
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()

                try:
                    for event in runtime.stream_chat(messages, sources, web_enabled=web_enabled):
                        line = f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                        self.wfile.write(line.encode("utf-8"))
                        self.wfile.flush()
                except Exception as e:
                    err_payload = {
                        "error": str(e),
                        "delta": f"[error: {e}]",
                        "done": True,
                        "source_ids": [],
                    }
                    err_line = f"data: {json.dumps(err_payload, ensure_ascii=False)}\n\n"
                    self.wfile.write(err_line.encode("utf-8"))
                    self.wfile.flush()
                return

            return self._json({"error": "not found"}, 404)

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description="Satz v0.3 Local Model Sidecar")
    parser.add_argument("--sgs-root", default=str(Path(__file__).resolve().parent.parent.parent / "sgs"))
    parser.add_argument("--gemma-path", default="models/gemma-4-e4b-it")
    parser.add_argument("--store", default=str(resolve_default_store_path()))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8020)
    args = parser.parse_args()

    runtime = SatzSidecarRuntime(
        sgs_root=Path(args.sgs_root),
        store_path=Path(args.store),
        gemma_rel_path=args.gemma_path,
    )
    server = make_sidecar_server(runtime, host=args.host, port=args.port)
    print(
        f"[satz-sidecar] listening on http://{args.host}:{args.port} (sgs={runtime.sgs_root}, store={runtime.store_path})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
