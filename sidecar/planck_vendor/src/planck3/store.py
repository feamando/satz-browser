"""
The knowledge store: where Planck 3.0 "gets smarter with use" (weights stay frozen).
It is a local, private knowledge graph that grows with every question, and becomes
MORE relevant to its user over time: it retrieves what they searched and what is
adjacent to it, from the sources they trust, instead of what an ad auction wants.

    facts     every answered value + source + span + p + freshness TTL
    passages  the evidence read to answer (retrievable later with no web at all)
    edges     entity co-mention graph built from passages ("what is adjacent")
    queries   the interest log (what this user asks about, recency-weighted)
    personal  the user's own 0-10 score per source ("trust more / less"); effective trust =
              0.7 x system (hand-scored registry) + 0.3 x personal (src/planck3/registry.py)
    domains   per-domain Beta(a, b) usage statistics (corroborated vs nothing usable): an AUDIT
              record only since round 5; it no longer moves trust (scores must stay explainable)
    watches   stored fact queries re-run on a schedule; notify on change

Lookup is lexical in v0 (exact entity/attribute, else fuzzy question match).
The DynamicBlobStore index (src/conversation_memory.py) plugs in once the
Planck encoder is in the loop (G3).
"""

import json
import re
import sqlite3
import time
from difflib import SequenceMatcher
from pathlib import Path

from .util import content_words, norm_text

DAY = 86400.0

# attribute keyword -> TTL days. First match wins; None = never expires.
TTL_RULES = (
    (("price", "cost", "fee", "deal", "stock", "availability"), 1),
    (("hours", "open", "opening", "closing", "schedule", "weather"), 7),
    (("ceo", "president", "leader", "population", "rating", "version", "latest"), 90),
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT, question_norm TEXT, entity TEXT, attribute TEXT, answer_type TEXT,
    value TEXT, source_url TEXT, domain TEXT, context TEXT,
    retrieved_at REAL, ttl_days REAL, p REAL, verified INTEGER, task_id TEXT
);
CREATE INDEX IF NOT EXISTS facts_ea ON facts(entity, attribute);
CREATE TABLE IF NOT EXISTS domains (domain TEXT PRIMARY KEY, a REAL, b REAL);
CREATE TABLE IF NOT EXISTS personal (domain TEXT PRIMARY KEY, score REAL, ts REAL);
CREATE TABLE IF NOT EXISTS passages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT, domain TEXT, title TEXT, text TEXT, text_norm TEXT UNIQUE, entity TEXT, question TEXT, ts REAL
);
CREATE TABLE IF NOT EXISTS edges (src TEXT, dst TEXT, weight REAL, ts REAL, PRIMARY KEY (src, dst));
CREATE TABLE IF NOT EXISTS queries (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, entity TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, target TEXT, value INTEGER, ts REAL);
CREATE TABLE IF NOT EXISTS watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT, answer_type TEXT, entity TEXT, attribute TEXT,
    condition TEXT, last_value TEXT, last_checked REAL, created REAL
);
"""


def ttl_for(attribute: str | None, question: str, override: float | None = None) -> float | None:
    if override is not None:
        return override
    hay = norm_text(f"{attribute or ''} {question}")
    for keys, days in TTL_RULES:
        if any(k in hay.split() for k in keys):
            return days
    return None


class Store:
    def __init__(self, path: str | Path, clock=time.time, registry=None):
        from .registry import default_registry
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # the chat server serializes turns behind a lock, so cross-thread use is safe
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.clock = clock
        self.registry = registry or default_registry()

    def close(self):
        self.db.close()

    # ── facts ────────────────────────────────────────────────────────────
    def add_fact(self, *, question, value, answer_type, source_url, domain, context,
                 p, verified=False, entity=None, attribute=None, ttl_days=None, task_id=None) -> int:
        cur = self.db.execute(
            "INSERT INTO facts (question, question_norm, entity, attribute, answer_type, value,"
            " source_url, domain, context, retrieved_at, ttl_days, p, verified, task_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (question, norm_text(question), norm_text(entity or "") or None,
             norm_text(attribute or "") or None, answer_type, value, source_url, domain,
             context, self.clock(), ttl_for(attribute, question, ttl_days), float(p),
             int(bool(verified)), task_id))
        self.db.commit()
        return cur.lastrowid

    def is_fresh(self, row) -> bool:
        ttl = row["ttl_days"]
        return ttl is None or (self.clock() - row["retrieved_at"]) < ttl * DAY

    def lookup(self, question: str, entity: str | None = None, attribute: str | None = None,
               answer_type: str | None = None, min_ratio: float = 0.85, limit: int = 5) -> list[dict]:
        """Fresh stored facts matching the query, best first."""
        if entity and attribute:
            rows = self.db.execute(
                "SELECT * FROM facts WHERE entity=? AND attribute=? ORDER BY retrieved_at DESC",
                (norm_text(entity), norm_text(attribute))).fetchall()
            scored = [(1.0, r) for r in rows]
        else:
            # Fuzzy path: the SAME content words (order/stopwords may differ). A near-identical
            # string with a different subject ("capital of Canada" vs "capital of Brazil")
            # must never hit; that is a confidently wrong answer served from memory.
            qn = norm_text(question)
            qset = set(content_words(question))
            rows = self.db.execute("SELECT * FROM facts ORDER BY retrieved_at DESC LIMIT 5000").fetchall()
            scored = []
            for r in rows:
                if set(content_words(r["question"])) != qset:
                    continue
                sim = SequenceMatcher(None, qn, r["question_norm"]).ratio()
                if sim >= min_ratio:
                    scored.append((sim, r))
        out = []
        for sim, r in sorted(scored, key=lambda x: (-x[0], -x[1]["p"])):
            if answer_type and r["answer_type"] != answer_type:
                continue
            if not self.is_fresh(r):
                continue
            d = dict(r)
            d["match"] = round(sim, 3)
            out.append(d)
            if len(out) >= limit:
                break
        return out

    def related(self, entity: str | None, exclude_question: str = "", limit: int = 5) -> list[dict]:
        """Fresh stored facts about the same subject: the memory half of the depth pack."""
        if not entity:
            return []
        ent = norm_text(entity)
        rows = self.db.execute("SELECT * FROM facts ORDER BY retrieved_at DESC LIMIT 5000").fetchall()
        out, seen = [], {norm_text(exclude_question)}
        for r in rows:
            if r["question_norm"] in seen or not self.is_fresh(r):
                continue
            if re.search(rf"\b{re.escape(ent)}\b", r["question_norm"]) or r["entity"] == ent:
                out.append({"question": r["question"], "value": r["value"], "source_url": r["source_url"],
                            "p": r["p"], "retrieved_at": r["retrieved_at"]})
                seen.add(r["question_norm"])
                if len(out) >= limit:
                    break
        return out

    def n_facts(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]

    # ── the growing graph: passages, entities, interests ─────────────────
    def log_query(self, question: str, entity: str | None):
        self.db.execute("INSERT INTO queries (question, entity, ts) VALUES (?,?,?)",
                        (question, norm_text(entity or "") or None, self.clock()))
        self.db.commit()

    def add_passages(self, passages: list[dict], entity: str | None, question: str):
        """Keep the evidence (dedup by normalized text) and grow the co-mention graph."""
        from .candidates import passage_entities
        ent = norm_text(entity or "") or None
        for p in passages:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO passages (url, domain, title, text, text_norm, entity, question, ts)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (p["url"], p.get("domain", ""), p.get("title", ""), p["text"], norm_text(p["text"]), ent,
                 question, self.clock()))
            if not cur.rowcount or not ent:
                continue
            for other in passage_entities(p["text"], exclude=entity):
                o = norm_text(other)
                if not o or o == ent:
                    continue
                for a, b in ((ent, o), (o, ent)):
                    self.db.execute(
                        "INSERT INTO edges (src, dst, weight, ts) VALUES (?,?,1,?) "
                        "ON CONFLICT(src, dst) DO UPDATE SET weight = weight + 1, ts = excluded.ts",
                        (a, b, self.clock()))
        self.db.commit()

    def local_passages(self, question: str, k: int = 6) -> list[dict]:
        """Retrieve what you searched, locally: rank stored passages for a new question."""
        from .candidates import rank_passages
        rows = self.db.execute("SELECT url, domain, title, text FROM passages ORDER BY ts DESC LIMIT 5000").fetchall()
        docs = [{"url": r["url"], "domain": r["domain"], "title": r["title"], "text": r["text"],
                 "trust": self.domain_prior(r["domain"])} for r in rows]
        return rank_passages(question, docs, k=k)

    def interests(self, n: int = 10, half_life_days: float = 14.0) -> list[tuple[str, float]]:
        """Entities this user asks about, weighted by recency (exponential decay)."""
        import math
        score: dict[str, float] = {}
        now = self.clock()
        for r in self.db.execute("SELECT entity, ts FROM queries WHERE entity IS NOT NULL"):
            age = (now - r["ts"]) / DAY
            score[r["entity"]] = score.get(r["entity"], 0.0) + math.exp(-age * math.log(2) / half_life_days)
        for r in self.db.execute("SELECT target, value FROM feedback WHERE kind='entity'"):
            score[r["target"]] = score.get(r["target"], 0.0) + 0.5 * r["value"]
        return sorted(score.items(), key=lambda x: -x[1])[:n]

    def adjacent(self, entity: str, n: int = 5, exclude: set | None = None) -> list[tuple[str, float]]:
        exclude = exclude or set()
        rows = self.db.execute("SELECT dst, weight FROM edges WHERE src=? ORDER BY weight DESC LIMIT ?",
                               (norm_text(entity), n + len(exclude) + 5)).fetchall()
        return [(r["dst"], r["weight"]) for r in rows if r["dst"] not in exclude][:n]

    def passages_about(self, entity: str, k: int = 3, min_trust: float = 0.0) -> list[dict]:
        ent = norm_text(entity)
        rows = self.db.execute("SELECT url, domain, title, text, ts FROM passages ORDER BY ts DESC LIMIT 5000").fetchall()
        out = []
        for r in rows:
            if re.search(rf"\b{re.escape(ent)}\b", norm_text(r["text"])) and self.domain_prior(r["domain"]) >= min_trust:
                out.append(dict(r) | {"trust": self.domain_prior(r["domain"])})
                if len(out) >= k:
                    break
        return out

    def feedback(self, kind: str, target: str, value: int):
        """kind: 'source' (a domain: moves its trust prior) or 'entity' (moves interest)."""
        value = 1 if value > 0 else -1
        self.db.execute("INSERT INTO feedback (kind, target, value, ts) VALUES (?,?,?,?)",
                        (kind, norm_text(target) if kind == "entity" else target, value, self.clock()))
        self.db.commit()
        if kind == "source":  # one click = +/- PERSONAL_STEP on the user's own 0-10 score (default: the system's)
            from .registry import PERSONAL_STEP
            cur = self.personal(target)
            base = self.registry.lookup(target)["score"] if cur is None else cur
            self.set_personal(target, base + (PERSONAL_STEP if value > 0 else -PERSONAL_STEP))

    def stale_facts(self, limit: int = 10) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM facts ORDER BY retrieved_at DESC LIMIT 5000")
                if not self.is_fresh(r)][:limit]

    def graph_stats(self) -> dict:
        q = lambda sql: self.db.execute(sql).fetchone()[0]  # noqa: E731
        return {"facts": q("SELECT COUNT(*) FROM facts"), "passages": q("SELECT COUNT(*) FROM passages"),
                "entities": q("SELECT COUNT(DISTINCT src) FROM edges"), "edges": q("SELECT COUNT(*) FROM edges") // 2,
                "queries": q("SELECT COUNT(*) FROM queries"), "domains": q("SELECT COUNT(*) FROM domains")}

    # ── source trust: hand-scored system registry + this user's personal score (capped at 30%) ──
    def personal(self, domain: str) -> float | None:
        row = self.db.execute("SELECT score FROM personal WHERE domain=?", (domain,)).fetchone()
        return None if row is None else float(row["score"])

    def set_personal(self, domain: str, score: float | None):
        if score is None:
            self.db.execute("DELETE FROM personal WHERE domain=?", (domain,))
        else:
            self.db.execute("INSERT OR REPLACE INTO personal (domain, score, ts) VALUES (?,?,?)",
                            (domain, max(0.0, min(10.0, float(score))), self.clock()))
        self.db.commit()

    def trust(self, domain: str, session_shift: float = 0.0, personal: bool = True) -> dict:
        """0-10 trust record (system, personal, effective, band, family). session_shift is ignored since
        round 5: 'more results from here' changes what is RETRIEVED, never a source's trust."""
        from .registry import trust_record
        return trust_record(domain, self.personal(domain) if personal else None, self.registry)

    def domain_prior(self, domain: str) -> float:
        return self.trust(domain)["combined"]

    def update_domain(self, domain: str, success: bool, weight: float = 1.0):
        row = self.db.execute("SELECT a, b FROM domains WHERE domain=?", (domain,)).fetchone()
        a, b = (row["a"], row["b"]) if row else (1.0, 1.0)
        a, b = (a + weight, b) if success else (a, b + weight)
        self.db.execute("INSERT OR REPLACE INTO domains (domain, a, b) VALUES (?,?,?)", (domain, a, b))
        self.db.commit()

    def top_domains(self, n: int = 10) -> list[tuple[str, float, float]]:
        rows = self.db.execute("SELECT domain, a, b FROM domains").fetchall()
        ranked = sorted(((r["domain"], self.domain_prior(r["domain"]), r["a"] + r["b"] - 2) for r in rows),
                        key=lambda x: (-x[1], -x[2]))
        return ranked[:n]

    def known_domains(self) -> set[str]:
        """Every domain with an opinion: scored in the registry, personally scored, or seen."""
        return (set(self.registry.domains) | {r["domain"] for r in self.db.execute("SELECT domain FROM personal")}
                | {r["domain"] for r in self.db.execute("SELECT domain FROM domains")})

    # ── watches ──────────────────────────────────────────────────────────
    def add_watch(self, question, answer_type, condition: dict | None = None,
                  entity=None, attribute=None) -> int:
        cur = self.db.execute(
            "INSERT INTO watches (question, answer_type, entity, attribute, condition, last_value,"
            " last_checked, created) VALUES (?,?,?,?,?,?,?,?)",
            (question, answer_type, entity, attribute, json.dumps(condition or {}), None, None, self.clock()))
        self.db.commit()
        return cur.lastrowid

    def watches(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM watches ORDER BY id")]

    def update_watch(self, watch_id: int, value: str | None):
        self.db.execute("UPDATE watches SET last_value=?, last_checked=? WHERE id=?",
                        (value, self.clock(), watch_id))
        self.db.commit()
