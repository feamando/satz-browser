"""
Planck 3.0 pointer head: scores each candidate independently (the Jev trick that
sidesteps the 512-token window), trained on cached encoder embeddings.

    score(c | target t, node n) = MLP([c', t'*c', n'*c', |t'-c'|]) + w * cos(t, c)

    x' = LayerNorm(Linear(x)). The cosine skip gives every head a lexical prior;
    the MLP must earn anything above it.
Loss: multi-positive NLL = logsumexp(all) - logsumexp(gold).
"""

import math

import torch
import torch.nn as nn
import torch.nn.functional as F


class PointerHead(nn.Module):
    def __init__(self, dim: int, hidden: int = 256, dropout: float = 0.1):
        super().__init__()
        self.pt, self.pn, self.pc = (nn.Sequential(nn.Linear(dim, hidden), nn.LayerNorm(hidden)) for _ in range(3))
        self.mlp = nn.Sequential(nn.Linear(4 * hidden, hidden), nn.GELU(), nn.Dropout(dropout),
                                 nn.Linear(hidden, 1))
        self.cos_w = nn.Parameter(torch.tensor(5.0))
        self.log_temp = nn.Parameter(torch.zeros(()), requires_grad=False)  # set by calibration

    def forward(self, e_t, e_n, e_c):
        """e_t, e_n: [B, D]; e_c: [B, C, D] -> logits [B, C] (pre-temperature)."""
        t, n, c = self.pt(e_t).unsqueeze(1), self.pn(e_n).unsqueeze(1), self.pc(e_c)
        feat = torch.cat([c, t * c, n * c, (t - c).abs()], dim=-1)
        cos = F.cosine_similarity(e_t.unsqueeze(1), e_c, dim=-1)
        return self.mlp(feat).squeeze(-1) + self.cos_w * cos

    @property
    def temperature(self) -> float:
        return float(self.log_temp.exp())


def multi_positive_nll(logits, gold_mask, cand_mask):
    neg_inf = torch.finfo(logits.dtype).min
    all_l = logits.masked_fill(~cand_mask, neg_inf)
    gold_l = logits.masked_fill(~(gold_mask & cand_mask), neg_inf)
    return (torch.logsumexp(all_l, -1) - torch.logsumexp(gold_l, -1)).mean()


def fit_temperature(logits_list, gold_list) -> float:
    """Grid-search T minimising multi-positive NLL on held-out steps."""
    best_t, best = 1.0, math.inf
    for t in [0.2 * 1.12 ** i for i in range(45)]:
        nll = 0.0
        for lg, gm in zip(logits_list, gold_list):
            z = lg / t
            nll += float(torch.logsumexp(z, 0) - torch.logsumexp(z[gm], 0))
        if nll < best:
            best_t, best = t, nll
    return best_t
