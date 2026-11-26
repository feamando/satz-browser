"""
Source trust, 0-10 (round 5, 2026-10-09). Replaces the measured log-odds system layer of round 4.

    system     hand-scored registry (config/planck3/source_registry.json): category scores from the
               owner's rubric, explicit per-domain scores, and FAMILIES (Wikipedia + its mirrors are one
               source: agreement inside a family counts once). Unknown domains: 5, flagged "unscored".
    personal   the user's own score per domain (trust more / less buttons), default = system.
    effective  0.7 x system + 0.3 x personal: a personal view moves a source by at most 3 points,
               so it can tilt the weighing but cannot turn a 4 into a 9 (no echo chamber). A personal
               score 3+ points from the system's is a CONFLICT and is shown on the card.

Bands (owner): 9-10 high trust / high confidence; 7-8 good, might have bias; 5-6 low, frequent bias;
below 5 treat with scepticism, can be propaganda. The same scale is used for answer confidence.
"""

from functools import lru_cache
from pathlib import Path

from .util import REPO_ROOT, read_json

REGISTRY = REPO_ROOT / "config" / "planck3" / "source_registry.json"
PERSONAL_WEIGHT = 0.3       # owner: personal weighting influences trust by at most 30%
CONFLICT_GAP = 3.0          # |personal - system| >= this is highlighted
PERSONAL_STEP = 2.0         # one "trust more / less" click on the 0-10 scale


def band(score: float | None) -> str:
    if score is None:
        return "none"
    if score >= 9:
        return "high"
    if score >= 7:
        return "good"
    if score >= 5:
        return "low"
    return "sceptical"


BAND_LABEL = {"high": "High trust", "good": "Good, might have bias", "low": "Low, frequent bias",
              "sceptical": "Treat with scepticism", "none": "No answer"}


class Registry:
    def __init__(self, path: str | Path | None = None):
        data = read_json(Path(path) if path else REGISTRY)
        self.categories = data["categories"]
        self.domains = data["domains"]
        self.suffix_rules = sorted(data.get("suffix_rules", []), key=lambda r: -len(r["suffix"]))  # most specific first
        self.keyword_rules = data.get("keyword_rules", [])
        self.unscored = data.get("unscored", {"score": 5, "label": "unscored"})
        self.as_of = data.get("as_of")

    @lru_cache(maxsize=20000)
    def lookup(self, domain: str) -> dict:
        """{score, category, family, why, rubric, scored} for a domain (subdomains fall back to parents)."""
        d = (domain or "").lower().removeprefix("www.")
        entry, matched = None, None
        parts = d.split(".")
        for i in range(len(parts) - 1):          # exact, then parent domains: news.bbc.co.uk -> bbc.co.uk
            cand = ".".join(parts[i:])
            if cand in self.domains:
                entry, matched = self.domains[cand], cand
                break
        if entry is None:
            for rule in self.suffix_rules:
                if d.endswith(rule["suffix"]) or d == rule["suffix"].lstrip("."):
                    # a suffix names a CATEGORY, not a source: every .gov site is its own family
                    entry, matched = {k: v for k, v in rule.items() if k != "suffix"}, d
                    break
        if entry is None:
            for rule in self.keyword_rules:      # rubric-derived: "airport", "museum" ... in the domain name
                if rule["contains"] in d:
                    entry, matched = {"category": rule["category"]}, d
                    break
        if entry is None:
            return {"score": float(self.unscored["score"]), "category": "unscored", "family": d, "why": self.unscored["label"],
                    "rubric": "default", "scored": False, "matched": None}
        cat = self.categories.get(entry.get("category"), {})
        score = entry.get("score", cat.get("score", self.unscored["score"]))
        return {"score": float(score), "category": entry.get("category"), "family": entry.get("family") or matched,
                "why": entry.get("why") or cat.get("what", ""), "rubric": cat.get("rubric", ""), "scored": True,
                "matched": matched}


@lru_cache(maxsize=4)
def default_registry(path: str | None = None) -> Registry:
    return Registry(path)


def effective(system: float, personal: float | None) -> float:
    p = system if personal is None else max(0.0, min(10.0, personal))
    return round((1 - PERSONAL_WEIGHT) * system + PERSONAL_WEIGHT * p, 2)


def trust_record(domain: str, personal: float | None = None, registry: Registry | None = None) -> dict:
    """Everything a card shows about one source. 'combined' (0-1) keeps older callers working."""
    reg = registry or default_registry()
    info = reg.lookup(domain)
    s = info["score"]
    e = effective(s, personal)
    conflict = personal is not None and abs(personal - s) >= CONFLICT_GAP
    return {"domain": domain, "system": s, "personal": personal, "effective": e, "combined": round(e / 10, 3),
            "band": band(e), "band_label": BAND_LABEL[band(e)], "category": info["category"], "family": info["family"],
            "why": info["why"], "rubric": info["rubric"], "scored": info["scored"], "conflict": conflict}
