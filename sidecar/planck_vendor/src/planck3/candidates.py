"""
Deterministic candidate generation for EXTRACT.

The policy never writes a value. This module turns a page into typed mentions
(year / number / date / entity / text), each with its context sentence, and
pre-ranks them lexically. The policy's job is only to pick one (plan section 5).
"""

import math
import re

from .util import STOPWORDS, content_words, norm_text

ANSWER_TYPES = ("year", "number", "date", "entity", "text")
MAX_SPAN_CANDIDATES = 32

_MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|December|"
           "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec")
_UNITS = ("km/h|mph|km|cm|mm|m|metres|meters|metre|meter|ft|feet|foot|inches|inch|in|kg|g|lb|lbs|"
          "mAh|Wh|W|GB|TB|MB|GHz|MHz|hours|h|minutes|min|%|percent|°C|°F|million|billion")

RE_YEAR = re.compile(r"(?<![\d.,])(1[5-9]\d\d|20\d\d)(?![\d,]|\.\d)")
RE_DATE = re.compile(
    rf"\b(\d{{1,2}} (?:{_MONTHS})\.? \d{{4}}|(?:{_MONTHS})\.? \d{{1,2}},? \d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})\b")
RE_NUMBER = re.compile(
    rf"(?<![\w.,])(\d{{1,3}}(?:[,\u00a0\u202f\u2009]\d{{3}})+(?:\.\d+)?|\d+(?:\.\d+)?)(?:\s?({_UNITS})(?![A-Za-z]))?")
_CONNECT = {"de", "da", "del", "van", "von", "der", "la", "le", "di", "du", "y", "of", "&", "bin", "al"}
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
# words that name the answer TYPE, not the fact ("what YEAR", "how MANY")
_QFORM = {"year", "years", "many", "much", "number", "exactly", "approximately", "roughly"}
# reference-list / boilerplate lines carry dates and names that are never the answer
_BOILER = re.compile(r"↑|\bRetrieved\b|\bArchived from\b|\bISBN\b|\bdoi:|^\^|cookies?\b", re.I)


def split_sentences(text: str, max_len: int = 400) -> list[str]:
    out = []
    text = re.sub(r"\[\s*(?:\d+|citation needed|[a-z])\s*\]", "", text)
    for block in text.split("\n"):
        block = block.strip(" |\t")
        if len(block) < 3:
            continue
        for s in _SENT_SPLIT.split(block):
            s = s.strip()
            if 3 <= len(s) and not _BOILER.search(s):
                out.append(s[:max_len])
    return out


_UNIT_CANON = {"m": "m", "metres": "m", "meters": "m", "metre": "m", "meter": "m",
               "ft": "ft", "feet": "ft", "foot": "ft", "in": "in", "inch": "in", "inches": "in",
               "km": "km", "kilometres": "km", "kilometers": "km", "cm": "cm", "mm": "mm",
               "kg": "kg", "kilograms": "kg", "g": "g", "grams": "g", "lb": "lb", "lbs": "lb", "pounds": "lb",
               "mph": "mph", "km/h": "km/h", "°c": "c", "celsius": "c", "°f": "f", "fahrenheit": "f"}


def question_unit(question: str) -> str | None:
    for w in re.findall(r"[\w/°]+", question.lower()):
        if w in _UNIT_CANON and w not in ("in", "m", "g"):  # bare in/m/g are too ambiguous in prose
            return _UNIT_CANON[w]
    return None


def _is_cap(tok: str) -> bool:
    return bool(tok) and tok[0].isupper() and any(c.isalpha() for c in tok)


def _entities(sentence: str) -> list[tuple[str, int]]:
    raw = list(re.finditer(r"\S+", sentence))
    toks = [(re.sub(r"['’]s$", "", m.group(0).strip(".,;:()[]\"'!?")), m.start()) for m in raw]
    spans, cur = [], []
    for i, (tok, pos) in enumerate(toks):
        if _is_cap(tok) and tok.lower() not in STOPWORDS:
            cur.append((tok, pos))
        elif cur and tok.lower() in _CONNECT and i + 1 < len(toks) and _is_cap(toks[i + 1][0]):
            cur.append((tok, pos))
        else:
            if cur:
                spans.append(cur)
            cur = []
            continue
        if raw[i].group(0)[-1] in ",;:.)!?":  # punctuation closes the span
            spans.append(cur)
            cur = []
    if cur:
        spans.append(cur)
    out = []
    for span in spans:
        span = span[:5]
        out.append((" ".join(t for t, _ in span), span[0][1]))
    return out


def mentions(sentence: str, answer_type: str) -> list[tuple[str, int]]:
    """(value, char_offset) mentions of the requested type in one sentence."""
    if answer_type == "year":
        return [(m.group(1), m.start()) for m in RE_YEAR.finditer(sentence)]
    if answer_type == "date":
        return [(m.group(1), m.start()) for m in RE_DATE.finditer(sentence)]
    if answer_type == "number":
        out = []
        for m in RE_NUMBER.finditer(sentence):
            val = m.group(1) + (f" {m.group(2)}" if m.group(2) else "")
            out.append((val, m.start()))
        return out
    if answer_type == "entity":  # a month or weekday is never the answer to a who/which question
        return [(e, o) for e, o in _entities(sentence) if not (set(norm_text(e).split()) & _NOT_NODES)]
    if answer_type == "text":
        return [(sentence, 0)]
    raise ValueError(f"unknown answer_type {answer_type}")


def _score(sentence: str, value: str, offset: int, q_words: list[str], weights: dict,
           q_unit: str | None = None) -> float:
    return sum(_score_parts(sentence, value, offset, q_words, weights, q_unit).values())


# what each score term means, in the words an answer card shows ("why this value")
PART_LABELS = {"overlap": "sentence uses the question's words", "near": "value sits next to them",
               "echo": "value repeats the question's subject", "unit": "unit matches the question",
               "about": "source is about the subject", "repeats": "mentioned more than once",
               "agree": "other sources give the same value"}


def _score_parts(sentence: str, value: str, offset: int, q_words: list[str], weights: dict,
                 q_unit: str | None = None) -> dict:
    """The additive terms of a candidate's score, kept so an answer can say why it won."""
    s_norm = norm_text(sentence)
    s_words = set(s_norm.split())
    if not q_words:
        return {"overlap": 0.0}
    overlap = sum(weights[w] for w in q_words if w in s_words) / sum(weights.values())
    # proximity: value close to a query word in the sentence
    prox = 0.0
    low = sentence.lower()
    positions = [low.find(w) for w in q_words if low.find(w) >= 0]
    if positions:
        dist = min(abs(p - offset) for p in positions)
        prox = 1.0 / (1.0 + dist / 40.0)
    # a value that IS the subject of the question is not its answer
    v_words = set(norm_text(value).split())
    echo = 1.0 if v_words and v_words <= set(q_words) else 0.0
    return {"overlap": overlap, "near": 0.5 * prox, "echo": -1.5 * echo, "unit": _unit_bonus(value, q_unit)}


def _unit_bonus(value: str, q_unit: str | None) -> float:
    if not q_unit:
        return 0.0
    parts = value.split(" ", 1)
    c_unit = _UNIT_CANON.get(parts[1].lower()) if len(parts) > 1 else None
    if c_unit is None:
        return -0.2
    return 0.4 if c_unit == q_unit else -0.8


def span_candidates(question: str, text: str, answer_type: str, url: str = "",
                    extra_lines: list[str] | None = None, limit: int = MAX_SPAN_CANDIDATES) -> list[dict]:
    """Ranked typed candidates from ONE page [{value, type, context, url, score, support, margin}]."""
    lines = [(l, url) for l in list(extra_lines or []) + split_sentences(text)]
    return _rank_lines(question, lines, answer_type, limit)


def title_aboutness(question: str, title: str) -> float:
    """
    Is this result ABOUT the question's subject? Title core (site suffixes like " - Wikipedia"
    dropped), then overlap over union, so "Netflix Animation" (0.5) ranks below "Netflix" (1.0)
    for a question about Netflix. 0.5 when the question has no recognisable subject.
    """
    subject = main_entity(question)
    s_words = set(norm_text(subject).split()) if subject else set()
    if not s_words:
        return 0.5
    t_words = set(content_words(re.split(r"\s[-|–—:·]\s", title)[0]))
    return round(len(s_words & t_words) / len(s_words | t_words), 3) if t_words else 0.0


def snippet_candidates(question: str, results: list[dict], answer_type: str,
                       limit: int = MAX_SPAN_CANDIDATES) -> list[dict]:
    """
    Snippet-first: typed candidates read off the search result snippets, before any fetch.
    A value repeated by several DIFFERENT domains is corroboration (free VERIFY); it is
    counted in `domains` and earns a small score bonus.
    """
    # aboutness: a snippet from a page ABOUT the subject (title names it) is evidence; a snippet
    # from another page that merely mentions it ("Netflix Animation" for "Netflix founded") is not
    about = {r["url"]: title_aboutness(question, r.get("title", "")) for r in results}
    lines = [(sent, r["url"]) for r in results for sent in split_sentences(_unstamp(r.get("snippet", "")))]
    cands = _rank_lines(question, lines, answer_type, limit=10**6, domain_bonus=0.1,
                        line_bonus={u: 0.4 * a - (0.3 if a == 0 else 0.0) for u, a in about.items()})
    for c in cands:
        c["about"] = max(about.get(u, 0.0) for u in c.get("urls", [c["url"]]))
    return cands[:limit]


_STAMP = re.compile(rf"^\s*((?:{_MONTHS})\.? \d{{1,2}}, \d{{4}}|\d+ (?:minutes?|hours?|days?|weeks?) ago)\s*[\u00b7\u2013\u2014-]\s*")


def _unstamp(snippet: str) -> str:
    """Bing-style snippets (ddgs) open with a publish stamp, 'Sep 13, 2026 · Who won ...': make it its own
    sentence, so the stamp's month/year is not read as part of the answer sentence (round 4, Mac check)."""
    return _STAMP.sub(lambda m: m.group(1) + ". ", snippet or "", count=1)


def _rank_lines(question, lines, answer_type, limit, domain_bonus: float = 0.0,
                line_bonus: dict | None = None) -> list[dict]:
    q_words = [w for w in content_words(question) if w not in _QFORM]
    q_unit = question_unit(question) if answer_type == "number" else None
    # in-page IDF: the question's subject ("IKEA") is on every line of its own
    # page and says nothing; the attribute word ("founded") is rare and decisive
    line_words = [set(norm_text(l).split()) for l, _ in lines]
    n = max(len(lines), 1)
    weights = {w: math.log(1 + n / (1 + sum(1 for lw in line_words if w in lw))) + 0.1 for w in q_words}
    best: dict[str, dict] = {}
    for sent, url in lines:
        for value, off in mentions(sent, answer_type):
            key = norm_text(value)
            if not key:
                continue
            parts = _score_parts(sent, value, off, q_words, weights, q_unit)
            parts["about"] = (line_bonus or {}).get(url, 0.0)
            sc = sum(parts.values())
            dom = _domain(url)
            prev = best.get(key)
            if prev is None:
                best[key] = {"value": value, "type": answer_type, "context": sent[:240], "url": url,
                             "score": sc, "support": 1, "domains": [dom], "urls": [url], "parts": parts}
            else:
                prev["support"] += 1
                if dom not in prev["domains"]:
                    prev["domains"].append(dom)
                if url not in prev["urls"]:
                    prev["urls"].append(url)
                if sc > prev["score"]:
                    prev.update(value=value, context=sent[:240], score=sc, url=url, parts=parts)
    cands = list(best.values())
    for c in cands:  # repeated mentions are weak corroboration; other domains stronger
        c["parts"] = dict(c["parts"], repeats=0.05 * min(c["support"] - 1, 4),
                          agree=domain_bonus * min(len(c["domains"]) - 1, 3))
        c["parts"] = {k: round(v, 3) for k, v in c["parts"].items() if abs(v) >= 0.0005}
        c["score"] = round(c["score"] + c["parts"].get("repeats", 0.0) + c["parts"].get("agree", 0.0), 4)
    cands.sort(key=lambda c: -c["score"])
    for a, b in zip(cands, cands[1:] + [None]):  # lead over the runner-up
        a["margin"] = round(a["score"] - (b["score"] if b else 0.0), 4)
    return cands[:limit]


def _domain(url: str) -> str:
    from urllib.parse import urlparse
    d = urlparse(url).netloc.lower()
    return d[4:] if d.startswith("www.") else d


# ── depth: ranked evidence passages (Brain-style retrieval, over the web) ──
def main_entity(question: str) -> str | None:
    """Longest capitalized span that is not the sentence-initial wh-word (the question's subject)."""
    toks = re.findall(r"[\w&'’.-]+", question)
    spans, cur = [], []
    for i, t in enumerate(toks):
        t = t.strip(".")
        ok = t[:1].isupper() and not (i == 0 and t.lower() in STOPWORDS) and t.lower() != "i"
        if ok or (cur and t.lower() in ("of", "the", "de", "&") and i + 1 < len(toks) and toks[i + 1][:1].isupper()):
            cur.append(t)
        elif cur:
            spans.append(" ".join(cur))
            cur = []
    if cur:
        spans.append(" ".join(cur))
    return max(spans, key=len) if spans else None


def rank_passages(question: str, docs: list[dict], k: int = 6, per_source: int = 2,
                  min_score: float = 0.25) -> list[dict]:
    """
    docs: [{url, domain, title, trust, text}] -> top-k passages [{text, url, domain, title, trust, score}].
    A passage = a relevant sentence plus its next sentence for context. Only content words
    count (stopword-only overlap is the noise Brain's keyword tier shows), weighted by
    IDF across ALL docs, so a word every page repeats earns nothing. Near-duplicate
    passages (mirrors, syndicated copies) are kept once, from the most trusted source.
    """
    q_words = [w for w in content_words(question) if w not in _QFORM]
    if not q_words:
        return []
    per_doc = []
    for d in docs:
        sents = split_sentences(d.get("text", ""))
        per_doc.append((d, sents, [set(norm_text(x).split()) for x in sents]))
    all_sets = [ws for _, _, sets in per_doc for ws in sets]
    n = max(len(all_sets), 1)
    idf = {w: math.log(1 + n / (1 + sum(1 for ws in all_sets if w in ws))) for w in q_words}
    total = sum(idf.values()) or 1.0
    cands = []
    for d, sents, sets in per_doc:
        for i, (sent, ws) in enumerate(zip(sents, sets)):
            if len(sent) < 25:
                continue
            sc = sum(idf[w] for w in q_words if w in ws) / total
            if sc < min_score:
                continue
            text = sent if i + 1 >= len(sents) else f"{sent} {sents[i + 1]}"
            cands.append({"text": text[:420], "url": d["url"], "domain": d.get("domain", ""),
                          "title": d.get("title", ""), "trust": d.get("trust", 0.5),
                          "score": round(sc + 0.1 * d.get("trust", 0.5), 4)})
    cands.sort(key=lambda c: -c["score"])
    out, seen, used = [], [], {}
    for c in cands:
        sig = set(norm_text(c["text"]).split())
        if any(len(sig & s) / max(len(sig | s), 1) > 0.6 for s in seen):
            continue  # near-duplicate of a passage we already kept
        if used.get(c["url"], 0) >= per_source:
            continue
        out.append(c)
        seen.append(sig)
        used[c["url"]] = used.get(c["url"], 0) + 1
        if len(out) >= k:
            break
    return out


_NOT_NODES = set("""january february march april may june july august september october november december
jan feb mar apr jun jul aug sep sept oct nov dec
monday tuesday wednesday thursday friday saturday sunday""".split())
# nationality/language adjectives ("Swedish", "American", "Japanese") describe, they are not places to go
_ADJ_SUFFIX = ("ish", "ese", "ian", "ean", "ican", "ic", "an")


def _is_node(n: str) -> bool:
    words = n.split()
    if len(n) < 3 or n in STOPWORDS or any(w in _NOT_NODES for w in words):
        return False
    if len(words) == 1 and n.endswith(_ADJ_SUFFIX) and not n.endswith(("stan", "land")):
        return False
    return " of " not in f" {n} "  # "CEO of H&M", "Duke of X": roles/phrases, not nodes


def passage_entities(text: str, exclude: str | None = None, limit: int = 8) -> list[str]:
    """Named things a passage mentions (graph nodes). Drops the subject itself and junk spans."""
    ex = norm_text(exclude or "")
    out, seen = [], set()
    for sent in split_sentences(text):
        for ent, off in _entities(sent):
            n = norm_text(ent)
            if n == ex or n in seen or not _is_node(n) or (off == 0 and len(n.split()) == 1):
                continue  # sentence-initial single capitalized words are mostly not names
            seen.add(n)
            out.append(ent)
            if len(out) >= limit:
                return out
    return out
