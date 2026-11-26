"""
Consolidation (round 5): what several sources say -> one answer with a 0-10 confidence, every
point itemized. Plain arithmetic, no model, no training: the READER (readers.py) only says which
candidate values answer the question (r in [0, 1]); trust, agreement, conflict and question type
are weighed here, where they can be recomputed with or without the user's personal scores.

    clusters    equivalent values merged ("Alex Palou" = "Álex Palou", "5 March 2026" = "2026-03-05")
    families    copies of one source count once (Wikipedia + mirrors); a family's trust = its best domain
    choice      argmax  r x (1 - TRUST_MIX + TRUST_MIX x top_trust / 10)   the reader leads, trust tilts
    confidence  top_trust                         the most trusted source stating the value
                + 1 per other independent family at >= 7 that agrees (max +2)
                - 2 if a family at >= 7 states a different value the reader also rated (r >= 0.2)
                - 2 / - 1 if the reader itself is unsure (r < 0.3 / r < 0.6)
                - the question-type penalty (news 2, encyclopedic 1, general information 0)
                clamped to 0-10; banded like trust (9-10 high, 7-8 good, 5-6 low, < 5 sceptical)
"""

from .metrics import is_correct
from .qtype import PENALTY
from .registry import BAND_LABEL, band
from .web import domain_of

STRONG = 7.0
AGREE_MAX = 2.0
CONFLICT_PENALTY = 2.0
CONFLICT_MIN_R = 0.2
TRUST_MIX = 0.5
MIN_R = 0.05          # below this the reader found nothing that answers the question


def same_value(a: str, b: str, answer_type: str) -> bool:
    return is_correct(a, [b], answer_type) or is_correct(b, [a], answer_type)


def cluster(pools: list[dict], answer_type: str) -> list[dict]:
    """
    pools: [{"name", "cands": [...], "r": [...]}] -> clusters. Within one pool the r of equivalent
    spans add up (one distribution); across pools a cluster keeps its best pool's r.
    """
    clusters: list[dict] = []
    for pool in pools:
        per: dict[int, float] = {}
        for c, r in zip(pool["cands"], pool["r"]):
            for i, cl in enumerate(clusters):
                if same_value(cl["value"], c["value"], answer_type):
                    break
            else:
                clusters.append({"value": c["value"], "r": 0.0, "support": {}, "best_r_member": -1.0})
                i = len(clusters) - 1
            cl = clusters[i]
            per[i] = per.get(i, 0.0) + float(r)
            if r > cl["best_r_member"]:
                cl["value"], cl["best_r_member"] = c["value"], float(r)
            for url in c.get("urls") or [c.get("url")]:
                if not url:
                    continue
                dom = domain_of(url)
                s = cl["support"].setdefault(dom, {"domain": dom, "url": url, "context": ""})
                if url == c.get("url") and not s["context"]:
                    s["context"] = c.get("context", "")   # other sources' text is filled in from their snippets
        for i, r in per.items():
            clusters[i]["r"] = max(clusters[i]["r"], min(1.0, r))
    return clusters


def _families(cl: dict, trust_fn) -> list[dict]:
    fam: dict[str, dict] = {}
    for dom, s in cl["support"].items():
        t = trust_fn(dom)
        f = fam.get(t["family"])
        if f is None or t["effective"] > f["trust"]["effective"]:
            fam[t["family"]] = {"family": t["family"], "domain": dom, "url": s["url"], "context": s["context"], "trust": t}
    return sorted(fam.values(), key=lambda f: -f["trust"]["effective"])


def consolidate(pools: list[dict], answer_type: str, qtype: str, trust_fn) -> dict:
    """trust_fn(domain) -> registry trust record. Returns the winner, confidence, items and conflicts."""
    clusters = cluster(pools, answer_type)
    scored = []
    for cl in clusters:
        fams = _families(cl, trust_fn)
        top = fams[0]["trust"]["effective"] if fams else 0.0
        scored.append(dict(cl, families=fams, top_trust=top, key=cl["r"] * (1 - TRUST_MIX + TRUST_MIX * top / 10)))
    scored.sort(key=lambda c: -c["key"])
    if not scored or scored[0]["r"] < MIN_R or not scored[0]["families"]:
        return {"value": None, "confidence": None, "band": "none", "band_label": BAND_LABEL["none"], "qtype": qtype,
                "items": [], "conflicts": [], "families": [], "candidates": _cands(scored)}
    win = scored[0]
    fams = win["families"]
    items = [[f"most trusted source stating it: {fams[0]['domain']} ({fams[0]['trust']['category']})", round(win["top_trust"], 2)]]
    agree = [f for f in fams[1:] if f["trust"]["effective"] >= STRONG]
    if agree:
        n = min(AGREE_MAX, len(agree))
        items.append([f"{len(agree)} more independent source(s) at 7+ agree: " + ", ".join(f["domain"] for f in agree[:3]), n])
    conflicts = []
    for other in scored[1:]:
        if other["r"] >= CONFLICT_MIN_R and other["families"] and other["top_trust"] >= STRONG:
            f = other["families"][0]
            conflicts.append({"value": other["value"], "domain": f["domain"], "url": f["url"], "context": f["context"],
                              "trust": f["trust"], "r": round(other["r"], 3)})
    if conflicts:
        items.append(["a source at 7+ says something else: " + "; ".join(f"{c['domain']} says {c['value']}" for c in conflicts[:2]),
                      -CONFLICT_PENALTY])
    if win["r"] < 0.3:
        items.append([f"the reader is unsure this answers the question (p {win['r']:.2f})", -2.0])
    elif win["r"] < 0.6:
        items.append([f"the reader is not certain this answers the question (p {win['r']:.2f})", -1.0])
    pen = PENALTY.get(qtype, 1.0)
    if pen:
        items.append([f"{qtype.replace('_', ' ')} question", -pen])
    conf = round(max(0.0, min(10.0, sum(v for _, v in items))), 1)
    return {"value": win["value"], "confidence": conf, "band": band(conf), "band_label": BAND_LABEL[band(conf)],
            "qtype": qtype, "items": items, "conflicts": conflicts, "families": fams, "reader_p": round(win["r"], 3),
            "candidates": _cands(scored)}


def _cands(scored: list[dict]) -> list[dict]:
    return [{"value": c["value"], "r": round(c["r"], 3), "top_trust": c.get("top_trust"),
             "sources": [f["domain"] for f in c.get("families", [])][:4]} for c in scored[:4]]


def divergence(personal: dict, system: dict, answer_type: str) -> dict | None:
    """Did the user's personal scores change the answer or its band? Then the card must say so."""
    if personal["value"] is None and system["value"] is None:
        return None
    changed_value = (personal["value"] is None) != (system["value"] is None) or (
        personal["value"] is not None and not same_value(personal["value"], system["value"], answer_type))
    if changed_value or personal["band"] != system["band"]:
        return {"changed_value": changed_value, "changed_band": personal["band"] != system["band"],
                "system_value": system["value"], "system_confidence": system["confidence"], "system_band": system["band"]}
    return None
