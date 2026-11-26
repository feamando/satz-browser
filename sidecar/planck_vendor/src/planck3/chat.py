"""
Chat surface: the product bet is the behaviour shift from search boxes to chat,
done cheaply. Search already works; what a chat turn adds is (1) a direct answer
instead of links, (2) follow-ups that carry context ("and H&M?", "when was it
founded?"), (3) an answer phrased for a conversation, with its evidence.

All three are deterministic here (typed rules, no generation); each rule is a
small classification the Planck head can learn later (answer type, NEW vs
SWAP_ENTITY vs PRONOUN follow-up), which is exactly a System One decision.
"""

import re
from dataclasses import dataclass, field

from .candidates import main_entity  # noqa: F401  (re-exported for callers/tests)
from .harness import Harness
from .web import domain_of

_FOLLOW_LEAD = re.compile(r"^\s*(?:and|what about|how about|and what about|and for|same for|also)\b[\s,]*", re.I)
_PRONOUN = re.compile(r"\b(it|its|they|their|them|he|his|she|her|this|that one)\b", re.I)
_WH = re.compile(r"^\s*(who|what|when|where|which|how|in what|in which|is|are|was|were|did|does|do)\b", re.I)


def infer_answer_type(question: str) -> str:
    q = question.lower().strip()
    if re.search(r"\b(what|which) (date|day)\b|\bwhen exactly\b|\bon what date\b", q):
        return "date"
    if re.search(r"\b(what|which|in what|in which) year\b|^\s*when\b|\bwhat year\b", q):
        return "year"
    if re.search(r"\bhow (many|much|tall|high|long|far|big|large|heavy|old|fast|deep|wide)\b", q) or \
       re.search(r"\b(height|elevation|altitude|population|number|price|cost|size|length|weight|speed|atomic number|"
                 r"capacity|area|distance|temperature|percentage)\b", q):
        return "number"
    if re.search(r"^\s*(who|whom)\b|\bwho (is|was|were|founded|wrote|directed|painted|invented|developed|created)\b", q) or \
       re.search(r"^\s*where\b|\b(which|what) (city|country|town|company|planet|state|continent|person|author|director)\b", q) or \
       re.search(r"\b(capital|headquarter|headquarters|founder|author|director|ceo|inventor)\b", q):
        return "entity"
    return "text"


@dataclass
class Turn:
    user: str
    question: str          # the standalone question actually asked (after follow-up rewrite)
    answer_type: str
    entity: str | None
    rewrite: str           # NEW | SWAP_ENTITY | PRONOUN
    result: dict = field(default_factory=dict)


def resolve_followup(utterance: str, prev: Turn | None) -> tuple[str, str, str | None]:
    """-> (standalone question, rewrite kind, entity)."""
    u = utterance.strip()
    if prev is None:
        return u, "NEW", main_entity(u)
    lead = _FOLLOW_LEAD.match(u)
    words = re.findall(r"\w+", u)
    # "and H&M?" / "what about Zara" / bare "Zara?" -> same question, new subject
    if lead or (len(words) <= 3 and not _WH.match(u)):
        new_ent = _FOLLOW_LEAD.sub("", u).strip(" ?.!")
        if new_ent and prev.entity and re.search(re.escape(prev.entity), prev.question, re.I):
            q = re.sub(re.escape(prev.entity), new_ent, prev.question, count=1, flags=re.I)
            return q, "SWAP_ENTITY", new_ent
    # "when was it founded?" -> substitute the carried subject
    if prev.entity and _PRONOUN.search(u) and not main_entity(u):
        q = _PRONOUN.sub(lambda m: prev.entity + ("'s" if m.group(1).lower() in ("its", "their", "his", "her") else ""),
                         u, count=1)
        return q, "PRONOUN", prev.entity
    return u, "NEW", main_entity(u)


def chat_answer(turn: Turn) -> str:
    """
    A chat reply: the direct answer first, then its evidence, source and confidence. When the
    confidence is low it says so up front and still shows the best guess. No generation.
    """
    r = turn.result
    ex = r.get("explain") or {}
    if ex.get("pipeline") == "answer":
        return answer_card_text(turn)
    tier = ex.get("tier") or ("confident" if r.get("answered") else "none")
    if tier == "none":
        return ("I couldn't find an answer in what I read. The evidence I found is below. "
                f"(searched for: \"{turn.question}\")")
    value, p = ex.get("value", r.get("value")), ex.get("confidence", r.get("p"))
    ctx = (ex.get("context") or r.get("context") or "").strip()
    srcs = ex.get("sources") or []
    main = next((s["domain"] for s in srcs if s["role"] == "answer"), domain_of(r.get("source_url") or ""))
    agree = next((s["domain"] for s in srcs if s["role"] == "agrees"), None)
    src = main + (f", and {agree} agrees" if agree else ", single source")
    mem = " (from memory)" if r.get("from_store") else ""
    kind = ex.get("confidence_kind", "")
    conf = f"confidence {p:.0%}" if p is not None else "no confidence estimate"
    if tier == "confident":
        return f"**{value}**{mem}.\n> {ctx[:220]}\nSource: {src} · {conf} ({kind})"
    cands = [c for c in ex.get("candidates", []) if c["value"] != value][:1]
    runner = ""
    if cands:
        c = cands[0]
        runner = f" · runner-up {c['value']}" + (f" ({c['p']:.0%})" if c.get("p") is not None else "")
    return (f"Low confidence in my results. Best guess: **{value}**{mem} ({conf}, below my "
            f"{ex.get('bar', 0.5):.0%} bar; {kind}).\n> {ctx[:220]}\nSource: {src}{runner}")


LEADS = {"high": "", "good": "", "low": "Low confidence in my results. ", "sceptical": "Treat this with scepticism. "}


def answer_card_text(turn: Turn) -> str:
    """Round 5 card text: the written answer, its 0-10 confidence and band, and any personal-tilt warning."""
    r = turn.result
    ex = r["explain"]
    if ex["band"] == "none":
        return f"{r['answer_text']} (searched for: \"{turn.question}\")"
    text = r["answer_text"]
    v = str(ex["value"])
    i = text.find(v)
    if i >= 0:
        text = text[:i] + f"**{v}**" + text[i + len(v):]
    lines = [LEADS.get(ex["band"], "") + text,
             f"Confidence {ex['confidence10']:.1f}/10 ({ex['band_label']}) · {ex['qtype'].replace('_', ' ')} question"]
    d = ex.get("divergence")
    if d:
        lines.append(f"Your source preferences changed this answer. Without them: {d['system_value']} "
                     f"({d['system_confidence']}/10, {d['system_band']}).")
    return "\n".join(lines)


def render_why(turn: Turn) -> str:
    """How the answer was collated, the confidence and the weights behind it, the trust of each source."""
    ex = turn.result.get("explain") or {}
    if not ex:
        return "(no explanation recorded)"
    if ex.get("pipeline") == "answer":
        lines = ["How I got this:"] + [f"  {i}. {s}" for i, s in enumerate(ex["steps"], 1)]
        if ex.get("items"):
            lines.append(f"Confidence {ex['confidence10']:.1f}/10 =")
            lines += [f"  {v:+5.1f}  {k}" for k, v in ex["items"]]
        if ex.get("candidates"):
            lines.append("Candidates (reader p, best source trust): " + " · ".join(
                f"{c['value']} ({c['r']:.2f}, {c['top_trust'] or 0:.0f}/10)" for c in ex["candidates"]))
        lines.append(f"Reader: {ex['reader']} · writer: {ex['writer']}"
                     + (" (fell back to the template: " + "; ".join(ex["writer_problems"][:2]) + ")" if ex.get("writer_fallback") else ""))
        if ex.get("sources"):
            lines.append("Sources (system / you / effective, 0-10; you count for at most 30%):")
            for s in ex["sources"]:
                t = s["trust"]
                you = "-" if t["personal"] is None else f"{t['personal']:.0f}"
                flag = "  <- you and the system disagree" if t["conflict"] else ""
                lines.append(f"  {s['role'][:22]:<22} {s['domain']:<28} {t['system']:.0f} / {you} / {t['effective']:.1f}  "
                             f"{t['category']}{flag}")
        return "\n".join(lines)
    lines = ["How I got this:"] + [f"  {i}. {s}" for i, s in enumerate(ex["steps"], 1)]
    if ex.get("confidence") is not None:
        lines.append(f"Confidence: {ex['confidence']:.0%} ({ex['confidence_kind']}); my bar is {ex['bar']:.0%}")
    if ex.get("candidates"):
        lines.append("Candidates: " + " · ".join(
            c["value"] + (f" ({c['p']:.0%})" if c.get("p") is not None else f" (score {c.get('score', 0):.2f})")
            for c in ex["candidates"]))
    if ex.get("why_value"):
        lines.append("Why this value: " + " · ".join(f"{k} {v:+.2f}" for k, v in ex["why_value"]))
    wc = ex.get("why_confidence") or {}
    if wc.get("items"):
        lines.append(f"Why this confidence ({wc['kind']}): " + " · ".join(
            f"{k} {v:+.2f}" if isinstance(v, (int, float)) else f"{k} {v}" for k, v in wc["items"]))
    if ex.get("sources"):
        lines.append("Sources (trust 0-10: system / you / effective; you count for at most 30%):")
        for s in ex["sources"]:
            t = s["trust"]
            you = "-" if t["personal"] is None else f"{t['personal']:.0f}"
            lines.append(f"  {s['role']:<7} {s['domain']:<28} {t['system']:.0f} / {you} / {t['effective']:.1f}  {t['category']}")
    return "\n".join(lines)


def depth_summary(turn: Turn) -> str:
    d = turn.result.get("depth") or {}
    n_src = len({p["url"] for p in d.get("passages", [])})
    return (f"In depth: {len(d.get('passages', []))} passages from {n_src} sources, "
            f"{len(d.get('related', []))} related facts in memory")


def render_depth(turn: Turn, max_passages: int = 6) -> str:
    """The retrieval layer behind the answer: evidence, sources, memory."""
    d = turn.result.get("depth") or {}
    lines = ["Evidence:"]
    for i, p in enumerate(d.get("passages", [])[:max_passages], 1):
        lines.append(f"  {i}. \"{p['text'][:300]}\"\n     ({p['domain']}, trust {p['trust']:.2f}) {p['url']}")
    if d.get("related"):
        lines.append("Also in memory:")
        for f in d["related"]:
            lines.append(f"  - {f['question']} {f['value']}")
    read = [s for s in d.get("sources", []) if s["read"]]
    unread = [s for s in d.get("sources", []) if not s["read"]]
    if read:
        lines.append("Read: " + ", ".join(s["domain"] for s in read))
    if unread:
        lines.append("Further reading:")
        for s in unread[:5]:
            lines.append(f"  - {s['title'][:80]}  {s['url']}")
    return "\n".join(lines)


class ChatSession:
    def __init__(self, harness: Harness):
        self.h = harness
        self.turns: list[Turn] = []

    def ask(self, utterance: str) -> Turn:
        prev = self.turns[-1] if self.turns else None
        q, kind, ent = resolve_followup(utterance, prev)
        at = infer_answer_type(q)
        t = Turn(user=utterance, question=q, answer_type=at, entity=ent, rewrite=kind)
        t.result = self.h.run_fact(q, at, entity=None, attribute=None)
        self.turns.append(t)
        return t
