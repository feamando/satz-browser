"""
ROUND 4 (superseded 2026-10-09 by src/planck3/registry.py, hand-scored 0-10 + capped personal score).
Kept for `planck3.py trust build|show`: the MEASURED table is now an audit signal only (how often a
domain's snippet carried the right answer on encyclopedic training questions), never a trust score.

Source trust in three layers (2026-10-08). Every source an answer cites shows all three:

    system   the same for every user, and measured, not hand-picked: on the G2 training
             questions (known answers, disjoint from every benchmark), how often a domain's
             snippet carried the right answer when some snippet did.
             Shipped in git as config/planck3/source_trust.json (`planck3.py trust build`).
    user     this user's own evidence, kept in their private store: implicit (a value from
             the source was corroborated / a page had nothing usable) and explicit
             "trust more" / "trust less".
    session  this conversation only: "more results from here". Gone on "New chat".

The layers add in log-odds, so the card can show each one as a number:

    logit(trust) = logit(system) + user_shift + session_shift

    system         Beta mean of the shipped counts (unknown domain: Beta(1, 1) = 0.5)
    user_shift     how far this user's counts move the posterior away from the system prior
    session_shift  +SESSION_STEP per "more results from here" (capped at SESSION_MAX)
"""

import math
from pathlib import Path

from .util import REPO_ROOT, now_iso, read_json, read_jsonl, write_json

SYSTEM_TRUST = REPO_ROOT / "config" / "planck3" / "source_trust.json"
SYSTEM_MAX_STRENGTH = 20.0   # a system prior counts as at most 20 observations, so a user can outvote it
SYSTEM_MIN_N = 3             # fewer observations than this: no system opinion (0.5)
SESSION_STEP = 1.0
SESSION_MAX = 2.0


def logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def load_system(path: str | Path | None = None) -> dict[str, tuple[float, float]]:
    """{domain: (a, b)} from the shipped table; empty (everything 0.5) if it is not built yet."""
    p = Path(path) if path else SYSTEM_TRUST
    if not p.exists():
        return {}
    return {d: (float(v["a"]), float(v["b"])) for d, v in read_json(p).get("domains", {}).items()}


def layers(system: tuple[float, float] | None, user: tuple[float, float] | None,
           session_shift: float = 0.0) -> dict:
    """The three layers of one domain plus their log-odds contributions."""
    sa, sb = system or (1.0, 1.0)
    ua, ub = user or (1.0, 1.0)              # the store keeps Beta(1, 1) + this user's signals
    p_sys = sa / (sa + sb)
    p_user = (sa + ua - 1) / (sa + sb + ua + ub - 2)
    shift = max(-SESSION_MAX, min(SESSION_MAX, session_shift))
    w_sys, w_user = logit(p_sys), logit(p_user) - logit(p_sys)
    return {"system": round(p_sys, 3), "user": round(p_user, 3), "session": round(shift, 3),
            "combined": round(sigmoid(w_sys + w_user + shift), 3),
            "weights": {"system": round(w_sys, 3), "user": round(w_user, 3), "session": round(shift, 3)},
            "signals": {"system": round(sa + sb - 2, 1), "user": round(ua + ub - 2, 1)}}


def build_system(points_paths: list[Path], out: Path = SYSTEM_TRUST, min_n: int = SYSTEM_MIN_N) -> dict:
    """
    Snippet decision points only (several domains side by side, nothing chosen yet), and only
    those where SOME snippet carried the right answer: for each domain present, did its own
    snippet carry it? That is what trust is for here: when this source shows up, does reading it
    help? Page points are skipped (only the page that was read is in them, so they are biased),
    and questions with no right answer anywhere say nothing about any source.
    """
    stats: dict[str, list[int]] = {}
    files = []
    for path in points_paths:
        if not Path(path).exists():
            continue
        files.append(Path(path).name)
        for pt in read_jsonl(path):
            if pt.get("source", "snippet") != "snippet" or not any(pt["labels"]):
                continue
            has: dict[str, bool] = {}
            for c, ok in zip(pt["cands"], pt["labels"]):
                for d in c.get("domains") or []:
                    has[d] = has.get(d, False) or bool(ok)
            for d, ok in has.items():
                s = stats.setdefault(d, [0, 0])
                s[0] += 1
                s[1] += int(ok)
    domains = {}
    for d, (n, right) in sorted(stats.items(), key=lambda x: -x[1][0]):
        if n < min_n:
            continue
        a, b = 1.0 + right, 1.0 + n - right
        if a + b > SYSTEM_MAX_STRENGTH:
            k = SYSTEM_MAX_STRENGTH / (a + b)
            a, b = a * k, b * k
        domains[d] = {"a": round(a, 3), "b": round(b, 3), "n": n, "right": right, "rate": round(right / n, 3)}
    table = {"_note": "System layer of source trust (src/planck3/trust.py). Measured on the G2 training "
                      "questions (disjoint from every benchmark), never hand-edited. Counts are capped at "
                      f"{SYSTEM_MAX_STRENGTH:.0f} so a user's own signals can outvote it.",
             "built_at": now_iso(), "built_from": files, "min_n": min_n, "domains": domains}
    write_json(out, table)
    return table
