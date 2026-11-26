"""
G2, redesigned (2026-10-07): learn the decisions from KNOWN ANSWERS, not from a teacher.

The first two box runs showed the Gemma teacher is now worse than the deterministic
heuristic on G0 (85.1% vs 93.6%): its errors are subject echoes and abstains, so
imitating it would teach Planck those errors. Instead:

    collect   for each training question (Wikidata, disjoint from every benchmark):
              SEARCH -> snippet candidates (decision point 1), then read the most
              on-subject page -> page candidates (decision point 2). Each candidate is
              labelled right/wrong against the gold answer. No model in the loop.
    embed     encode question + "value. context" texts (hash control | Planck)
    train     CandidateScorer: per candidate [question, candidate, features] -> logit,
              plus a NULL logit ("none of these is right"), multi-positive NLL,
              temperature-calibrated on held-out questions
    policy    PlanckPolicy plugs into the harness: EXTRACT the top candidate when its
              calibrated p >= 0.5, otherwise read a page / abstain; ANSWER with that p
"""

import hashlib
import json
import math
import random
import time
from pathlib import Path

import numpy as np

from .actions import Decision
from .candidates import snippet_candidates, span_candidates, title_aboutness
from .metrics import is_correct
from .policies import HeuristicPolicy, Policy
from .util import REPO_ROOT, content_words, norm_text, read_json, read_jsonl, write_json
from .web import extract_jsonld, extract_main_text

G2_DIR = REPO_ROOT / "data" / "planck3" / "g2"
ANSWER_TYPES = ("year", "number", "date", "entity", "text")
N_FEAT = 9 + len(ANSWER_TYPES)
EXTRACT_THRESHOLD = 0.5
MAX_PAGES = 2  # fetch budget per question (declared 2026-10-07, before the box run): unsure after 2 pages -> abstain


# ── features (identical at train and decision time) ──────────────────────
# names in the words an answer card uses ("why this confidence")
FEATURE_NAMES = ["lexical match", "lexical lead over the next candidate", "source is about the subject",
                 "sources agreeing", "times mentioned", "position in the ranking", "repeats the question",
                 "read from a snippet", "near the top of the ranking"] + [f"answer type {t}" for t in ANSWER_TYPES]


def cand_text(c: dict) -> str:
    return f"{c['value']}. {c.get('context', '')}"[:400]


def features(c: dict, question: str, answer_type: str, i: int, n: int, from_snippet: bool) -> list[float]:
    q = set(content_words(question))
    v = set(norm_text(c["value"]).split())
    def num(k, default):  # stored candidates may carry None for fields their source lacks
        v = c.get(k)
        return float(default if v is None else v)
    f = [num("score", 0.0), num("margin", 0.0), num("about", 0.5),
         math.log1p(len(c.get("domains") or [1])), math.log1p(num("support", 1)), i / max(n - 1, 1),
         1.0 if v and v <= q else 0.0, 1.0 if from_snippet else 0.0, 1.0 / (1 + i)]
    return f + [1.0 if answer_type == t else 0.0 for t in ANSWER_TYPES]


# ── collect ──────────────────────────────────────────────────────────────
def collect(tasks: list[dict], web, out_path: Path, limit: int = 0):
    """Two labelled decision points per question. Resumable: skips task ids already collected."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = {r["task_id"] for r in read_jsonl(out_path)} if out_path.exists() else set()
    # attempted = searched, even if no pool came back (round 10: a re-run after a credit stop must not
    # search those again, and must know when the whole set is through)
    # Lines are "id<TAB>ok|empty". A search that FAILED (an error, not an empty answer) is never recorded,
    # so it is retried; a bare id (the first version) counts only if the question has a pool.
    att_path = out_path.with_suffix(".attempted.txt")
    attempted = set()
    if att_path.exists():
        for line in att_path.read_text(encoding="utf-8").splitlines():
            tid, _, how = line.partition("\t")
            if tid and (how or tid in done):
                attempted.add(tid)
    facts = [t for t in tasks if t["family"] == "fact"]
    todo = [t for t in facts if t["id"] not in done | attempted][: limit or None]
    stopped = False
    print(f"[g2] collecting {len(todo)} questions ({len(done)} already done) -> {out_path}")
    t0, empty = time.time(), 0
    with open(out_path, "a", encoding="utf-8") as f:
        for i, t in enumerate(todo, 1):
            q, at, gold = t["question"], t["answer_type"], t["gold"]
            left = web.brave_left() if hasattr(web, "brave_left") else None
            if left is not None and left < 2 and not (web.cache.get("search", f"brave|{q}") or {}).get("results"):
                # round 10: the run's Brave credit is spent. Stop rather than collect this question on
                # another backend (it would be marked done with a non-Brave pool); a re-run resumes here
                print(f"[g2] Brave credit for this run is spent after {i - 1} questions; re-run to resume", flush=True)
                stopped = True
                break
            results = web.search(q)
            if not results:
                empty += 1
            points = []
            snip = snippet_candidates(q, results, at)
            points.append(("snippet", snip))
            # the page a sensible policy would read: most on-subject title, then rank
            ranked = sorted(enumerate(results), key=lambda x: (-title_aboutness(q, x[1].get("title", "")), x[0]))
            if ranked:
                r = ranked[0][1]
                page = web.fetch(r["url"])
                if page.get("html"):
                    text = extract_main_text(page["html"], r["url"])
                    points.append(("page", span_candidates(q, text, at, url=r["url"],
                                                           extra_lines=extract_jsonld(page["html"]))))
            for src, cands in points:
                if not cands:
                    continue
                labels = [is_correct(c["value"], gold, at) for c in cands]
                f.write(json.dumps({"task_id": t["id"], "question": q, "answer_type": at, "source": src,
                                    "search_backend": getattr(web, "last_backend", None),
                                    "on_topic": getattr(web, "last_on_topic", None),
                                    "cands": [{k: c.get(k) for k in ("value", "context", "score", "margin", "about",
                                                                     "domains", "support", "url")} for c in cands],
                                    "labels": labels}, ensure_ascii=False) + "\n")
            f.flush()
            if results or not getattr(web, "last_error", None):     # an outage is not an answer: retry it
                with open(att_path, "a", encoding="utf-8") as fa:
                    fa.write(f"{t['id']}\t{'ok' if results else 'empty'}\n")
                attempted.add(t["id"])
            if i % 50 == 0:
                rate = (time.time() - t0) / i
                print(f"  {i}/{len(todo)} ({rate:.1f}s/question, ~{rate * (len(todo) - i) / 60:.0f} min left; "
                      f"{empty} empty searches)", flush=True)
    through = sum(t["id"] in done | attempted for t in facts)
    write_json(out_path.with_suffix(".progress.json"),
               {"target": len(facts), "through": through, "complete": through >= len(facts) and not stopped,
                "stopped_for_credit": stopped, "brave_live_calls": getattr(web, "brave_used", None)})
    print(f"[g2] {through}/{len(facts)} questions through" + (" (stopped: Brave credit spent)" if stopped else ""), flush=True)
    health = web.search_health() if hasattr(web, "search_health") else {}
    if health:
        write_json(out_path.with_suffix(".health.json"), health)
        print(f"[g2] search health: {health['fallback_rate']:.0%} via Wikipedia fallback, "
              f"{health['final_empty_rate']:.0%} empty")
    if todo and empty / len(todo) > 0.2:
        print(f"  ! {empty}/{len(todo)} searches came back empty: the search engine may be rate-limiting")


# ── embed ────────────────────────────────────────────────────────────────
def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def embed(points_path: Path, encoder_name: str, out_dir: Path, **enc_kw):
    from .encoders import make_encoder
    pts = read_jsonl(points_path)
    texts = sorted({p["question"] for p in pts} | {cand_text(c) for p in pts for c in p["cands"]})
    enc = make_encoder(encoder_name, **enc_kw)
    t0 = time.time()
    E = enc.encode(texts, progress=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(emb_path(out_dir, encoder_name, points_path), E)
    write_json(emb_index_path(out_dir, encoder_name, points_path), {_key(t): i for i, t in enumerate(texts)})
    print(f"[g2] {emb_path(out_dir, encoder_name, points_path).name}: {E.shape} in {time.time() - t0:.0f}s")


def emb_path(d: Path, enc: str, points: Path) -> Path:
    """Embeddings belong to a points file (Wikipedia-collected and SearXNG-collected never mix)."""
    return d / f"emb_{enc}_{Path(points).stem}.npy"


def emb_index_path(d: Path, enc: str, points: Path) -> Path:
    return d / f"emb_{enc}_{Path(points).stem}_index.json"


# ── model ────────────────────────────────────────────────────────────────
def make_scorer(dim: int, hidden: int = 128, dropout: float = 0.2):
    import torch.nn as nn

    class CandidateScorer(nn.Module):
        def __init__(self):
            super().__init__()
            self.pq = nn.Sequential(nn.Linear(dim, hidden), nn.LayerNorm(hidden))
            self.pc = nn.Sequential(nn.Linear(dim, hidden), nn.LayerNorm(hidden))
            self.pf = nn.Sequential(nn.Linear(N_FEAT, hidden), nn.GELU())
            self.mlp = nn.Sequential(nn.Linear(4 * hidden, hidden), nn.GELU(), nn.Dropout(dropout), nn.Linear(hidden, 1))
            self.null = nn.Sequential(nn.Linear(hidden, hidden // 2), nn.GELU(), nn.Linear(hidden // 2, 1))

        def forward(self, e_q, e_c, feats):
            """e_q [B,D], e_c [B,C,D], feats [B,C,F] -> logits [B, C+1] (last = NULL: none is right)."""
            import torch
            q = self.pq(e_q)
            c = self.pc(e_c)
            x = torch.cat([c, q.unsqueeze(1) * c, (q.unsqueeze(1) - c).abs(), self.pf(feats)], -1)
            return torch.cat([self.mlp(x).squeeze(-1), self.null(q)], -1)

    return CandidateScorer()


def _tensors(batch, E, index, device):
    import torch
    C = max(len(p["cands"]) for p in batch)
    B, D = len(batch), E.shape[1]
    e_q = torch.zeros(B, D)
    e_c = torch.zeros(B, C, D)
    ft = torch.zeros(B, C, N_FEAT)
    mask = torch.zeros(B, C + 1, dtype=torch.bool)
    pos = torch.zeros(B, C + 1, dtype=torch.bool)
    for r, p in enumerate(batch):
        e_q[r] = torch.from_numpy(E[index[_key(p["question"])]].astype(np.float32))
        n = len(p["cands"])
        for i, c in enumerate(p["cands"]):
            e_c[r, i] = torch.from_numpy(E[index[_key(cand_text(c))]].astype(np.float32))
            ft[r, i] = torch.tensor(features(c, p["question"], p["answer_type"], i, n, p["source"] == "snippet"))
        mask[r, :n] = True
        mask[r, C] = True                      # NULL is always a legal choice
        lab = p["labels"]
        if any(lab):
            pos[r, :n] = torch.tensor(lab)
        else:
            pos[r, C] = True                   # nothing on offer is right
    return e_q.to(device), e_c.to(device), ft.to(device), mask.to(device), pos.to(device)


def _nll(logits, pos, mask):
    import torch
    neg = torch.finfo(logits.dtype).min
    a = logits.masked_fill(~mask, neg)
    g = logits.masked_fill(~(pos & mask), neg)
    return (torch.logsumexp(a, -1) - torch.logsumexp(g, -1)).mean()


def train(points_path: Path, emb_dir: Path, encoder_name: str, out_dir: Path, seed: int = 0,
          epochs: int = 12, lr: float = 1e-3, patience: int = 3):
    import torch
    torch.manual_seed(seed)
    rng = random.Random(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    pts = read_jsonl(points_path)
    E = np.load(emb_path(emb_dir, encoder_name, points_path))
    index = read_json(emb_index_path(emb_dir, encoder_name, points_path))
    tids = sorted({p["task_id"] for p in pts})
    rng.shuffle(tids)
    val_ids = set(tids[: max(1, len(tids) // 10)])          # held-out QUESTIONS, not points
    tr = [p for p in pts if p["task_id"] not in val_ids]
    va = [p for p in pts if p["task_id"] in val_ids]
    model = make_scorer(E.shape[1]).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.05)
    best, bad, log = -1.0, 0, []
    out_dir.mkdir(parents=True, exist_ok=True)
    for ep in range(epochs):
        model.train()
        rng.shuffle(tr)
        tot = 0.0
        for s in range(0, len(tr), 64):
            e_q, e_c, ft, m, pos = _tensors(tr[s:s + 64], E, index, device)
            loss = _nll(model(e_q, e_c, ft), pos, m)
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += loss.item()
        acc = _val_top1(model, va, E, index, device)
        log.append({"epoch": ep, "train_nll": tot / max(1, len(tr) // 64), "val_top1": acc})
        print(f"  epoch {ep}: train_nll={log[-1]['train_nll']:.4f} val_top1={acc:.4f}", flush=True)
        if acc <= best:
            bad += 1
            if bad >= patience:
                break
            continue
        best, bad = acc, 0
        torch.save({"model": model.state_dict(), "dim": E.shape[1], "encoder": encoder_name, "seed": seed}, out_dir / "head.pt")
    ck = torch.load(out_dir / "head.pt", map_location=device)
    model.load_state_dict(ck["model"])
    T = _fit_temperature(model, va, E, index, device)
    ck["temperature"] = T
    torch.save(ck, out_dir / "head.pt")
    cal = _val_calibration(model, va, E, index, device, T)
    cal.update(_val_choice(model, va, E, index, device))
    base = _heuristic_val_top1(va)
    write_json(out_dir / "train_log.json", {"epochs": log, "best_val_top1": best, "temperature": T,
                                            "val_heuristic_top1": base, **cal, "encoder": encoder_name, "seed": seed,
                                            "n_train_points": len(tr), "n_val_points": len(va)})
    print(f"[g2] head:{encoder_name} s{seed}: choice accuracy {cal['val_choice_acc']:.3f} vs deterministic ranker "
          f"{base:.3f} on {cal['val_points_with_gold']} val points with a right candidate; 'none' correct "
          f"{cal['val_none_acc']:.3f} on {cal['val_points_without_gold']}; T={T:.2f}, ECE {cal['val_ece']:.3f} -> {out_dir}")


def _scores(model, pts, E, index, device, T=1.0):
    import torch
    model.eval()
    out = []
    with torch.no_grad():
        for s in range(0, len(pts), 128):
            batch = pts[s:s + 128]
            e_q, e_c, ft, m, pos = _tensors(batch, E, index, device)
            lg = model(e_q, e_c, ft).masked_fill(~m, -1e4) / T
            pr = torch.softmax(lg, -1)
            for r, p in enumerate(batch):
                n = len(p["cands"])
                C = lg.shape[1] - 1
                out.append((pr[r, list(range(n)) + [C]].cpu().numpy(), p))
    return out


def _val_top1(model, va, E, index, device) -> float:
    ok = 0
    for pr, p in _scores(model, va, E, index, device):
        k = int(pr.argmax())
        ok += (k == len(p["cands"]) and not any(p["labels"])) or (k < len(p["cands"]) and p["labels"][k])
    return ok / max(len(va), 1)


def _heuristic_val_top1(va) -> float:
    """The deterministic ranker's first candidate, on points where a right candidate EXISTS."""
    has = [p for p in va if any(p["labels"])]
    return sum(1 for p in has if p["labels"][0]) / max(len(has), 1)


def _val_choice(model, va, E, index, device) -> dict:
    """Apples to apples with the ranker: argmax over CANDIDATES only, on points with a right one;
    plus how often 'none of these' is chosen correctly where nothing on offer is right."""
    has_ok = has_n = none_ok = none_n = 0
    for pr, p in _scores(model, va, E, index, device):
        n = len(p["cands"])
        if any(p["labels"]):
            has_n += 1
            has_ok += bool(p["labels"][int(pr[:n].argmax())])
        else:
            none_n += 1
            none_ok += int(pr.argmax()) == n
    return {"val_choice_acc": has_ok / max(has_n, 1), "val_points_with_gold": has_n,
            "val_none_acc": none_ok / max(none_n, 1), "val_points_without_gold": none_n}


def _fit_temperature(model, va, E, index, device) -> float:
    best_t, best = 1.0, math.inf
    raw = _scores(model, va, E, index, device, T=1.0)
    logits = [np.log(np.clip(pr, 1e-12, 1)) for pr, _ in raw]
    for t in [0.3 * 1.12 ** i for i in range(40)]:
        nll = 0.0
        for lg, (_, p) in zip(logits, raw):
            z = lg / t
            z = z - z.max()
            lp = z - np.log(np.exp(z).sum())
            posi = [i for i, y in enumerate(p["labels"]) if y] or [len(p["cands"])]
            nll -= np.log(np.exp(lp[posi]).sum())
        if nll < best:
            best_t, best = t, nll
    return best_t


def _val_calibration(model, va, E, index, device, T) -> dict:
    from .metrics import ece
    probs, corr = [], []
    for pr, p in _scores(model, va, E, index, device, T):
        n = len(p["cands"])
        k = int(pr[:n].argmax()) if n else 0
        probs.append(float(pr[k]))
        corr.append(bool(n and p["labels"][k]))
    return {"val_ece": ece(probs, corr) or 0.0,
            "val_answer_acc_at_0.5": (sum(c for p_, c in zip(probs, corr) if p_ >= 0.5) /
                                      max(sum(1 for p_ in probs if p_ >= 0.5), 1))}


# ── the policy ───────────────────────────────────────────────────────────
class PlanckPolicy(Policy):
    """Learned candidate choice + calibrated confidence; everything else as the heuristic."""
    name = "planck"
    kind = "local"

    def __init__(self, head_path: str, checkpoint: str | None = None, tokenizer: str | None = None):
        super().__init__()
        import torch
        from .encoders import make_encoder
        self.torch = torch
        ck = torch.load(head_path, map_location="cpu", weights_only=False)
        self.encoder_name = ck["encoder"]
        self.name = f"planck-g2:{self.encoder_name}"
        self.enc = make_encoder(self.encoder_name, checkpoint=checkpoint, tokenizer=tokenizer)
        self.model = make_scorer(ck["dim"])
        self.model.load_state_dict(ck["model"])
        self.model.eval()
        self.T = float(ck.get("temperature", 1.0))
        self.fallback = HeuristicPolicy()
        self._held_p = 0.5

    def _probs(self, obs, spans, from_snippet):
        torch = self.torch
        q, at = obs["question"], obs["answer_type"]
        E = self.enc.encode([q] + [cand_text(c) for c in spans]).astype(np.float32)
        e_q = torch.from_numpy(E[:1])
        e_c = torch.from_numpy(E[1:]).unsqueeze(0)
        ft = torch.tensor([[features(c, q, at, i, len(spans), from_snippet) for i, c in enumerate(spans)]])
        with torch.no_grad():
            pr = torch.softmax(self.model(e_q, e_c, ft)[0] / self.T, -1).numpy()
        return pr  # [n + 1], last = none is right

    def decide(self, obs):
        phase = obs["phase"]
        spans = obs["lists"].get("spans", [])
        if phase in ("results_snip", "page") and spans:
            pr = self._probs(obs, spans, phase == "results_snip")
            k = int(pr[:-1].argmax())
            if pr[k] >= EXTRACT_THRESHOLD:
                self._held_p = float(pr[k])
                return Decision("EXTRACT", k=k, p=self._held_p)
            nxt = self.fallback._best_unopened(obs)
            if nxt is not None and len(obs["opened"]) < MAX_PAGES:
                return Decision("OPEN", k=nxt, p=float(pr[k]))
            return Decision("ABSTAIN", p=float(pr[k]))
        if phase == "extracted":
            p = self._held_p
            if p < 0.7 and self.fallback._best_unopened(obs) is not None:
                return Decision("VERIFY", p=p)
            return Decision("ANSWER", p=p)
        if phase == "verified":
            p = min(0.97, self._held_p + 0.2) if obs["verified"] else self._held_p * 0.8
            return Decision("ANSWER", p=p)
        return self.fallback.decide(obs)  # start / store_hit / results without snippet values


# ── G2 v2 (2026-10-08): choice and answerability decoupled ───────────────
# v1 failed because ONE softmax over candidates + NULL answered two questions at once
# ("which candidate?" and "is any right?"): trained where 52% of points had no right
# candidate, NULL absorbed the mass and the policy was under-confident under shift
# (the right answer ranked FIRST at p 0.05-0.33). v2:
#   choice head   softmax over CANDIDATES only, trained only on points with a right one
#   gate          calibrated logistic P(the chosen candidate is right), on points the
#                 choice head never saw (validation questions)
#   threshold     the lowest gate score whose validation precision >= GATE_PRECISION,
#                 fixed before any benchmark run; coverage/precision reported on a test split
GATE_PRECISION = 0.90
GATE_FEATURE_NAMES = ["choice head's probability", "lead over the runner-up", "spread across candidates",
                      "number of candidates", "agrees with the lexical ranker"] + FEATURE_NAMES


def gate_features(choice_p, cands, question, answer_type, from_snippet) -> list[float]:
    """Scalar features of a decision: how sure the choice head is, and about what."""
    order = np.argsort(-choice_p)
    k, k2 = int(order[0]), (int(order[1]) if len(order) > 1 else None)
    p1 = float(choice_p[k])
    p2 = float(choice_p[k2]) if k2 is not None else 0.0
    ent = float(-(choice_p * np.log(np.clip(choice_p, 1e-12, 1))).sum() / max(math.log(len(choice_p)), 1e-9)) \
        if len(choice_p) > 1 else 0.0
    f = features(cands[k], question, answer_type, k, len(cands), from_snippet)
    return [p1, p1 - p2, ent, math.log1p(len(cands)), 1.0 if k == 0 else 0.0] + f


def select_threshold(scores: list[float], correct: list[bool], precision: float = GATE_PRECISION) -> float:
    """Lowest threshold t such that precision among {score >= t} >= target (1.01 = never answer)."""
    pairs = sorted(zip(scores, correct), key=lambda x: -x[0])
    best, hit = 1.01, 0
    for i, (sc, ok) in enumerate(pairs, 1):
        hit += ok
        if hit / i >= precision:
            best = sc
    return float(best)


def _choice_probs(model, pts, E, index, device, T):
    import torch
    out = []
    model.eval()
    with torch.no_grad():
        for s in range(0, len(pts), 128):
            batch = pts[s:s + 128]
            e_q, e_c, ft, m, pos = _tensors(batch, E, index, device)
            C = e_c.shape[1]
            lg = model(e_q, e_c, ft)[:, :C].masked_fill(~m[:, :C], -1e4) / T
            pr = torch.softmax(lg, -1).cpu().numpy()
            for r, p in enumerate(batch):
                out.append(pr[r, :len(p["cands"])])
    return out


def train_v2(points_path: Path, emb_dir: Path, encoder_name: str, out_dir: Path, seed: int = 0,
             epochs: int = 12, lr: float = 1e-3, patience: int = 3):
    import torch
    from sklearn.linear_model import LogisticRegression
    from .metrics import ece
    torch.manual_seed(seed)
    rng = random.Random(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    pts = read_jsonl(points_path)
    E = np.load(emb_path(emb_dir, encoder_name, points_path))
    index = read_json(emb_index_path(emb_dir, encoder_name, points_path))
    tids = sorted({p["task_id"] for p in pts})
    rng.shuffle(tids)
    n = len(tids)
    split = {t: ("test" if i < n // 10 else "val" if i < n // 5 else "train") for i, t in enumerate(tids)}
    tr = [p for p in pts if split[p["task_id"]] == "train" and any(p["labels"])]   # choice: only where a right one exists
    va_all = [p for p in pts if split[p["task_id"]] == "val"]
    te_all = [p for p in pts if split[p["task_id"]] == "test"]
    va_pos = [p for p in va_all if any(p["labels"])]
    model = make_scorer(E.shape[1]).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.05)
    best, bad, log = -1.0, 0, []
    out_dir.mkdir(parents=True, exist_ok=True)

    def choice_acc(ps, T=1.0):
        prs = _choice_probs(model, ps, E, index, device, T)
        return sum(bool(p["labels"][int(pr.argmax())]) for pr, p in zip(prs, ps)) / max(len(ps), 1)

    for ep in range(epochs):
        model.train()
        rng.shuffle(tr)
        tot = 0.0
        for s_ in range(0, len(tr), 64):
            e_q, e_c, ft, m, pos = _tensors(tr[s_:s_ + 64], E, index, device)
            C = e_c.shape[1]
            loss = _nll(model(e_q, e_c, ft)[:, :C], pos[:, :C], m[:, :C])     # NULL never used in v2
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += loss.item()
        acc = choice_acc(va_pos)
        log.append({"epoch": ep, "train_nll": tot / max(1, len(tr) // 64), "val_choice_acc": acc})
        print(f"  epoch {ep}: train_nll={log[-1]['train_nll']:.4f} val_choice_acc={acc:.4f}", flush=True)
        if acc <= best:
            bad += 1
            if bad >= patience:
                break
            continue
        best, bad = acc, 0
        torch.save({"model": model.state_dict()}, out_dir / "choice.pt")
    model.load_state_dict(torch.load(out_dir / "choice.pt", map_location=device)["model"])
    # temperature on validation points with a right candidate
    best_t, best_nll = 1.0, math.inf
    raw = _choice_probs(model, va_pos, E, index, device, 1.0)
    for t in [0.3 * 1.12 ** i for i in range(40)]:
        nll = 0.0
        for pr, p in zip(raw, va_pos):
            z = np.log(np.clip(pr, 1e-12, 1)) / t
            z -= z.max()
            lp = z - np.log(np.exp(z).sum())
            nll -= np.log(np.exp(lp[[i for i, y in enumerate(p["labels"]) if y]]).sum())
        if nll < best_nll:
            best_t, best_nll = t, nll
    T = best_t

    def gate_data(ps):
        prs = _choice_probs(model, ps, E, index, device, T)
        X = [gate_features(pr, p["cands"], p["question"], p["answer_type"], p["source"] == "snippet") for pr, p in zip(prs, ps)]
        y = [bool(p["labels"][int(pr.argmax())]) for pr, p in zip(prs, ps)]
        return np.array(X, dtype=np.float64), np.array(y)
    Xv, yv = gate_data(va_all)
    Xt, yt = gate_data(te_all)
    mu, sd = Xv.mean(0), Xv.std(0) + 1e-6
    gate = LogisticRegression(C=1.0, max_iter=2000, class_weight=None).fit((Xv - mu) / sd, yv) \
        if len(set(yv.tolist())) > 1 else None
    def gate_p(X):
        return gate.predict_proba((X - mu) / sd)[:, 1] if gate is not None else np.full(len(X), float(yv.mean() if len(yv) else 0))
    pv, pt = gate_p(Xv), gate_p(Xt)
    tau = select_threshold(pv.tolist(), yv.tolist())

    def at(p, y, t):
        sel = p >= t
        return {"coverage": float(sel.mean()) if len(p) else 0.0,
                "precision": float(y[sel].mean()) if sel.any() else None}
    try:
        from sklearn.metrics import roc_auc_score
        auc = float(roc_auc_score(yt, pt)) if len(set(yt.tolist())) > 1 else None
    except Exception:
        auc = None
    det = [p for p in te_all if any(p["labels"])]
    metrics = {
        "version": 2, "encoder": encoder_name, "seed": seed, "points": str(points_path),
        "n_questions": n, "n_train_points": len(tr), "n_val_points": len(va_all), "n_test_points": len(te_all),
        "temperature": T, "tau": tau, "gate_precision_target": GATE_PRECISION,
        "test_choice_acc": choice_acc(det, T), "test_ranker_acc": _heuristic_val_top1(det), "test_points_with_gold": len(det),
        "test_gate_auc": auc, "test_gate_ece": ece(pt.tolist(), yt.tolist()) if len(pt) else None,
        "val_at_tau": at(pv, yv, tau), "test_at_tau": at(pt, yt, tau),
        "test_base_rate": float(yt.mean()) if len(yt) else None, "epochs": log}
    torch.save({"version": 2, "model": model.state_dict(), "dim": E.shape[1], "encoder": encoder_name, "seed": seed,
                "temperature": T, "tau": tau,
                "gate": {"coef": gate.coef_[0].tolist() if gate is not None else None,
                         "intercept": float(gate.intercept_[0]) if gate is not None else float(yv.mean() if len(yv) else 0),
                         "mu": mu.tolist(), "sd": sd.tolist()}}, out_dir / "head.pt")
    write_json(out_dir / "train_log.json", metrics)
    ta = metrics["test_at_tau"]
    print(f"[g2v2] head:{encoder_name}: test choice {metrics['test_choice_acc']:.3f} vs ranker {metrics['test_ranker_acc']:.3f} "
          f"({len(det)} test points with a right one); gate AUC {auc}; tau={tau:.3f} -> test coverage "
          f"{ta['coverage']:.2f} at precision {ta['precision']} (target {GATE_PRECISION}) -> {out_dir}")


class PlanckPolicyV2(PlanckPolicy):
    """v2: choose with the choice head; answer only when the calibrated gate clears tau."""
    calibrated = True
    confidence_kind = "calibrated on held-out questions"

    def __init__(self, head_path: str, checkpoint: str | None = None, tokenizer: str | None = None):
        super().__init__(head_path, checkpoint, tokenizer)
        import torch
        ck = torch.load(head_path, map_location="cpu", weights_only=False)
        self.name = f"planck-g2v2:{self.encoder_name}"
        self.tau = float(ck["tau"])
        g = ck["gate"]
        self.g_coef = np.array(g["coef"]) if g["coef"] is not None else None
        self.g_b, self.g_mu, self.g_sd = g["intercept"], np.array(g["mu"]), np.array(g["sd"])

    def _choice(self, obs, spans, from_snippet):
        torch = self.torch
        q, at = obs["question"], obs["answer_type"]
        E = self.enc.encode([q] + [cand_text(c) for c in spans]).astype(np.float32)
        ft = torch.tensor([[features(c, q, at, i, len(spans), from_snippet) for i, c in enumerate(spans)]])
        with torch.no_grad():
            lg = self.model(torch.from_numpy(E[:1]), torch.from_numpy(E[1:]).unsqueeze(0), ft)[0, :len(spans)]
            pr = torch.softmax(lg / self.T, -1).numpy()
        x = np.array(gate_features(pr, spans, q, at, from_snippet))
        if self.g_coef is None:
            self._weights = []
            return pr, float(1 / (1 + np.exp(-self.g_b)))
        contrib = (x - self.g_mu) / self.g_sd * self.g_coef      # each feature's push, in log-odds
        order = np.argsort(-np.abs(contrib))[:5]
        self._weights = [[GATE_FEATURE_NAMES[i], round(float(contrib[i]), 3)] for i in order]
        return pr, float(1 / (1 + np.exp(-(contrib.sum() + self.g_b))))

    def decide(self, obs):
        phase = obs["phase"]
        spans = obs["lists"].get("spans", [])
        if phase in ("results_snip", "page") and spans:
            pr, gate = self._choice(obs, spans, phase == "results_snip")
            k = int(pr.argmax())
            top = np.argsort(-pr)[:3]
            meta = {"argmax": k, "argmax_value": spans[k]["value"], "gate": round(gate, 4), "tau": self.tau,
                    "top3": [[int(i), spans[int(i)]["value"], round(float(pr[i]), 4)] for i in top],
                    "gate_weights": self._weights, "gate_bias": round(float(self.g_b), 3)}
            if gate >= self.tau:
                self._held_p = gate
                return Decision("EXTRACT", k=k, p=gate, meta=meta)
            nxt = self.fallback._best_unopened(obs)
            if nxt is not None and len(obs["opened"]) < MAX_PAGES:
                return Decision("OPEN", k=nxt, p=gate, meta=meta)
            return Decision("ABSTAIN", p=gate, meta=meta)
        return super().decide(obs)


def load_policy(head_path: str, checkpoint=None, tokenizer=None):
    import torch
    ck = torch.load(head_path, map_location="cpu", weights_only=False)
    cls = PlanckPolicyV2 if ck.get("version") == 2 else PlanckPolicy
    return cls(head_path, checkpoint=checkpoint, tokenizer=tokenizer)


# ── CLI ──────────────────────────────────────────────────────────────────
def add_cli(sub, add_web_args, build_web):
    p = sub.add_parser("g2", help="G2: learn decisions from known answers (collect | embed | train)")
    p.add_argument("stage", choices=["collect", "embed", "train", "train2"])
    p.add_argument("--tasks", default=str(REPO_ROOT / "scripts" / "assets" / "planck3_g2_train_tasks.json"))
    p.add_argument("--points", default=None,
                   help="decision points file (default: points_<search backend>.jsonl for collect, "
                        "points_searxng.jsonl if present else points.jsonl for embed/train)")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--encoder", default="hash", choices=["hash", "planck"])
    p.add_argument("--checkpoint", default="checkpoints/planck13/best.pt")
    p.add_argument("--tokenizer", default="data/wikipedia/tokenizer.model")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--tag", default="", help="suffix for the head dir (round 4: _ddgs)")
    add_web_args(p)

    def default_points():
        for name in ("points_searxng.jsonl", "points.jsonl", "points_wikipedia.jsonl"):
            if (G2_DIR / name).exists():
                return G2_DIR / name
        return G2_DIR / "points_searxng.jsonl"

    def run(args):
        if args.stage == "collect":
            web = build_web(args)
            pts = Path(args.points) if args.points else G2_DIR / f"points_{web.backend}.jsonl"
            collect(read_json(args.tasks)["tasks"], web, pts, args.limit)
            return
        pts = Path(args.points) if args.points else default_points()
        print(f"[g2] points: {pts}")
        if args.stage == "embed":
            embed(pts, args.encoder, G2_DIR, checkpoint=args.checkpoint, tokenizer=args.tokenizer)
        elif args.stage == "train":
            train(pts, G2_DIR, args.encoder,
                  REPO_ROOT / "results" / "planck3" / f"g2_head_{args.encoder}_s{args.seed}", seed=args.seed)
        else:
            train_v2(pts, G2_DIR, args.encoder,
                     REPO_ROOT / "results" / "planck3" / f"g2v2_head_{args.encoder}_s{args.seed}{args.tag}", seed=args.seed)
    p.set_defaults(fn=run)
