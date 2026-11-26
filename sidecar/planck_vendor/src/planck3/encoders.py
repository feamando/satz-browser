"""
Text -> vector encoders for the Planck 3.0 heads.

    hash     hashed unigram+bigram TF vectors. No model, deterministic. It is the
             control: if heads on Planck features don't beat heads on hash
             features, Planck is adding nothing (report it, don't hide it).
    planck   frozen Planck 1.3 (or any SGSLanguageModel checkpoint): mean-pooled
             post-LN hidden states (return_hidden=True), L2-normalised.
    hertz    the same over Hertz 1.2 (640M, d_f=3700): the G1 capacity ablation.
"""

import zlib

import numpy as np

from .util import content_words


class HashEncoder:
    name = "hash"

    def __init__(self, dim: int = 1024):
        self.dim = dim

    def encode(self, texts: list[str], batch_size: int = 0, progress: bool = False) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            w = content_words(t)
            feats = w + [f"{a}_{b}" for a, b in zip(w, w[1:])]
            for f in feats:
                h = zlib.crc32(f.encode("utf-8"))
                out[i, h % self.dim] += 1.0 if (h >> 31) & 1 else -1.0
        n = np.linalg.norm(out, axis=1, keepdims=True)
        return (out / np.maximum(n, 1e-6)).astype(np.float16)


class PlanckEncoder:
    name = "planck"

    def __init__(self, checkpoint: str, tokenizer: str, device: str | None = None, max_len: int = 64):
        import sentencepiece as spm
        import torch
        from scripts.generate import infer_arch
        from src.sgs_lm import SGSLanguageModel, migrate_state_dict
        from .ckpt_io import load_sharded_or_pt, resolve_tokenizer_path

        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        tok_path = resolve_tokenizer_path(tokenizer, checkpoint)
        self.sp = spm.SentencePieceProcessor(model_file=str(tok_path))
        ckpt = load_sharded_or_pt(checkpoint)
        state = migrate_state_dict(ckpt["model"] if "model" in ckpt else ckpt)
        arch = infer_arch(state)
        self.max_len = min(max_len, arch["max_len"])
        self.model = SGSLanguageModel(**arch, return_hidden=True)
        incompat = self.model.load_state_dict(state, strict=False)
        missing = [k for k in incompat.missing_keys if not k.startswith("lm_head.")]
        unexpected = [k for k in incompat.unexpected_keys if not k.startswith("lm_head.")]
        if missing or unexpected:
            raise RuntimeError(f"Encoder checkpoint mismatch in {checkpoint}: missing={missing}, unexpected={unexpected}")
        self.model.to(self.device).eval()
        for p in self.model.parameters():
            p.requires_grad = False
        self.dim = arch["d_f"]
        self.pad_id = self.sp.pad_id() if self.sp.pad_id() >= 0 else 0

    def encode(self, texts: list[str], batch_size: int = 256, progress: bool = False) -> np.ndarray:
        torch = self.torch
        ids = [self.sp.encode(t, out_type=int)[: self.max_len] or [self.sp.unk_id()] for t in texts]
        order = np.argsort([len(x) for x in ids])  # length-bucket to cut padding
        out = np.zeros((len(texts), self.dim), dtype=np.float16)
        use_amp = self.device.startswith("cuda")
        for bi, start in enumerate(range(0, len(ids), batch_size)):
            idx = order[start:start + batch_size]
            L = max(len(ids[i]) for i in idx)
            tok = torch.full((len(idx), L), self.pad_id, dtype=torch.long)
            mask = torch.zeros((len(idx), L), dtype=torch.float32)
            for r, i in enumerate(idx):
                tok[r, : len(ids[i])] = torch.tensor(ids[i])
                mask[r, : len(ids[i])] = 1.0
            tok, mask = tok.to(self.device), mask.to(self.device)
            with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16, enabled=use_amp):
                h = self.model(tok).float()                      # [B, L, d_f]; causal, so right-pad is inert
            v = (h * mask.unsqueeze(-1)).sum(1) / mask.sum(1, keepdim=True)
            v = torch.nn.functional.normalize(v, dim=-1)
            out[idx] = v.cpu().numpy().astype(np.float16)
            if progress and bi % 50 == 0:
                print(f"  encoded {min(start + batch_size, len(ids)):,}/{len(ids):,}", flush=True)
        return out


def make_encoder(name: str, **kw):
    if name == "hash":
        return HashEncoder()
    if name in ("planck", "hertz"):  # any SGSLanguageModel checkpoint; hertz = Hertz 1.2 (640M) ablation
        enc = PlanckEncoder(kw["checkpoint"], kw["tokenizer"], device=kw.get("device"))
        enc.name = name
        return enc
    raise ValueError(f"unknown encoder {name}")
