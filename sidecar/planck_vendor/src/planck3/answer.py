"""
The round 5 answer pipeline (the product path): read -> weigh -> write, no retraining in the loop.

    search    one query (ddgs / Brave / SearXNG / Wikipedia), every result tagged with its 0-10 trust
    read      snippet candidates first; if the weighed confidence is under 7, read up to MAX_PAGES
              pages (on-subject titles first, then most trusted) and read again
    weigh     consolidate.py: clusters, families, itemized 0-10 confidence; computed twice, with and
              without the user's personal scores, so a personal tilt that changes the answer is shown
    write     writer.py: template / small fine-tuned writer / Gemma, always faithfulness-checked
    depth     ranked evidence passages + sources, stored in the user's local graph

Everything the card shows is in the returned record, so an answer can be audited after the fact.
"""

import time

from .candidates import main_entity, rank_passages, snippet_candidates, span_candidates, title_aboutness
from .consolidate import consolidate, divergence
from .qtype import classify
from .web import extract_jsonld, extract_main_text

MAX_PAGES = 2
OPEN_BELOW = 7.0     # read pages when the snippets alone weigh in under "good"


class Answerer:
    def __init__(self, web, store, reader, writer, max_pages: int = MAX_PAGES, use_personal: bool = True,
                 store_answer: bool = True, personal_override=None, open_below: float = OPEN_BELOW,
                 keep_pools: bool = False):
        self.web, self.store, self.reader, self.writer = web, store, reader, writer
        self.open_below = open_below    # round 11: > 10 = always read the pages (the evidence check)
        self.keep_pools = keep_pools    # round 11: return what the reader saw (diagnosis dumps)
        self.personal_override = personal_override  # (domain, system) -> personal score; evaluation profiles
        self.max_pages = max_pages
        self.use_personal = use_personal
        self.store_answer = store_answer
        self.session_more: list[str] = []   # "more results from here": retrieval only, this chat

    def _trust(self, personal: bool):
        cache = {}

        def fn(domain):
            if domain not in cache:
                if personal and self.use_personal and self.personal_override is not None:
                    from .registry import trust_record
                    sysscore = self.store.registry.lookup(domain)["score"]
                    cache[domain] = trust_record(domain, self.personal_override(domain, sysscore), self.store.registry)
                else:
                    cache[domain] = self.store.trust(domain, personal=personal and self.use_personal)
            return cache[domain]
        return fn

    def run_fact(self, question: str, answer_type: str | None = None, **_kw) -> dict:
        """Chat compatibility: ChatSession calls run_fact on whatever answers its turns."""
        return self.run(question, answer_type)

    def run(self, question: str, answer_type: str | None = None, task_id: str | None = None) -> dict:
        from .chat import infer_answer_type
        t_all = time.perf_counter()
        at = answer_type or infer_answer_type(question)
        qt = classify(question)
        calls0 = {k: self.web.calls.get(k, 0) for k in ("search", "fetch")}
        timing = {"search_ms": 0.0, "fetch_ms": 0.0, "read_ms": 0.0, "write_ms": 0.0}
        steps = []
        t0 = time.perf_counter()
        results = self.web.search(question)
        on_topic = getattr(self.web, "last_on_topic", None)
        for dom in self.session_more[-1:]:
            if hasattr(self.web, "search_site") and not any(r["domain"] == dom for r in results):
                results = results + [dict(r, session=True) for r in self.web.search_site(dom, question)[:2]]
        timing["search_ms"] = (time.perf_counter() - t0) * 1000
        tp, ts = self._trust(True), self._trust(False)
        for r in results:
            r["trust_record"] = tp(r["domain"])
            r["trust"] = r["trust_record"]["combined"]
        steps.append(f"Searched ({getattr(self.web, 'last_backend', None) or 'search'}) for \"{question}\": "
                     f"{len(results)} results from {len({r['domain'] for r in results})} sites")
        snippets = {r["url"]: r.get("snippet", "") for r in results}
        pools, docs = [], []
        if results:
            cands = snippet_candidates(question, results, at)
            if cands:
                pools.append({"name": "snippets", "cands": cands, "snippet": True})
                steps.append(f"Read {len(cands)} candidate values off the snippets ({qt.replace('_', ' ')} question)")
        self._read(question, at, pools, timing)
        cons = consolidate(pools, at, qt, tp)
        opened = []
        if results and (cons["value"] is None or cons["confidence"] < self.open_below):
            order = sorted(results, key=lambda r: (-(title_aboutness(question, r.get("title", "")) >= 0.5),
                                                   -r["trust_record"]["effective"]))
            for r in order[: self.max_pages]:
                t0 = time.perf_counter()
                page = self.web.fetch(r["url"])
                timing["fetch_ms"] += (time.perf_counter() - t0) * 1000
                opened.append(r["domain"])
                if not page.get("html"):
                    steps.append(f"Opened {r['domain']}: could not read it")
                    continue
                text = extract_main_text(page["html"], r["url"])
                docs.append({"url": r["url"], "domain": r["domain"], "title": r.get("title", ""), "trust": r["trust"], "text": text})
                pc = span_candidates(question, text, at, url=r["url"], extra_lines=extract_jsonld(page["html"]))
                steps.append(f"Opened {r['domain']} ({r['trust_record']['effective']:.0f}/10): {len(pc)} candidate values")
                if pc:
                    pools.append({"name": f"page:{r['domain']}", "cands": pc, "snippet": False})
            self._read(question, at, pools, timing, only_new=True)
            cons = consolidate(pools, at, qt, tp)
        sys_cons = consolidate(pools, at, qt, ts)
        div = divergence(cons, sys_cons, at) if self.use_personal else None
        if cons["value"] is None:
            steps.append("Nothing I read answers this; the evidence I found is below")
            wr = {"writer": "none", "text": "I couldn't find an answer in what I read. The evidence I found is below.",
                  "sources": [], "faithful": True, "problems": [], "fallback": False, "ms": 0.0}
        else:
            steps.append(f"Weighed {len(cons['families'])} independent source(s) for {cons['value']}: "
                         f"confidence {cons['confidence']:.1f}/10 ({cons['band_label']})")
            wr = self.writer.write(question, at, cons, snippets)
            steps.append(f"Wrote the answer ({wr['writer']}" + (", fell back to the template: " + "; ".join(wr["problems"][:2])
                                                                 if wr.get("fallback") else "") + ")")
        timing["write_ms"] = wr.get("ms", 0.0)
        if div:
            steps.append("Your source preferences changed this answer: system-only answer "
                         f"{div['system_value']} ({div['system_confidence']}/10)")
        passages = rank_passages(question, docs + [{"url": r["url"], "domain": r["domain"], "title": r.get("title", ""),
                                                    "trust": r["trust"], "text": r.get("snippet", "")} for r in results])
        sources = [{"title": r.get("title", ""), "url": r["url"], "domain": r["domain"], "trust": r["trust"],
                    "trust_record": r["trust_record"], "read": r["domain"] in opened, "session": bool(r.get("session"))}
                   for r in results]
        if self.store_answer:
            subject = main_entity(question)
            self.store.log_query(question, subject)
            self.store.add_passages(passages, subject, question)
            if cons["value"] is not None and cons["confidence"] >= OPEN_BELOW and cons["families"]:
                f = cons["families"][0]
                self.store.add_fact(question=question, value=cons["value"], answer_type=at, source_url=f["url"],
                                    domain=f["domain"], context=f["context"], p=cons["confidence"] / 10,
                                    verified=len(cons["families"]) > 1, task_id=task_id)
        timing["total_ms"] = (time.perf_counter() - t_all) * 1000
        explain = {"pipeline": "answer", "tier": cons["band"], "value": cons["value"], "confidence10": cons["confidence"],
                   "confidence": None if cons["confidence"] is None else cons["confidence"] / 10,
                   "band": cons["band"], "band_label": cons["band_label"], "qtype": qt, "items": cons["items"],
                   "conflicts": cons["conflicts"], "candidates": cons["candidates"], "steps": steps,
                   "reader": self.reader.name, "reader_p": cons.get("reader_p"), "writer": wr["writer"],
                   "writer_faithful": wr["faithful"], "writer_problems": wr.get("problems", []),
                   "writer_fallback": wr.get("fallback", False), "writer_generated": wr.get("generated"),
                   "writer_tries": wr.get("tries", 0), "writer_first_try_faithful": wr.get("first_try_faithful"),
                   "writer_template": wr.get("template"), "search_on_topic": on_topic,
                   "read_pools": len(pools), "read_cands": sum(min(len(p["cands"]), getattr(self.reader, "max_cands", None)
                                                                   or len(p["cands"])) for p in pools),
                   "divergence": div,
                   "sources": [{"role": "states it" if i == 0 else "agrees", "domain": f["domain"], "url": f["url"],
                                "trust": f["trust"]} for i, f in enumerate(cons["families"])]
                   + [{"role": "says " + str(c["value"]), "domain": c["domain"], "url": c["url"], "trust": c["trust"]}
                      for c in cons["conflicts"]]}
        return {"question": question, "answer_type": at, "answered": cons["value"] is not None, "value": cons["value"],
                "p": explain["confidence"] or 0.0, "answer_text": wr["text"], "writer_sources": wr["sources"],
                "explain": explain, "tier": cons["band"], "depth": {"passages": passages, "sources": sources, "related":
                self.store.related(main_entity(question), exclude_question=question), "n_pages_read": len(docs)},
                "timing": {k: round(v, 1) for k, v in timing.items()},
                "search_calls": self.web.calls.get("search", 0) - calls0["search"],
                "fetch_calls": self.web.calls.get("fetch", 0) - calls0["fetch"],
                "web_calls": sum(self.web.calls.get(k, 0) - calls0[k] for k in calls0),
                "steps": len(steps), "trajectory": [], "usage": dict(getattr(self.reader, "usage", {})),
                "pools": [{"name": p["name"], "snippet": p.get("snippet", False), "r": [round(float(x), 4) for x in p["r"][:32]],
                           "cands": [{"value": c["value"], "context": (c.get("context") or "")[:240], "score": c.get("score"),
                                      "domains": (c.get("domains") or [])[:3]} for c in p["cands"][:32]]}
                          for p in pools] if self.keep_pools else None}

    def _read(self, question, at, pools, timing, only_new=False):
        for pool in pools:
            if only_new and "r" in pool:
                continue
            t0 = time.perf_counter()
            pool["r"] = self.reader.read(question, at, pool)
            timing["read_ms"] += (time.perf_counter() - t0) * 1000

    def more_from(self, domain: str, question: str, pages: int = 2) -> dict:
        """'More results from here': read more of one source now, and search it in later turns."""
        if domain not in self.session_more:
            self.session_more.append(domain)
        results = self.web.search_site(domain, question) if hasattr(self.web, "search_site") else []
        if not results:
            results = [r for r in self.web.search(question) if r["domain"] == domain]
        trust = self.store.trust(domain)
        docs = []
        for r in results[:pages]:
            page = self.web.fetch(r["url"])
            if page.get("html"):
                docs.append({"url": r["url"], "domain": domain, "title": r.get("title", ""), "trust": trust["combined"],
                             "text": extract_main_text(page["html"], r["url"])})
        docs += [{"url": r["url"], "domain": domain, "title": r.get("title", ""), "trust": trust["combined"],
                  "text": r.get("snippet", "")} for r in results]
        passages = rank_passages(question, docs, k=6, per_source=3)
        self.store.add_passages(passages, main_entity(question), question)
        return {"domain": domain, "trust": trust, "passages": passages,
                "sources": [{"title": r.get("title", ""), "url": r["url"], "domain": domain} for r in results]}
