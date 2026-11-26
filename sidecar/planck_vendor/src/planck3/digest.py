"""
"For you": a digest from the user's own knowledge graph instead of an ad feed.

The graph grows with every question (passages + co-mention edges + interest log +
trust priors), so the digest gets MORE relevant with use, and it only ever draws
from sources the user trusts (earned trust or an explicit thumbs-up).

    build_digest   what you asked about (recency-weighted), what is adjacent to it,
                   facts gone stale that should be refreshed. Local only, no web.
    explore        the continuous-retrieval loop: search adjacent entities, keep only
                   results from trusted domains, read them into the graph.
"""

from .candidates import rank_passages
from .web import domain_of, extract_main_text

DEFAULT_MIN_TRUST = 0.6


def trusted_domains(store, min_trust: float = DEFAULT_MIN_TRUST) -> set[str]:
    """System layer (shipped, measured) + this user's layer, combined (src/planck3/trust.py)."""
    return {d for d in store.known_domains() if store.domain_prior(d) >= min_trust}


def build_digest(store, n_interests: int = 5, n_adjacent: int = 3, min_trust: float = DEFAULT_MIN_TRUST) -> dict:
    interests = store.interests(n_interests)
    asked = {e for e, _ in interests}
    sections = []
    for ent, score in interests:
        adj = []
        for other, w in store.adjacent(ent, n=n_adjacent, exclude=asked):
            ps = store.passages_about(other, k=1, min_trust=min_trust)
            adj.append({"entity": other, "weight": w, "passage": ps[0] if ps else None})
        sections.append({"entity": ent, "interest": round(score, 3),
                         "recent": store.passages_about(ent, k=2, min_trust=min_trust), "adjacent": adj})
    return {"interests": sections, "stale": store.stale_facts(), "watches": store.watches(),
            "trusted": sorted(trusted_domains(store, min_trust)), "graph": store.graph_stats()}


def explore(store, web, min_trust: float = DEFAULT_MIN_TRUST, max_entities: int = 5, pages_per_entity: int = 1) -> list[dict]:
    """Read adjacent entities from TRUSTED domains into the graph. Returns what was added."""
    trusted = trusted_domains(store, min_trust)
    if not trusted:
        return []
    interests = store.interests(max_entities)
    asked = {e for e, _ in interests}
    added = []
    for ent, _ in interests:
        for other, _w in store.adjacent(ent, n=1, exclude=asked):
            results = [r for r in web.search(other) if r["domain"] in trusted][:pages_per_entity]
            for r in results:
                page = web.fetch(r["url"])
                if not page.get("html"):
                    continue
                doc = {"url": r["url"], "domain": domain_of(r["url"]), "title": r.get("title", ""),
                       "trust": store.domain_prior(r["domain"]),
                       "text": extract_main_text(page["html"], r["url"])}
                ps = rank_passages(f"{other} {ent}", [doc], k=3, per_source=3)
                store.add_passages(ps, other, f"(explore) {other}")
                added.append({"entity": other, "via": ent, "url": r["url"], "passages": len(ps)})
            asked.add(other)
    return added


def render_digest(d: dict) -> str:
    g = d["graph"]
    lines = [f"# For you  ({g['facts']} facts · {g['passages']} passages · {g['entities']} entities · "
             f"{g['queries']} questions asked)", ""]
    if not d["interests"]:
        return "\n".join(lines + ["Nothing yet: ask a few questions first; the digest grows from them."])
    for s in d["interests"]:
        lines.append(f"## {s['entity'].title()}  (interest {s['interest']})")
        for p in s["recent"]:
            lines.append(f"- {p['text'][:240]}  _({p['domain']})_")
        if s["adjacent"]:
            lines.append("  Adjacent:")
            for a in s["adjacent"]:
                txt = f": {a['passage']['text'][:160]}  _({a['passage']['domain']})_" if a["passage"] else ""
                lines.append(f"  - **{a['entity'].title()}**{txt}")
        lines.append("")
    if d["stale"]:
        lines.append("## Due for a refresh")
        for f in d["stale"]:
            lines.append(f"- {f['question']}  (last answer: {f['value']})")
    lines.append(f"\nTrusted sources: {', '.join(d['trusted']) or 'none yet (sources earn trust as answers check out, or thumbs-up them)'}")
    return "\n".join(lines)
