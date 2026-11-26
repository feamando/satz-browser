"""
The round 6 reader (SETUP_planck_20261012.md): Planck 1.3 (100M) or Hertz 1.2 (640M) fine-tuned ONCE
as a cross-encoder that reads the question and each candidate's evidence TOGETHER.

Round 5's reader scored frozen Planck embeddings of the question and of the candidate separately
(they met only in a small MLP) and lost 20 points to Gemma, mostly on news-style questions. Here the
whole SGS model is trained, on the question + candidate text, to answer "does this candidate answer
this question, according to this evidence?". It is still a reading SKILL: labels come from known
answers (Wikidata, the portal item's words), never from a model, and nothing about 2026 is in the data.

    input     "QUESTION ... ANSWER TYPE ..." (shared prefix) + "CANDIDATE ... FROM ... EVIDENCE ... ?"
              per candidate (top 16 of a pool); the hidden state at the last token + the round 4
              lexical features (score, lead, aboutness, agreement, ...) -> two logits:
    choice    softmax over the pool's candidates: WHICH one answers (trained where one does)
    answer    per candidate: DOES it answer (trained on every candidate, right or not)
    output    r_k = choice_k x g, g = Platt(answer logit of the chosen candidate), both calibrated
              on held-out QUESTIONS; r feeds consolidate.py unchanged
    years     training pools get every year shifted by the same random k (p 0.5), so "2025"
              vs "2026" carries no information about answerability: the reader must read

On a phone the shared question prefix is computed once and each candidate continues from the
KV cache (SGSLanguageModel.forward_cached), so a pool of 16 is one batched step.
"""

import hashlib
import json
import math
import random
import re
import time
from pathlib import Path

import numpy as np

from .g2 import N_FEAT, features
from .util import REPO_ROOT, read_json, read_jsonl, write_json

READER_DIR = REPO_ROOT / "data" / "planck3" / "reader"
MAX_CANDS = 16
MAX_READ = 32         # round 11: a trained reader may READ up to this many (trained on MAX_CANDS)
PREFIX_TOKENS = 64
CAND_TOKENS = 112
EVIDENCE_CHARS = 320
YEAR_SHIFT_P = 0.5
GROUPS = ("stable", "recent", "news", "info", "squad", "newsqa", "triviaqa", "searchqa", "nq", "squad2neg")  # + round 7 reading sets


def prefix_text(question: str, answer_type: str) -> str:
    return f"QUESTION: {question}\nANSWER TYPE: {answer_type}\n"


def cand_text(c: dict, from_snippet: bool) -> str:
    return (f"CANDIDATE: {c['value']}\nFROM: {'a search result snippet' if from_snippet else 'a page'}\n"
            f"EVIDENCE: {(c.get('context') or '')[:EVIDENCE_CHARS]}\nDOES THE CANDIDATE ANSWER THE QUESTION?")


_YEAR = re.compile(r"(?<!\d)(19\d\d|20[0-3]\d)(?!\d)")


def shift_years(s: str, k: int) -> str:
    return _YEAR.sub(lambda m: str(int(m.group(1)) + k), s or "")


def group_of(task_id: str) -> str:
    g = task_id.split("_", 1)[0]
    return g if g in GROUPS else "stable"


def split_of(task_id: str) -> str:
    """By QUESTION (hash of the task id): 80% train, 10% validation (calibration), 10% test."""
    h = int(hashlib.sha1(task_id.encode("utf-8")).hexdigest()[:8], 16) % 10
    return "test" if h == 0 else "val" if h == 1 else "train"


def pool_cands(p: dict, k_max: int = MAX_CANDS) -> tuple[list[dict], list[bool]]:
    """Top MAX_CANDS candidates in ranker order, exactly what the reader sees when it answers.

    Round 6 swapped a right candidate from beyond the cut into the LAST slot at training time. With
    "position in the ranking" among the features, that taught the reader that the 16th candidate is
    often right, which is never true at answer time (no labels, no swap). Round 6b: no swap; a pool
    whose only right candidate is beyond the cut is a pool with no right candidate, as served."""
    k = min(len(p["cands"]), k_max)
    return list(p["cands"][:k]), [bool(x) for x in p["labels"][:k]]


def right_beyond_cut(p: dict) -> bool:
    """A right candidate exists, but only beyond the top MAX_CANDS (unreachable for the reader)."""
    labels = p.get("labels") or []
    return any(labels[MAX_CANDS:]) and not any(labels[:MAX_CANDS])


# ── model ────────────────────────────────────────────────────────────────
def load_backbone(checkpoint: str, use_checkpoint: bool = False):
    import torch
    from scripts.generate import infer_arch
    from src.sgs_lm import SGSLanguageModel, migrate_state_dict
    ck = torch.load(checkpoint, map_location="cpu", weights_only=False)
    state = migrate_state_dict(ck["model"] if "model" in ck else ck)
    arch = infer_arch(state)
    lm = SGSLanguageModel(**arch, return_hidden=True, use_checkpoint=use_checkpoint)
    lm.load_state_dict(state)
    return lm, arch


def make_head(d_f: int):
    import torch.nn as nn
    return nn.Sequential(nn.Linear(d_f + N_FEAT, 256), nn.GELU(), nn.Linear(256, 2))


class Encoded:
    """One pool as token ids: a shared prefix + one continuation per candidate."""

    def __init__(self, sp, p: dict, shift: int = 0, k_max: int = MAX_CANDS):
        q = shift_years(p["question"], shift) if shift else p["question"]
        cands, self.labels = pool_cands(p, k_max)
        t = p.get("teacher")                     # round 10: Gemma's reading of the same pool, if labelled
        self.teacher = None if not t else (int(t["k"]) if t.get("k") is not None and int(t["k"]) < len(cands) else -1,
                                           float(t.get("p", 0.5)))
        snip = p.get("source") == "snippet" or p.get("snippet", False)
        if shift:
            cands = [dict(c, value=shift_years(c["value"], shift), context=shift_years(c.get("context", ""), shift))
                     for c in cands]
        self.prefix = sp.encode(prefix_text(q, p["answer_type"]), out_type=int)[:PREFIX_TOKENS]
        self.conts = [sp.encode(cand_text(c, snip), out_type=int)[:CAND_TOKENS] or [sp.unk_id()] for c in cands]
        self.feats = [features(c, q, p["answer_type"], i, len(cands), snip) for i, c in enumerate(cands)]


def _forward(lm, head, batch: list[Encoded], device, pad: int):
    """Full sequences (prefix + continuation), right-padded: the hidden at each last real token."""
    import torch
    seqs = [e.prefix + c for e in batch for c in e.conts]
    L = max(len(s) for s in seqs)
    ids = torch.full((len(seqs), L), pad, dtype=torch.long)
    for i, s in enumerate(seqs):
        ids[i, :len(s)] = torch.tensor(s)
    last = torch.tensor([len(s) - 1 for s in seqs])
    ft = torch.tensor([f for e in batch for f in e.feats], dtype=torch.float32)
    ids, last, ft = ids.to(device), last.to(device), ft.to(device)
    with torch.autocast("cuda", dtype=torch.bfloat16, enabled=str(device).startswith("cuda")):
        h = lm(ids)
    h = h.float()[torch.arange(len(seqs), device=device), last]
    return head(torch.cat([h, ft], -1))                       # [N, 2]: choice logit, answer logit


def _losses(logits, batch: list[Encoded], teacher_w: float = 0.0):
    """Known-answer labels (choice: the right candidates' share; answer: per-candidate BCE). Round 10 adds,
    with weight teacher_w, Gemma's reading of the same pool as a soft target: its chosen candidate gets
    its stated probability p, the rest share 1 - p; "none of these" (k = -1) pushes every answer logit down."""
    import torch
    import torch.nn.functional as F
    choice, bce, n_choice, k = 0.0, [], 0, 0
    soft, n_soft = 0.0, 0
    for e in batch:
        n = len(e.conts)
        lg = logits[k:k + n]
        k += n
        y = torch.tensor(e.labels, device=lg.device)
        if y.any():
            s = lg[:, 0]
            choice = choice + (torch.logsumexp(s, 0) - torch.logsumexp(s.masked_fill(~y, -1e4), 0))
            n_choice += 1
        bce.append(F.binary_cross_entropy_with_logits(lg[:, 1], y.float(), reduction="sum"))
        if teacher_w and e.teacher is not None:
            tk, tp = e.teacher
            if tk >= 0:
                q = torch.full((n,), (1 - tp) / max(n - 1, 1), device=lg.device)
                q[tk] = tp if n > 1 else 1.0
                soft = soft - (q * F.log_softmax(lg[:, 0], 0)).sum()
            else:
                soft = soft + F.binary_cross_entropy_with_logits(lg[:, 1], torch.zeros(n, device=lg.device))
            n_soft += 1
    n_c = sum(len(e.conts) for e in batch)
    loss = choice / max(n_choice, 1) + torch.stack(bce).sum() / max(n_c, 1)
    return loss + teacher_w * soft / n_soft if n_soft else loss


def _batches(encs: list[Encoded], cands_per_step: int):
    b, n = [], 0
    for e in encs:
        if b and n + len(e.conts) > cands_per_step:
            yield b
            b, n = [], 0
        b.append(e)
        n += len(e.conts)
    if b:
        yield b


def _n_batches(sizes: list[int], cands_per_step: int) -> int:
    """How many batches _batches packs these pools into (pools are never split across batches)."""
    nb, n = 0, 0
    for k in sizes:
        if nb and n + k > cands_per_step:
            nb, n = nb + 1, 0
        elif not nb:
            nb = 1
        n += k
    return nb


def _scores(lm, head, encs, device, pad, cands_per_step):
    import torch
    lm.eval()
    head.eval()
    out = []
    with torch.no_grad():
        for b in _batches(encs, cands_per_step):
            lg = _forward(lm, head, b, device, pad).float().cpu().numpy()
            k = 0
            for e in b:
                out.append(lg[k:k + len(e.conts)])
                k += len(e.conts)
    return out


def _softmax(x, T=1.0):
    z = np.asarray(x, dtype=np.float64) / T
    z = np.exp(z - z.max())
    return z / z.sum()


def fit_temperature(scores, encs) -> float:
    best_t, best = 1.0, math.inf
    pos = [(s[:, 0], e.labels) for s, e in zip(scores, encs) if any(e.labels)]
    for t in [0.3 * 1.12 ** i for i in range(40)]:
        nll = 0.0
        for s, y in pos:
            p = _softmax(s, t)
            nll -= math.log(max(sum(pi for pi, yi in zip(p, y) if yi), 1e-12))
        if nll < best:
            best_t, best = t, nll
    return best_t


def gate_data(scores, encs, T):
    """Per pool: (answer logit of the chosen candidate, is the chosen candidate right)."""
    x, y = [], []
    for s, e in zip(scores, encs):
        k = int(np.argmax(_softmax(s[:, 0], T)))
        x.append(float(s[k, 1]))
        y.append(bool(e.labels[k]))
    return np.array(x), np.array(y)


def fit_platt(x, y, iters: int = 200) -> tuple[float, float]:
    """1-D logistic regression by Newton's method (no sklearn on the phone path)."""
    a, b = 1.0, 0.0
    if len(set(y.tolist())) < 2:
        return 0.0, float(np.log((y.mean() + 1e-3) / (1 - y.mean() + 1e-3)))
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(a * x + b)))
        g = np.array([((p - y) * x).sum(), (p - y).sum()])
        w = p * (1 - p) + 1e-9
        H = np.array([[(w * x * x).sum(), (w * x).sum()], [(w * x).sum(), w.sum()]]) + 1e-6 * np.eye(2)
        step = np.linalg.solve(H, g)
        a, b = a - step[0], b - step[1]
        if np.abs(step).max() < 1e-8:
            break
    return float(a), float(b)


def evaluate(scores, encs, T, a, b) -> dict:
    from .metrics import ece
    from .wikirace import mcnemar
    has = [(s, e) for s, e in zip(scores, encs) if any(e.labels)]
    hit_c = [bool(e.labels[int(np.argmax(s[:, 0]))]) for s, e in has]
    hit_r = [bool(e.labels[0]) for _, e in has]
    choice = sum(hit_c) / max(len(has), 1)
    ranker = sum(hit_r) / max(len(has), 1)
    vs = mcnemar(hit_c, hit_r)          # paired: does the reader beat its own lexical ranker on these pools?
    x, y = gate_data(scores, encs, T)
    g = 1 / (1 + np.exp(-(a * x + b))) if len(x) else np.array([])
    try:
        from sklearn.metrics import roc_auc_score
        auc = float(roc_auc_score(y, g)) if len(set(y.tolist())) > 1 else None
    except Exception:
        auc = None
    return {"pools": len(encs), "pools_with_a_right_candidate": len(has), "choice_acc": choice, "ranker_acc": ranker,
            "only_choice_right": vs["a_only"], "only_ranker_right": vs["b_only"], "vs_ranker_p": vs["p"],
            "gate_auc": auc, "gate_ece": ece(g.tolist(), y.tolist()) if len(g) else None,
            "base_rate": float(y.mean()) if len(y) else None}


def teacher_agreement(scores, encs) -> dict:
    """Round 12: on held-out pools Gemma read, how often the reader picks Gemma's candidate (where Gemma
    picked one), and how often Gemma's pick is right where a right one exists (the teacher's own ceiling)."""
    rows = [(s, e) for s, e in zip(scores, encs) if e.teacher is not None and e.teacher[0] >= 0]
    if not rows:
        return {"pools": 0}
    same = sum(int(np.argmax(s[:, 0])) == e.teacher[0] for s, e in rows)
    lab = [(s, e) for s, e in rows if any(e.labels)]
    return {"pools": len(rows), "reader_picks_teacher": same / len(rows),
            "teacher_right": sum(bool(e.labels[e.teacher[0]]) for _, e in lab) / max(len(lab), 1),
            "reader_right": sum(bool(e.labels[int(np.argmax(s[:, 0]))]) for s, e in lab) / max(len(lab), 1),
            "pools_with_a_right_candidate": len(lab)}


def sample_points(src: Path, out: Path, n: int, seed: int = 12) -> dict:
    """Round 12: a seeded sample of n pools from a points file, streamed (round 7's 150k reading pools do
    not fit in memory parsed). n = 0 copies every pool. The source is never modified: `teach` rewrites its
    file in place, so round 12 teaches copies and rounds 6-10's files stay as they were."""
    with open(src, encoding="utf-8") as f:
        total = sum(1 for line in f if line.strip())
    keep = set(range(total)) if not n or n >= total else set(random.Random(seed).sample(range(total), n))
    by: dict[str, int] = {}
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with open(src, encoding="utf-8") as f, open(tmp, "w", encoding="utf-8") as g:
        i = 0
        for line in f:
            if not line.strip():
                continue
            if i in keep:
                g.write(line if line.endswith("\n") else line + "\n")
                tid = json.loads(line).get("task_id", "")
                by[group_of(tid)] = by.get(group_of(tid), 0) + 1
            i += 1
    tmp.replace(out)
    meta = {"src": str(src), "out": str(out), "total": total, "kept": len(keep), "seed": seed, "by_group": by}
    print(f"[xreader] sampled {len(keep)} of {total} pools -> {out} {by}", flush=True)
    return meta


# ── train once ───────────────────────────────────────────────────────────
def load_points(paths: list[Path]) -> list[dict]:
    """Pools trimmed to the top MAX_CANDS as they are read (round 7's 150k reading pools would not
    fit in memory with every candidate); `beyond` keeps whether a right one was only past the cut."""
    pts = []
    for path in paths:
        if path and Path(path).is_file():
            for p in read_jsonl(path):
                if p.get("cands"):
                    p["beyond"] = right_beyond_cut(p)
                    p["cands"], p["labels"] = p["cands"][:MAX_CANDS], p["labels"][:MAX_CANDS]
                    pts.append(p)
    return pts


def train(points: list[Path], base_ckpt: str, tokenizer: str, out_dir: Path, name: str, epochs: int = 3,
          lr: float = 5e-5, cands_per_step: int = 64, seed: int = 0, grad_checkpoint: bool = False,
          max_points: int = 0, init: str | None = None, max_eval: int = 0, teacher_w: float = 0.0,
          early_stop: int = 0) -> dict:
    """init: start from a trained reader (round 7: the reading-skill reader, then our own pools).
    max_eval: cap the validation and test pools (a seeded sample) when a points set is very large.
    teacher_w: weight of Gemma's soft labels (round 10). early_stop: stop after this many epochs without a
    better validation choice accuracy (round 10: Hertz overfit our pools in round 7, loss 0.18)."""
    import sentencepiece as spm
    import torch
    torch.manual_seed(seed)
    rng = random.Random(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    sp = spm.SentencePieceProcessor(model_file=str(tokenizer))
    lm, arch = load_backbone(base_ckpt, use_checkpoint=grad_checkpoint)
    if arch["vocab_size"] != sp.get_piece_size():
        raise SystemExit(f"tokenizer vocab {sp.get_piece_size()} != checkpoint vocab {arch['vocab_size']} ({tokenizer})")
    head = make_head(arch["d_f"])
    if init:
        w0 = torch.load(init, map_location="cpu", weights_only=False)
        lm.load_state_dict(w0["lm"])
        head.load_state_dict(w0["head"])
        print(f"[xreader:{name}] starting from {init}", flush=True)
    lm.to(device)
    head.to(device)
    pts = load_points(points)
    if max_points:
        rng.shuffle(pts)
        pts = pts[:max_points]
    by = {s: [p for p in pts if split_of(p["task_id"]) == s] for s in ("train", "val", "test")}
    if max_eval:
        er = random.Random(seed + 1)
        for s in ("val", "test"):
            if len(by[s]) > max_eval:
                by[s] = er.sample(by[s], max_eval)
    pad = sp.pad_id() if sp.pad_id() >= 0 else 0
    val = [Encoded(sp, p) for p in by["val"]]
    test = [Encoded(sp, p) for p in by["test"]]
    opt = torch.optim.AdamW([{"params": lm.parameters(), "lr": lr}, {"params": head.parameters(), "lr": 1e-3}],
                            weight_decay=0.01)
    sizes = [min(len(p["cands"]), MAX_CANDS) for p in by["train"]]
    n_cands = sum(sizes)
    # round 8: the cosine schedule is sized in BATCHES. Rounds 6-7 sized it in candidates / cands_per_step,
    # which undercounts (a pool is never split across batches), so the last 9-15% of round 7's
    # reading epoch ran at learning rate 0.
    steps = max(1, epochs * _n_batches(sizes, cands_per_step))
    warm = min(100, steps // 10 + 1)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(s, steps) / steps)))
    out_dir.mkdir(parents=True, exist_ok=True)
    best, log, since = -1.0, [], 0
    print(f"[xreader:{name}] {len(by['train'])} train / {len(val)} val / {len(test)} test pools "
          f"({n_cands:,} train candidates), {arch['d_f']}-d backbone, {steps} steps", flush=True)
    for ep in range(epochs):
        lm.train()
        head.train()
        # same random draws as round 6b (a shift per pool, then a shuffle); pools are encoded lazily
        shifts = [rng.randint(-4, 4) if rng.random() < YEAR_SHIFT_P else 0 for _ in by["train"]]
        order = list(range(len(by["train"])))
        rng.shuffle(order)
        tr = (Encoded(sp, by["train"][i], shift=shifts[i]) for i in order)
        t0, tot, nb = time.time(), 0.0, 0
        for b in _batches(tr, cands_per_step):
            loss = _losses(_forward(lm, head, b, device, pad), b, teacher_w)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(list(lm.parameters()) + list(head.parameters()), 1.0)
            opt.step()
            sched.step()
            tot, nb = tot + loss.item(), nb + 1
            if nb % 2000 == 0:
                print(f"    [xreader:{name}] epoch {ep} step {nb} loss {tot / nb:.4f} ({time.time() - t0:.0f}s)", flush=True)
        sv = _scores(lm, head, val, device, pad, cands_per_step)
        acc = evaluate(sv, val, 1.0, 1.0, 0.0)["choice_acc"]
        log.append({"epoch": ep, "train_loss": tot / max(nb, 1), "val_choice_acc": acc, "s": round(time.time() - t0, 1)})
        print(f"  [xreader:{name}] epoch {ep}: loss {tot / max(nb, 1):.4f} val choice {acc:.3f} ({time.time() - t0:.0f}s)", flush=True)
        if acc > best:
            best, since = acc, 0
            torch.save({"lm": lm.state_dict(), "head": head.state_dict()}, out_dir / "weights.pt")
        else:
            since += 1
            if early_stop and since >= early_stop:
                print(f"  [xreader:{name}] early stop: no better validation in {since} epoch(s)", flush=True)
                break
    w = torch.load(out_dir / "weights.pt", map_location=device)
    lm.load_state_dict(w["lm"])
    head.load_state_dict(w["head"])
    sv = _scores(lm, head, val, device, pad, cands_per_step)
    T = fit_temperature(sv, val)
    a, b = fit_platt(*gate_data(sv, val, T))
    st = _scores(lm, head, test, device, pad, cands_per_step)
    metrics = {"name": name, "base": str(base_ckpt), "init": init, "tokenizer": str(tokenizer), "params": sum(p.numel() for p in lm.parameters()),
               "temperature": T, "platt": [a, b], "epochs": log, "best_val_choice_acc": best,
               "points": [str(p) for p in points], "n_points": {k: len(v) for k, v in by.items()},
               "pool_rule": "top16_as_served", "teacher_w": teacher_w, "early_stop": early_stop,
               "teacher_labelled": {k: sum(p.get("teacher") is not None for p in v) for k, v in by.items()},
               "schedule": {"unit": "batches", "steps": steps},
               "right_beyond_cut": {k: sum(bool(p.get("beyond")) for p in v) for k, v in by.items()},
               "test": evaluate(st, test, T, a, b),
               "test_teacher_agreement": teacher_agreement(st, test),
               "test_by_group": {g: evaluate([s for s, p in zip(st, by["test"]) if group_of(p["task_id"]) == g],
                                             [e for e, p in zip(test, by["test"]) if group_of(p["task_id"]) == g], T, a, b)
                                 for g in GROUPS if any(group_of(p["task_id"]) == g for p in by["test"])}}
    torch.save({"version": 7, "lm": lm.state_dict(), "head": head.state_dict(), "arch": arch, "tokenizer": str(tokenizer),
                "temperature": T, "platt": [a, b], "name": name, "base": str(base_ckpt)}, out_dir / "reader.pt")
    (out_dir / "weights.pt").unlink(missing_ok=True)
    write_json(out_dir / "train_log.json", metrics)
    t = metrics["test"]
    print(f"[xreader:{name}] test: choice {t['choice_acc']:.3f} vs ranker {t['ranker_acc']:.3f} on "
          f"{t['pools_with_a_right_candidate']} pools with a right one; gate AUC {t['gate_auc']}, ECE {t['gate_ece']}")
    for g, m in metrics["test_by_group"].items():
        print(f"    {g:<7} choice {m['choice_acc']:.3f} vs ranker {m['ranker_acc']:.3f} (n={m['pools_with_a_right_candidate']})")
    return metrics


# ── the reader (readers.py interface) ─────────────────────────────────────
class CrossReader:
    kind = "local"

    def __init__(self, checkpoint: str, device: str | None = None, prefix_cache: bool | None = None,
                 quant: str | None = None, max_cands: int = 0):
        """quant='int8': dynamic int8 weights for every Linear layer (CPU only; the phone proxy).
        max_cands: read only the top k candidates (default MAX_CANDS), the rest score 0. Round 11: up to
        MAX_READ, beyond what the reader was trained on (the view check; reported as untrained at that k)."""
        import sentencepiece as spm
        import torch
        from src.sgs_lm import SGSLanguageModel
        from .ckpt_io import load_sharded_or_pt, resolve_tokenizer_path
        self.torch = torch
        ck = load_sharded_or_pt(checkpoint)
        self.lm = SGSLanguageModel(**ck["arch"], return_hidden=True)
        incompat = self.lm.load_state_dict(ck["lm"], strict=False)
        missing = [k for k in incompat.missing_keys if not k.startswith("lm_head.")]
        unexpected = [k for k in incompat.unexpected_keys if not k.startswith("lm_head.")]
        if missing or unexpected:
            raise RuntimeError(f"Checkpoint mismatch in {checkpoint}: missing={missing}, unexpected={unexpected}")
        self.head = make_head(ck["arch"]["d_f"])
        self.head.load_state_dict(ck["head"])
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.lm.to(self.device).eval()
        self.head.to(self.device).eval()
        self.max_cands = min(max_cands or MAX_CANDS, MAX_READ)
        qeng = None
        if quant == "int8":
            if self.device != "cpu":
                raise SystemExit("--reader-quant int8 runs on CPU only (set CUDA_VISIBLE_DEVICES=-1)")
            eng = torch.backends.quantized.supported_engines           # x86: fbgemm/onednn; ARM (Macs): qnnpack
            qeng = next((e for e in ("fbgemm", "x86", "qnnpack", "onednn") if e in eng), None)
            if qeng:
                torch.backends.quantized.engine = qeng
                if hasattr(torch, "ao") and hasattr(torch.ao, "quantization"):
                    try:
                        self.lm = torch.ao.quantization.quantize_dynamic(
                            self.lm, {torch.nn.Linear}, dtype=torch.qint8
                        )
                    except Exception:
                        qeng = None
        elif quant:
            raise SystemExit(f"unknown reader quantization {quant!r} (int8)")
        self.config = {"quant": quant or "none", "max_cands": self.max_cands, "device": self.device,
                       "qengine": qeng if quant else None,
                       "threads": torch.get_num_threads(), "params": sum(p.numel() for p in self.lm.parameters())}
        if self.device == "cpu":
            self.config["size_mb"] = reader_size_mb(self.lm, self.head)
        tok_path = resolve_tokenizer_path(ck.get("tokenizer"), checkpoint)
        self.sp = spm.SentencePieceProcessor(model_file=str(tok_path))
        self.pad = self.sp.pad_id() if self.sp.pad_id() >= 0 else 0
        self.T, (self.a, self.b) = float(ck["temperature"]), ck["platt"]
        self.name = f"x-{ck.get('name', 'reader')}"
        # the shared-prefix KV cache pays off on CPU; on a GPU one padded batch is as fast
        self.prefix_cache = (self.device == "cpu") if prefix_cache is None else prefix_cache
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

    def logits(self, question: str, answer_type: str, pool: dict) -> np.ndarray:
        torch = self.torch
        e = Encoded(self.sp, {"question": question, "answer_type": answer_type, "cands": pool["cands"][:self.max_cands],
                              "labels": [False] * len(pool["cands"]), "snippet": pool.get("snippet", False)},
                    k_max=self.max_cands)
        if not self.prefix_cache:
            with torch.no_grad():
                return _forward(self.lm, self.head, [e], self.device, self.pad).float().cpu().numpy()
        with torch.no_grad():
            _, cache = self.lm.forward_cached(torch.tensor([e.prefix], device=self.device), hidden=True)
            n, L = len(e.conts), max(len(c) for c in e.conts)
            ids = torch.full((n, L), self.pad, dtype=torch.long)
            for i, c in enumerate(e.conts):
                ids[i, :len(c)] = torch.tensor(c)
            h, _ = self.lm.forward_cached(ids.to(self.device), self.lm.expand_cache(cache, n), hidden=True)
            h = h[torch.arange(n, device=h.device), torch.tensor([len(c) - 1 for c in e.conts], device=h.device)]
            ft = torch.tensor(e.feats, dtype=torch.float32, device=self.device)
            return self.head(torch.cat([h.float(), ft], -1)).cpu().numpy()

    def read(self, question: str, answer_type: str, pool: dict) -> list[float]:
        if not pool["cands"]:
            return []
        lg = self.logits(question, answer_type, pool)
        choice = _softmax(lg[:, 0], self.T)
        k = int(np.argmax(choice))
        g = 1 / (1 + math.exp(-(self.a * float(lg[k, 1]) + self.b)))
        r = [float(c * g) for c in choice]
        return r + [0.0] * (len(pool["cands"]) - len(r))       # beyond the top max_cands: not read


def reader_size_mb(lm, head) -> float:
    """Bytes the reader needs on the device: its weights as saved, without the LM head (the reader
    reads the hidden state and never predicts tokens)."""
    import io
    import torch
    buf = io.BytesIO()
    torch.save({"lm": {k: v for k, v in lm.state_dict().items() if not k.startswith("lm_head.")}, "head": head.state_dict()}, buf)
    return round(buf.tell() / 2 ** 20, 1)


def teach(points: Path, policy, limit: int = 0) -> dict:
    """Round 10: Gemma reads every pool of a points file once (the same READER_SYSTEM prompt and top-20
    view as the Gemma reader on the benchmark) and its pick is stored on the pool as {"k", "p"}. The file
    is rewritten in place; pools already taught are skipped, so an interrupted run resumes."""
    from .readers import LLMReader
    rd = LLMReader(policy)
    pts = read_jsonl(points)
    todo = [i for i, p in enumerate(pts) if p.get("teacher") is None and p.get("cands")][: limit or None]
    print(f"[xreader] Gemma reads {len(todo)} pools ({len(pts) - len(todo)} done or empty) -> {points}", flush=True)
    t0 = time.time()
    every = max(200, len(todo) // 60)      # round 12: a 30k-pool file is rewritten ~60 times, not 150
    for n, i in enumerate(todo, 1):
        p = pts[i]
        r = rd.read(p["question"], p["answer_type"], {"cands": p["cands"][:MAX_CANDS], "snippet": p.get("source") == "snippet"})
        k = int(np.argmax(r)) if r and max(r) > 0 else None
        p["teacher"] = {"k": k, "p": float(r[k]) if k is not None else 0.0, "by": policy.name}
        if n % every == 0 or n == len(todo):
            _write_jsonl(points, pts)
            print(f"  {n}/{len(todo)} pools ({(time.time() - t0) / n:.2f}s/pool)", flush=True)
    _write_jsonl(points, pts)
    taught = [p for p in pts if p.get("teacher")]
    agree = [bool(p["labels"][p["teacher"]["k"]]) for p in taught if p["teacher"]["k"] is not None and p["teacher"]["k"] < len(p["labels"]) and any(p["labels"])]
    out = {"pools": len(pts), "taught": len(taught), "teacher_right_when_a_right_one_exists": sum(agree) / max(len(agree), 1)}
    print(f"[xreader] teacher: {out}", flush=True)
    return out


def _write_jsonl(path: Path, rows: list[dict]):
    tmp = Path(path).with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(path)


# ── CLI ──────────────────────────────────────────────────────────────────
def add_cli(sub, add_web_args, build_web):
    p = sub.add_parser("xreader", help="round 6/7 reader: collect (search + label) | rcdata (round 7 reading sets) | train (planck|hertz)")
    p.add_argument("stage", choices=["collect", "rcdata", "train", "teach", "sample"])
    p.add_argument("--out", default=None, help="sample: where the sampled pools go")
    p.add_argument("--n", type=int, default=0, help="sample: how many pools (0 = copy all)")
    p.add_argument("--seed", type=int, default=12, help="sample: the seed")
    p.add_argument("--tasks", default=None, help="comma list (default: the Wikidata tasks + Gemma's news tasks)")
    p.add_argument("--points", default=str(READER_DIR / "points.jsonl"))
    p.add_argument("--stable-points", default=str(REPO_ROOT / "data" / "planck3" / "g2" / "points_ddgs.jsonl"),
                   help="round 4's labelled pools for the 1,455 round 3 training questions (reused, no search); 'none' to skip")
    p.add_argument("--init", default=None, help="start from a trained reader (round 7: the reading-skill reader)")
    p.add_argument("--max-eval", type=int, default=0, help="cap validation and test pools (large reading sets)")
    p.add_argument("--per-set", type=int, default=40000, help="rcdata: pools per reading set")
    p.add_argument("--neg", type=int, default=20000, help="rcdata: SQuAD 2.0 unanswerable pools")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--base", default="planck", choices=["planck", "hertz"])
    p.add_argument("--base-checkpoint", default=None)
    p.add_argument("--base-tokenizer", default=None)
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--lr", type=float, default=None)
    p.add_argument("--cands-per-step", type=int, default=None)
    p.add_argument("--max-points", type=int, default=0, help="quick runs: train on a sample")
    p.add_argument("--tag", default="")
    p.add_argument("--teacher-w", type=float, default=0.0, help="round 10: weight of Gemma's soft labels (pools with a 'teacher')")
    p.add_argument("--early-stop", type=int, default=0, help="stop after this many epochs without a better validation score")
    p.add_argument("--extra-points", default="", help="comma list of more pool files to train on (round 10: the Brave pools)")
    p.add_argument("--regimes", default="", help="collect: only these task regimes (round 10: recent,news)")
    add_web_args(p)                              # brings --gemma-path (round 10 teach)

    def run(a):
        if a.stage == "sample":
            if not a.out:
                raise SystemExit("xreader sample needs --out")
            if Path(a.out).exists():
                print(f"[xreader] {a.out} exists (kept: teach resumes on it)")
                return
            sample_points(Path(a.points), Path(a.out), a.n, a.seed)
            return
        if a.stage == "teach":
            from .policies import make_policy
            teach(Path(a.points), make_policy("gemma", gemma_path=a.gemma_path), a.limit)
            return
        if a.stage == "collect":
            from .g2 import collect
            from .readtasks import NEWS_TASKS, READ_TASKS
            files = a.tasks.split(",") if a.tasks else [str(READ_TASKS), str(NEWS_TASKS)]
            tasks = [t for f in files if Path(f).exists() for t in read_json(f)["tasks"]]
            if a.regimes:
                tasks = [t for t in tasks if t.get("regime") in a.regimes.split(",")]
            collect(tasks, build_web(a), Path(a.points), a.limit)
            return
        if a.stage == "rcdata":
            from .rcdata import build
            build(Path(a.points), per_set=a.per_set, neg=a.neg)
            return
        hertz = a.base == "hertz"
        ck = a.base_checkpoint or ("checkpoints/hertz/best.pt" if hertz else "checkpoints/planck13/best.pt")
        tok = a.base_tokenizer or ("data/hertz12_data/tokenizer.model" if hertz else "data/wikipedia/tokenizer.model")
        out = REPO_ROOT / "checkpoints" / f"xreader_{a.base}{a.tag}"
        extra = [Path(x) for x in a.extra_points.split(",") if x]
        meta = train([Path(a.stable_points), Path(a.points)] + extra, ck, tok, out, a.base, epochs=a.epochs,
                     lr=a.lr or (3e-5 if hertz else 5e-5), cands_per_step=a.cands_per_step or (32 if hertz else 64),
                     grad_checkpoint=hertz, max_points=a.max_points, init=a.init, max_eval=a.max_eval,
                     teacher_w=a.teacher_w, early_stop=a.early_stop)
        write_json(REPO_ROOT / "results" / "planck3" / f"xreader_{a.base}{a.tag}" / "train_log.json", meta)
    p.set_defaults(fn=run)
