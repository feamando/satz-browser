"""
The agent loop (plan section 5):

    query -> LOOKUP store -> (miss) SEARCH -> OPEN k -> EXTRACT k -> [VERIFY]
          -> ANSWER card | ABSTAIN

The policy only ever sees an observation and returns a typed Decision; every
side effect (search, fetch, extraction, store writes) happens here, in code.
Each step is logged so successful teacher trajectories can be distilled (G1/G2).

Every answer also carries an `explain` record (2026-10-08): how it was collated (the
steps, in words), the confidence and what kind it is, the weights behind the value
and behind the confidence, and the three trust layers of each source. Three tiers:

    confident       answered with p >= CONFIDENT_P
    low_confidence  a value is shown, clearly labelled ("Low confidence in my results"):
                    an answer below CONFIDENT_P, or the best guess the policy would not commit to
    none            nothing read answers it: only the evidence is shown
"""

import time

from .actions import PHASES, Decision, InvalidDecision, fallback, validate
from .candidates import span_candidates
from .metrics import is_correct, parse_number
from .util import content_words, norm_text
from .web import domain_of, extract_jsonld, extract_main_text

MAX_STEPS = 8
ANSWER_THRESHOLD = 0.3  # ANSWER with p below this becomes ABSTAIN ("couldn't verify"), not a guess
CONFIDENT_P = 0.5       # pre-registered 2026-10-08 (round 4): the confident / low-confidence line
MIN_GUESS_SCORE = 0.4   # an UNCHECKED top candidate is only shown as a best guess above this lexical score


class Harness:
    def __init__(self, policy, web, store, max_steps: int = MAX_STEPS, use_store: bool = True,
                 depth_pages: int = 0, snippet_first: bool = True, answer_threshold: float = ANSWER_THRESHOLD):
        self.policy = policy
        self.web = web
        self.store = store
        self.max_steps = max_steps
        self.use_store = use_store
        self.depth_pages = depth_pages  # extra sources opened AFTER answering, only for the depth pack
        self.snippet_first = snippet_first  # offer snippet values before any page fetch
        self.answer_threshold = answer_threshold
        # "more results from here" (this chat only): changes what is RETRIEVED in later turns, never a
        # source's trust (round 5: trust = system registry + capped personal score, nothing else)
        self.session_more: list[str] = []

    def _trust(self, domain: str) -> dict:
        return self.store.trust(domain)

    # ── one fact question ────────────────────────────────────────────────
    def run_fact(self, question: str, answer_type: str, entity: str | None = None,
                 attribute: str | None = None, ttl_days: float | None = None,
                 task_id: str | None = None, store_answer: bool = True) -> dict:
        st = {"phase": "start", "results": [], "spans": [], "store": [], "held": None,
              "verified": None, "opened": set(), "history": [], "docs": [], "snip_spans": [],
              "events": [], "guess": None, "verify_by": None, "decisions": []}
        calls0 = self.web.calls["search"] + self.web.calls["fetch"]
        search0 = self.web.calls["search"]
        fetch0 = self.web.calls["fetch"]
        usage0 = dict(getattr(self.policy, "usage", {}))
        steps, ms, invalid, trajectory = 0, [], 0, []
        outcome = {"answered": False, "value": None, "p": 0.0, "source_url": None,
                   "context": None, "verified": None, "reason": "step_cap", "from_store": False,
                   "gated_value": None, "from_snippet": False}

        def finish(**kw):
            outcome.update(kw)

        self._answer_type = answer_type
        while steps < self.max_steps:
            obs = self._observation(question, answer_type, st)
            t0 = time.perf_counter()
            d = self.policy.decide(obs)
            ms.append((time.perf_counter() - t0) * 1000)
            valid = True
            try:
                d = validate(d, st["phase"], {k: len(st[k]) for k in ("results", "spans", "store")})
            except InvalidDecision as e:
                invalid += 1
                valid = False
                bad = d
                d = fallback(st["phase"])
                d.meta["invalid"] = f"{bad.action} k={bad.k}: {e}"
            self._note_guess(st, d)
            st["decisions"].append(d)
            trajectory.append({"step": steps, "phase": st["phase"], "obs": _compact(obs),
                               "decision": d.to_dict(), "valid": valid, "raw": d.raw[:300],
                               "meta": {k: v for k, v in d.meta.items() if k != "fallback"}})
            steps += 1
            st["history"].append(d.action + (f" {d.k}" if d.k is not None else ""))
            done = self._apply(d, st, question, answer_type, entity, attribute, finish)
            if done:
                break

        if outcome["answered"] and store_answer and not outcome["from_store"]:
            self.store.add_fact(question=question, value=outcome["value"], answer_type=answer_type,
                                source_url=outcome["source_url"], domain=domain_of(outcome["source_url"] or ""),
                                context=outcome["context"], p=outcome["p"], verified=bool(outcome["verified"]),
                                entity=entity, attribute=attribute, ttl_days=ttl_days, task_id=task_id)
        answer_fetches = self.web.calls["fetch"] - fetch0  # what the user waits for
        outcome["guess"] = None if outcome["answered"] else self._final_guess(st, outcome)
        outcome["tier"] = answer_tier(outcome)
        outcome["depth"] = self._depth(question, entity, st)
        outcome["explain"] = self._explain(st, outcome)
        if store_answer:  # the knowledge graph grows with every question asked
            from .candidates import main_entity
            subject = entity or main_entity(question)
            self.store.log_query(question, subject)
            self.store.add_passages(outcome["depth"]["passages"], subject, question)
        usage = getattr(self.policy, "usage", {})
        outcome.update(steps=steps, decision_ms=ms, invalid=invalid, trajectory=trajectory,
                       web_calls=self.web.calls["search"] + self.web.calls["fetch"] - calls0,
                       search_calls=self.web.calls["search"] - search0,
                       fetch_calls=self.web.calls["fetch"] - fetch0, answer_fetch_calls=answer_fetches,
                       usage={k: usage.get(k, 0) - usage0.get(k, 0) for k in usage})
        return outcome

    def _observation(self, question, answer_type, st) -> dict:
        spec = PHASES[st["phase"]]
        return {"question": question, "answer_type": answer_type, "phase": st["phase"],
                "spans_source": "search result snippets" if st["phase"] == "results_snip" else "the open page",
                "allowed": list(spec["allowed"]), "pointer": dict(spec["pointer"]),
                "lists": {"results": st["results"], "spans": st["spans"], "store": st["store"]},
                "held": st["held"], "verified": st["verified"], "history": list(st["history"]),
                "opened": set(st["opened"]), "store_size": self.store.n_facts() if self.use_store else 0}

    def _apply(self, d: Decision, st, question, answer_type, entity, attribute, finish) -> bool:
        a = d.action
        if a == "LOOKUP":
            hits = self.store.lookup(question, entity, attribute, answer_type) if self.use_store else []
            if hits:
                st["store"], st["phase"] = hits, "store_hit"
                st["events"].append({"kind": "memory", "n": len(hits)})
                return False
            return self._search(st, question, finish)
        if a == "SEARCH":
            return self._search(st, question, finish)
        if a == "OPEN":
            return self._open(d.k, st, question, answer_type, finish)
        if a == "EXTRACT":
            span = dict(st["spans"][d.k])
            span["domain"] = domain_of(span["url"])
            span["from_snippet"] = st["phase"] == "results_snip"
            st["held"], st["verified"], st["phase"] = span, None, "extracted"
            st["events"].append({"kind": "extract", "value": span["value"], "domain": span["domain"],
                                 "from": "snippets" if span["from_snippet"] else "page"})
            self.store.update_domain(span["domain"], True, weight=0.5)
            return False
        if a == "VERIFY":
            st["verified"] = self._verify(st, question, answer_type)
            st["phase"] = "verified"
            st["events"].append({"kind": "verify", "ok": bool(st["verified"]), **(st["verify_by"] or {})})
            if st["verified"]:
                self.store.update_domain(st["held"]["domain"], True)
            return False
        if a == "ANSWER" and d.p < self.answer_threshold:
            # a guess is worse than "I couldn't verify that": keep the value for analysis only
            gated = st["store"][d.k]["value"] if st["phase"] == "store_hit" else (st["held"] or {}).get("value")
            finish(answered=False, p=d.p, reason="low_confidence", gated_value=gated)
            return True
        if a == "ANSWER":
            if st["phase"] == "store_hit":
                f = st["store"][d.k]
                finish(answered=True, value=f["value"], p=d.p, source_url=f["source_url"],
                       context=f["context"], verified=bool(f["verified"]), reason="store", from_store=True)
            else:
                h = st["held"]
                finish(answered=True, value=h["value"], p=d.p, source_url=h["url"],
                       context=h["context"], verified=st["verified"], reason="answer",
                       from_snippet=bool(h.get("from_snippet")))
            return True
        finish(answered=False, p=d.p, reason="abstain")
        return True

    def _search(self, st, question, finish) -> bool:
        results = self.web.search(question)
        for r in results:
            r["trust_layers"] = self._trust(r["domain"])
            r["trust"] = r["trust_layers"]["combined"]
        st["results"], st["opened"], st["phase"] = results, set(), "results"
        st["events"].append({"kind": "search", "query": question, "n": len(results),
                             "backend": getattr(self.web, "last_backend", None) or getattr(self.web, "backend", "search"),
                             "domains": list(dict.fromkeys(r["domain"] for r in results))})
        if not results:
            finish(answered=False, reason="no_results")
            return True
        if self.snippet_first:
            from .candidates import snippet_candidates
            st["snip_spans"] = snippet_candidates(question, results, self._answer_type)
            if st["snip_spans"]:
                st["spans"], st["phase"] = list(st["snip_spans"]), "results_snip"
                st["events"].append({"kind": "snippets", "n": len(st["snip_spans"])})
        return False

    def _open(self, k, st, question, answer_type, finish) -> bool:
        r = st["results"][k]
        st["opened"].add(k)
        spans = self._page_spans(r, question, answer_type, st)
        st["events"].append({"kind": "open", "domain": r["domain"], "title": r.get("title", ""), "n": len(spans)})
        if not spans:
            self.store.update_domain(r["domain"], False, weight=0.5)
            if len(st["opened"]) >= len(st["results"]):
                finish(answered=False, reason="exhausted")
                return True
            st["spans"], st["phase"] = [], "results"
            return False
        st["spans"], st["held"], st["verified"], st["phase"] = spans, None, None, "page"
        return False

    def _page_spans(self, result, question, answer_type, st):
        url = result["url"]
        page = self.web.fetch(url)
        if not page.get("html"):
            return []
        text = extract_main_text(page["html"], url)
        st["docs"].append({"url": url, "domain": result.get("domain", domain_of(url)),
                           "title": result.get("title", ""), "trust": result.get("trust", 0.5), "text": text})
        return span_candidates(question, text, answer_type, url=url,
                               extra_lines=extract_jsonld(page["html"]))

    def _depth(self, question, entity, st) -> dict:
        """
        Retrieval in depth behind the direct answer (Brain-style, over the web): ranked
        evidence passages from every page read (+ snippets), the sources consulted, and
        related facts already in memory. Deterministic; no model, no generation.
        """
        from .candidates import main_entity, rank_passages
        results = st["results"]
        extra = 0
        for i, r in sorted(enumerate(results), key=lambda x: -x[1].get("trust", 0.5)):
            if extra >= self.depth_pages:
                break
            if i in st["opened"]:
                continue
            st["opened"].add(i)
            page = self.web.fetch(r["url"])
            if page.get("html"):
                st["docs"].append({"url": r["url"], "domain": r["domain"], "title": r.get("title", ""),
                                   "trust": r.get("trust", 0.5), "text": extract_main_text(page["html"], r["url"])})
            extra += 1
        results = results + self._session_results(question, results)
        snippet_docs = [{"url": r["url"], "domain": r["domain"], "title": r.get("title", ""),
                         "trust": r.get("trust", 0.5), "text": r.get("snippet", "")} for r in results]
        passages = rank_passages(question, st["docs"] + snippet_docs)
        if not st["docs"]:  # answered from memory: retrieve what was read before, locally, no web
            passages = self.store.local_passages(question) or passages
        sources = [{"title": r.get("title", ""), "url": r["url"], "domain": r["domain"],
                    "trust": r.get("trust", 0.5), "read": i in st["opened"],
                    "session": bool(r.get("session"))} for i, r in enumerate(results)]
        related = self.store.related(entity or main_entity(question), exclude_question=question)
        return {"passages": passages, "sources": sources, "related": related,
                "n_pages_read": len(st["docs"])}

    # ── session layer: "more results from here" ──────────────────────────
    def _session_results(self, question, results) -> list[dict]:
        """Later turns of a chat also search the sources this session asked for more of."""
        if not self.session_more or not hasattr(self.web, "search_site"):
            return []
        have = {r["url"] for r in results}
        extra = []
        for dom in self.session_more[-1:]:
            for r in self.web.search_site(dom, question)[:2]:
                if r["url"] not in have:
                    extra.append(dict(r, trust=self._trust(dom)["combined"], session=True))
        return extra

    def more_from(self, domain: str, question: str, pages: int = 2) -> dict:
        """The 'more results from here' button: read more of one source now and in later turns of this chat."""
        from .candidates import main_entity, rank_passages
        if domain not in self.session_more:
            self.session_more.append(domain)
        results = self.web.search_site(domain, question) if hasattr(self.web, "search_site") else []
        if not results:  # backends without site: search (Wikipedia API): keep that source's normal results
            results = [r for r in self.web.search(question) if r["domain"] == domain]
        trust = self._trust(domain)
        docs = []
        for r in results[:pages]:
            page = self.web.fetch(r["url"])
            if page.get("html"):
                docs.append({"url": r["url"], "domain": domain, "title": r.get("title", ""),
                             "trust": trust["combined"], "text": extract_main_text(page["html"], r["url"])})
        docs += [{"url": r["url"], "domain": domain, "title": r.get("title", ""), "trust": trust["combined"],
                  "text": r.get("snippet", "")} for r in results]
        passages = rank_passages(question, docs, k=6, per_source=3)
        self.store.add_passages(passages, main_entity(question), question)
        return {"domain": domain, "trust": trust, "passages": passages,
                "sources": [{"title": r.get("title", ""), "url": r["url"], "domain": domain} for r in results]}

    # ── best guess + explanation ─────────────────────────────────────────
    def _note_guess(self, st, d):
        """A learned policy that declines to commit still names its best candidate (G2 v2 meta)."""
        m = d.meta
        if "argmax_value" not in m or not st["spans"] or m.get("argmax", -1) >= len(st["spans"]):
            return
        if st["guess"] is None or m["gate"] > (st["guess"]["p"] or 0.0):
            sp = st["spans"][m["argmax"]]
            st["guess"] = _guess(sp, m["gate"], st["phase"] == "results_snip")

    def _final_guess(self, st, outcome) -> dict | None:
        """What a low-confidence card shows: the held value, else the policy's best, else the top candidate."""
        if st["held"] and st["phase"] != "store_hit":
            return _guess(st["held"], outcome["p"], st["held"].get("from_snippet", False))
        if outcome["reason"] == "low_confidence" and st["phase"] == "store_hit" and st["store"]:
            f = st["store"][0]
            return {"value": f["value"], "p": outcome["p"], "url": f["source_url"], "domain": f["domain"],
                    "context": f["context"], "parts": {}, "from_snippet": False}
        if st["guess"]:
            return st["guess"]
        lists = [s for s in (st["spans"], st["snip_spans"]) if s]
        if lists and lists[0][0].get("score", 0.0) >= MIN_GUESS_SCORE:  # a junk top span is not a guess
            return _guess(lists[0][0], None, lists[0] is st["snip_spans"])
        return None

    def _explain(self, st, outcome) -> dict:
        pol = self.policy
        calibrated = bool(getattr(pol, "calibrated", False))
        bar = float(getattr(pol, "tau", CONFIDENT_P)) if calibrated else CONFIDENT_P
        tier = outcome["tier"]
        if outcome["answered"]:
            shown = {"value": outcome["value"], "p": outcome["p"], "url": outcome["source_url"],
                     "domain": domain_of(outcome["source_url"] or ""), "context": outcome["context"],
                     "parts": (st["held"] or {}).get("parts", {}) if not outcome["from_store"] else {}}
        else:
            shown = outcome["guess"] or {}
        steps = [_event_text(e) for e in st["events"]]
        p = shown.get("p")
        if tier == "confident":
            steps.append(f"Answered: confidence {p:.0%}, at or above my bar of {max(bar, CONFIDENT_P):.0%}")
        elif tier == "low_confidence" and p is not None:
            steps.append(f"Not confident: {p:.0%} is below my bar of {max(bar, CONFIDENT_P):.0%}, so this is a best guess")
        elif tier == "low_confidence":
            steps.append("Not confident: no candidate cleared the bar; this is the top-ranked value, unchecked")
        else:
            steps.append("Nothing I read answers this; the evidence I found is below")
        # the candidates it chose between, and why the value and the confidence came out as they did
        dec = next((d for d in reversed(st["decisions"]) if "top3" in d.meta
                    and (outcome["answered"] or d.meta.get("gate") == p)), None) or \
            next((d for d in reversed(st["decisions"]) if "top3" in d.meta), None)
        if dec is not None:
            cands = [{"value": v, "p": pr} for _, v, pr in dec.meta["top3"]]
            why_conf = {"kind": "log-odds (pushes toward / away from right)",
                        "items": dec.meta.get("gate_weights", []) + [["baseline", dec.meta.get("gate_bias", 0.0)]]}
        else:
            src = st["spans"] or st["snip_spans"]
            cands = [{"value": c["value"], "score": c["score"]} for c in src[:3]]
            h = st["held"] or {}
            items = [["lexical match", h.get("score")], ["lead over the runner-up", h.get("margin")]] if h else []
            if outcome.get("verified"):
                items.append(["a second source agreed", "+0.25"])
            why_conf = {"kind": pol.confidence_kind if hasattr(pol, "confidence_kind") else "score",
                        "items": [i for i in items if i[1] is not None]}
        from .candidates import PART_LABELS
        why_value = sorted(([PART_LABELS.get(k, k), v] for k, v in (shown.get("parts") or {}).items()),
                           key=lambda x: -abs(x[1]))
        sources, seen = [], set()
        held = st["held"] if outcome["answered"] and not outcome["from_store"] else None
        snippet_agree = [d for d in ((held or {}).get("domains") or []) if d != shown.get("domain")]
        for role, dom, url in (("answer", shown.get("domain"), shown.get("url")),
                               ("agrees" if outcome.get("verified") else "checked",
                                (st["verify_by"] or {}).get("domain"), None),
                               *(("agrees", d, None) for d in snippet_agree[:3])):
            if dom and dom not in seen:
                seen.add(dom)
                sources.append({"role": role, "domain": dom, "url": url, "trust": self._trust(dom)})
        for d in st["docs"]:
            if d["domain"] not in seen:
                seen.add(d["domain"])
                sources.append({"role": "read", "domain": d["domain"], "url": d["url"], "trust": self._trust(d["domain"])})
        return {"tier": tier, "value": shown.get("value"), "confidence": p, "calibrated": calibrated,
                "confidence_kind": getattr(pol, "confidence_kind", "score"), "bar": round(max(bar, CONFIDENT_P), 3),
                "context": shown.get("context"), "steps": steps, "candidates": cands,
                "why_value": why_value, "why_confidence": why_conf, "sources": sources}

    def _verify(self, st, question, answer_type) -> bool:
        """
        Deterministic. Free first: does a snippet from ANOTHER domain carry the same value?
        Otherwise open the most query-relevant unopened result and look for it there.
        """
        held = st["held"]
        for sp in st["snip_spans"]:
            others = [dom for dom in sp.get("domains", []) if dom != held["domain"]]
            if is_correct(sp["value"], [held["value"]], answer_type) and others:
                st["verify_by"] = {"domain": others[0], "how": "snippet"}
                return True
        q = set(content_words(question))
        best, best_s = None, -1.0
        for i, r in enumerate(st["results"]):
            if i in st["opened"] or domain_of(r["url"]) == st["held"]["domain"]:
                continue
            s = len(q & set(norm_text(f"{r['title']} {r['snippet']}").split())) + r.get("trust", 0.5)
            if s > best_s:
                best, best_s = i, s
        if best is None:
            return False
        st["opened"].add(best)
        spans = self._page_spans(st["results"][best], question, answer_type, st)
        st["verify_by"] = {"domain": st["results"][best]["domain"], "how": "page"}
        return any(is_correct(s["value"], [held["value"]], answer_type) for s in spans[:10])

    # ── compare = composed fact cards ────────────────────────────────────
    def run_compare(self, task: dict) -> dict:
        cells, table = [], {}
        for item in task["items"]:
            table[item] = {}
            for att in task["attributes"]:
                q = att["template"].format(item=item)
                res = self.run_fact(q, att["answer_type"], entity=item, attribute=att["name"],
                                    task_id=task["id"])
                res["item"], res["attribute"], res["question"] = item, att["name"], q
                table[item][att["name"]] = res
                cells.append(res)
        return {"cells": cells, "table": table}

    # ── watch = re-run a fact with the network forced, compare to last value ──
    def run_watch(self, watch: dict) -> dict:
        res = self.run_fact(watch["question"], watch["answer_type"], entity=watch["entity"],
                            attribute=watch["attribute"], store_answer=True)
        new, old = res["value"], watch["last_value"]
        cond = __import__("json").loads(watch["condition"] or "{}")
        fired = False
        if res["answered"]:
            if cond.get("op") in ("lt", "gt"):
                v = parse_number(new)
                if v is not None:
                    fired = v < cond["value"] if cond["op"] == "lt" else v > cond["value"]
            else:
                fired = old is not None and norm_text(new) != norm_text(old)
            self.store.update_watch(watch["id"], new)
        return {"watch_id": watch["id"], "question": watch["question"], "old": old, "new": new,
                "fired": fired, "result": res}


def _compact(obs: dict) -> dict:
    """What gets logged per step: enough to re-render the prompt / re-train a head."""
    lists = {}
    for name in set(obs["pointer"].values()):
        lists[name] = obs["lists"].get(name, [])
    return {"question": obs["question"], "answer_type": obs["answer_type"], "allowed": obs["allowed"],
            "pointer": obs["pointer"], "lists": lists, "held": obs["held"], "verified": obs["verified"],
            "history": obs["history"], "opened": sorted(obs["opened"])}


def answer_tier(res: dict) -> str:
    """confident | low_confidence | none (pre-registered 2026-10-08, CONFIDENT_P)."""
    if res["answered"] and res["p"] >= CONFIDENT_P:
        return "confident"
    if res["answered"] or (res.get("guess") and res["guess"].get("value")):
        return "low_confidence"
    return "none"


def _guess(span: dict, p, from_snippet: bool) -> dict:
    return {"value": span["value"], "p": p, "url": span.get("url"), "domain": span.get("domain") or domain_of(span.get("url", "")),
            "context": span.get("context", ""), "parts": span.get("parts", {}), "from_snippet": bool(from_snippet)}


def _n(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _event_text(e: dict) -> str:
    k = e["kind"]
    if k == "memory":
        return f"Found {e['n']} matching fact(s) in your memory"
    if k == "search":
        doms = ", ".join(e["domains"][:4]) + (f" +{len(e['domains']) - 4} more" if len(e["domains"]) > 4 else "")
        return f"Searched ({e['backend']}) for \"{e['query']}\": {e['n']} results from {len(e['domains'])} sites ({doms})"
    if k == "snippets":
        return f"Read {_n(e['n'], 'candidate value')} straight off the result snippets (no page opened yet)"
    if k == "open":
        return f"Opened {e['domain']}: " + (_n(e["n"], "candidate value") if e["n"] else "nothing usable")
    if k == "extract":
        return f"Picked {e['value']} from {e['domain']} (from the {e['from']})"
    if k == "verify":
        if e["ok"]:
            return f"Cross-checked: {e.get('domain')} gives the same value (from its {e.get('how', 'page')})"
        return "Cross-checked: no second source gave the same value" + (f" ({e['domain']} did not)" if e.get("domain") else "")
    return k


# ── answer cards (deterministic renderers, no generation) ─────────────────
def render_card(question: str, res: dict) -> str:
    ex = res.get("explain") or {}
    if not res["answered"]:
        g = res.get("guess") or {}
        if g.get("value"):
            conf = f"confidence {g['p']:.0%}" if g.get("p") is not None else "no confidence estimate"
            return (f"**{question}**\n  Low confidence in my results: best guess **{g['value']}** ({conf}, "
                    f"not committed; {res['reason']})\n  Source: {g.get('url')}")
        return f"**{question}**\n  I couldn't verify an answer ({res['reason']})."
    src = domain_of(res["source_url"] or "")
    tag = "verified by a 2nd source" if res.get("verified") else "single source"
    store = ", from memory" if res.get("from_store") else ""
    low = "Low confidence in my results: " if ex.get("tier") == "low_confidence" else ""
    return (f"**{question}**\n  {low}**{res['value']}**  (confidence {res['p']:.0%}, {tag}{store})\n"
            f"  \"{(res['context'] or '')[:200]}\"\n  Source: {res['source_url']} ({src})")


def render_table(task: dict, out: dict) -> str:
    atts = [a["name"] for a in task["attributes"]]
    lines = ["| item | " + " | ".join(atts) + " |", "|---" * (len(atts) + 1) + "|"]
    for item, row in out["table"].items():
        cells = []
        for a in atts:
            r = row[a]
            cells.append(f"{r['value']} ({domain_of(r['source_url'] or '')})" if r["answered"] else "n/a")
        lines.append(f"| {item} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
