"""
Readers (round 5): which candidate values ANSWER the question? A reader returns r in [0, 1] per
candidate of each pool (the snippet pool, then one pool per page read). It never sees trust: the
weighing in consolidate.py does that, so a user's source preferences cannot leak into reading.

    heuristic   lexical ranker scores, softmax (no model)
    planck      the G2 v2 choice head on frozen Planck 1.3 features (trained once on known answers;
                its answerability gate is NOT used: confidence is the itemized arithmetic now)
    gemma       Gemma 4 E4B picks the candidate (reference / teacher; too big for a phone)
    x-planck    round 6: Planck 1.3 fine-tuned once as a cross-encoder (xreader.py), question and
    x-hertz     evidence read together; same for Hertz 1.2
"""

import math
import time

import numpy as np

HEURISTIC_TEMP = 0.25


class HeuristicReader:
    name = "heuristic"
    kind = "local"

    def __init__(self):
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

    def read(self, question: str, answer_type: str, pool: dict) -> list[float]:
        sc = [c.get("score", 0.0) for c in pool["cands"]]
        if not sc:
            return []
        m = max(sc)
        z = [math.exp((x - m) / HEURISTIC_TEMP) for x in sc]
        s = sum(z)
        # a weak best match is not an answer however it compares to the rest
        cap = min(1.0, max(m, 0.0))
        return [cap * v / s for v in z]


class PlanckReader:
    name = "planck"
    kind = "local"

    def __init__(self, head_path: str, checkpoint: str | None = None, tokenizer: str | None = None):
        from .g2 import load_policy
        self.policy = load_policy(head_path, checkpoint=checkpoint, tokenizer=tokenizer)
        if not hasattr(self.policy, "_choice"):
            raise SystemExit(f"{head_path} is not a G2 v2 head (needs the choice head)")
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

    def read(self, question: str, answer_type: str, pool: dict) -> list[float]:
        cands = pool["cands"][:32]
        if not cands:
            return []
        obs = {"question": question, "answer_type": answer_type}
        pr, _gate = self.policy._choice(obs, cands, pool.get("snippet", False))
        return [float(x) for x in np.asarray(pr)] + [0.0] * (len(pool["cands"]) - len(cands))


READER_SYSTEM = """You read search evidence for a question and pick the candidate value that answers it.
Pick the candidate that actually answers the question, not one that merely repeats its words
(the subject itself, an unrelated year, a later or earlier event). If none answers it, k is null.
p is your probability that the chosen candidate is the right answer; be calibrated.
Reply with ONLY one JSON object: {"k": <integer or null>, "p": <number 0..1>}"""


class LLMReader:
    """Any LLMPolicy (Gemma local, Bedrock Haiku) as a reader over one pool."""
    kind = "llm"

    def __init__(self, policy, max_cands: int = 20):
        self.policy = policy
        self.name = policy.name
        self.usage = policy.usage
        self.max_cands = max_cands or 20          # round 11: Gemma at the product's top 16 (the view check)

    def read(self, question: str, answer_type: str, pool: dict) -> list[float]:
        import json
        import re
        cands = pool["cands"][:self.max_cands]
        if not cands:
            return []
        lines = [f"QUESTION: {question}", f"EXPECTED ANSWER TYPE: {answer_type}",
                 f"CANDIDATES (from {'search result snippets' if pool.get('snippet') else 'a page'}):"]
        for i, c in enumerate(cands):
            doms = ", ".join((c.get("domains") or [])[:3])
            lines.append(f"  [{i}] {c['value'][:80]} | \"{c.get('context', '')[:200]}\" | {doms}")
        raw = self.policy._complete(READER_SYSTEM, "\n".join(lines))
        m = re.search(r"\{.*?\}", raw, re.S)
        r = [0.0] * len(pool["cands"])
        try:
            d = json.loads(m.group(0)) if m else {}
            k = d.get("k")
            if k is not None and 0 <= int(k) < len(cands):
                r[int(k)] = max(0.0, min(1.0, float(d.get("p", 0.5))))
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
        return r


XREADER_CKPT = {"x-planck": "checkpoints/xreader_planck/reader.pt", "x-hertz": "checkpoints/xreader_hertz/reader.pt"}


def make_reader(name: str, **kw):
    if name == "heuristic":
        return HeuristicReader()
    if name in XREADER_CKPT:
        from pathlib import Path
        from .xreader import CrossReader
        path = kw.get("reader_checkpoint") or XREADER_CKPT[name]
        if not Path(path).exists():
            raise SystemExit(f"no {name} reader at {path}: run `planck3.py xreader train --base {name[2:]}` first")
        return CrossReader(path, quant=kw.get("reader_quant"), max_cands=kw.get("reader_cands") or 0)
    if name == "planck":
        return PlanckReader(kw["head"], kw.get("checkpoint"), kw.get("tokenizer"))
    if name in ("gemma", "bedrock"):
        from .policies import make_policy
        return LLMReader(make_policy(name, **{k: v for k, v in kw.items() if k in ("gemma_path", "model_id", "region", "profile")}),
                         max_cands=kw.get("reader_cands") or 20)
    raise ValueError(f"unknown reader {name}")


def timed(fn, *a, **kw):
    t0 = time.perf_counter()
    out = fn(*a, **kw)
    return out, (time.perf_counter() - t0) * 1000
