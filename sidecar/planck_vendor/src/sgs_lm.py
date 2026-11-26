"""
Causal SGS Language Model — Radiance Planck (100M).

Architecture: Semantic Gaussian Splatting with alpha-compositing rendering.
Each token is a Gaussian in splatting space. Multi-head, multi-pass
causal rendering composes meaning from visible tokens.

Key design:
  - Causal mask (diagonal=0): position t sees tokens 0..t, predicts t+1
  - Factored kernel: avoids materializing [B, L, L, d_s] diff tensors
  - Heads processed sequentially to limit VRAM
  - Transmittance via log-cumsum for numerical stability
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.checkpoint import checkpoint as grad_checkpoint


class SGSLanguageModel(nn.Module):
    """
    Causal language model using Semantic Gaussian Splatting.

    At each position, multi-head alpha-compositing rendering composes
    a meaning vector from causally visible token Gaussians. Multi-pass
    refinement updates Gaussian parameters between rendering passes.
    """

    def __init__(
        self,
        vocab_size: int = 32000,
        d_s: int = 128,
        d_f: int = 1000,      # ~100M params with default settings
        n_passes: int = 3,
        n_heads: int = 4,
        max_len: int = 512,
        tau_init: float = 128.0,
        ffn_mult: int = 4,
        dropout: float = 0.0,
        use_checkpoint: bool = False,
        # ── Planck 1.2 accel flags (§2.1-§2.4, all default off) ──
        # See docs/plans/planck_12_plan.md. When any of these are set,
        # forward returns (logits, T_diag, passes_run) instead of logits.
        return_accel_state: bool = False,   # enables the tuple return
        adaptive_passes: bool = False,      # §2.2
        ap_eps: float = 0.02,
        ap_min_step: int = 2000,
        sparse_k: int = 0,                  # §2.3; 0 = disabled
        sparse_warmup_steps: int = 5000,
        sparse_tau_gate: float = 30.0,
        shared_kernel: bool = False,        # §2.4
        # ── Planck 1.2.1 additions (§2.4 sharing schedule) ──
        # "always"  — cache K from pass 0, reuse in every subsequent pass
        #             (matches the 1.2 `shared_kernel=True` behaviour).
        # "mix"     — cache K from pass 0, recompute in middle passes,
        #             reuse only in the last pass. Softens the quality
        #             regression seen in 1.2's shk run.
        # "late"    — recompute in all passes until `shk_switch_step`,
        #             then switch to `mix` for the remainder of training.
        shk_schedule: str = "always",
        shk_switch_step: int = 20000,
        # Planck 1.2.1 Liger hook: when True, forward returns the pre-head
        # hidden state (post-LN) instead of logits, so the caller can run
        # a fused linear+CE kernel (liger_kernel.FusedLinearCrossEntropy).
        # Combined with return_accel_state it yields (hidden, T_diag,
        # passes_run). Eval always disables this for comparability.
        return_hidden: bool = False,
    ):
        super().__init__()
        self.vocab_size = vocab_size
        self.d_s = d_s
        self.d_f = d_f
        self.n_passes = n_passes
        self.n_heads = n_heads
        self.max_len = max_len
        self.use_checkpoint = use_checkpoint

        # Accel flags — plain attributes, not buffers. They are fixed per
        # training run so we don't need them in state_dict. `opt_step`
        # must be set externally by the training loop (default 0 means
        # warmup-based gates block sparsity until it's bumped).
        self.return_accel_state = return_accel_state
        self.adaptive_passes = adaptive_passes
        self.ap_eps = ap_eps
        self.ap_min_step = ap_min_step
        self.sparse_k = int(sparse_k)
        self.sparse_warmup_steps = sparse_warmup_steps
        self.sparse_tau_gate = sparse_tau_gate
        self.shared_kernel = shared_kernel
        self.shk_schedule = shk_schedule
        self.shk_switch_step = int(shk_switch_step)
        self.return_hidden = return_hidden
        self.opt_step = 0

        # ── Gaussian vocabulary (learned from scratch) ──
        self.tok_mu = nn.Embedding(vocab_size, d_s)
        self.tok_log_var = nn.Embedding(vocab_size, d_s)
        self.tok_raw_alpha = nn.Embedding(vocab_size, 1)
        self.tok_features = nn.Embedding(vocab_size, d_f)

        # ── Position embeddings (added to μ in splatting space) ──
        self.pos_mu = nn.Embedding(max_len, d_s)

        # ── Learned temperature ──
        self.log_tau = nn.Parameter(torch.tensor(math.log(tau_init)))

        # ── Multi-head query projection (single matmul for all heads) ──
        self.query_proj = nn.Linear(d_s, n_heads * d_s, bias=True)

        # ── Head combination → d_f ──
        self.head_proj = nn.Linear(n_heads * d_f, d_f)

        # ── Per-pass update networks (between rendering passes) ──
        self.mu_update = nn.ModuleList()
        self.alpha_gate = nn.ModuleList()
        self.pass_ffn = nn.ModuleList()
        for _ in range(n_passes - 1):
            self.mu_update.append(
                nn.Sequential(nn.Linear(d_f * 2, d_s), nn.Tanh())
            )
            self.alpha_gate.append(
                nn.Sequential(nn.Linear(d_f * 2, 1), nn.Sigmoid())
            )
            self.pass_ffn.append(
                nn.Sequential(
                    nn.LayerNorm(d_f * 2),
                    nn.Linear(d_f * 2, d_f * ffn_mult),
                    nn.GELU(),
                    nn.Linear(d_f * ffn_mult, d_f),
                )
            )

        # ── Output ──
        self.ln_f = nn.LayerNorm(d_f)
        self.lm_head = nn.Linear(d_f, vocab_size, bias=False)

        self.dropout = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

        self._init_weights()

    # ────────────────────────────────────────────────────────────
    # Initialization
    # ────────────────────────────────────────────────────────────

    def _init_weights(self):
        # Token embeddings
        nn.init.normal_(self.tok_mu.weight, std=0.02)
        nn.init.zeros_(self.tok_log_var.weight)       # Σ = I
        nn.init.zeros_(self.tok_raw_alpha.weight)      # α = 0.5
        nn.init.normal_(self.tok_features.weight, std=0.02)

        # Position embeddings — small so they modulate, not dominate
        nn.init.normal_(self.pos_mu.weight, std=0.01)

        # Query projection — block-diagonal near-identity
        nn.init.zeros_(self.query_proj.bias)
        with torch.no_grad():
            w = torch.zeros(self.n_heads * self.d_s, self.d_s)
            for h in range(self.n_heads):
                w[h*self.d_s:(h+1)*self.d_s, :] = torch.eye(self.d_s)
            self.query_proj.weight.copy_(w)

        # Head projection — scaled for residual-like accumulation
        nn.init.normal_(
            self.head_proj.weight,
            std=0.02 / math.sqrt(2 * self.n_passes),
        )
        nn.init.zeros_(self.head_proj.bias)

        # Per-pass MLPs
        for modules in [self.mu_update, self.alpha_gate, self.pass_ffn]:
            for block in modules:
                for m in block.modules():
                    if isinstance(m, nn.Linear):
                        nn.init.normal_(m.weight, std=0.02)
                        if m.bias is not None:
                            nn.init.zeros_(m.bias)

        # LM head
        nn.init.normal_(self.lm_head.weight, std=0.02)

    # ────────────────────────────────────────────────────────────
    # Core ops
    # ────────────────────────────────────────────────────────────

    @property
    def tau(self) -> torch.Tensor:
        return self.log_tau.exp()

    def _pairwise_kernel(
        self,
        queries: torch.Tensor,
        mu: torch.Tensor,
        log_var: torch.Tensor,
    ) -> torch.Tensor:
        """
        Memory-efficient pairwise Gaussian kernel.

        Factored computation avoids materializing [B, L, L, d_s]:
          M[t,j] = q_t² · iv_j  −  2·q_t · (μ_j·iv_j)  +  μ_j²·iv_j

        Args:
            queries: [B, L, d_s]
            mu:      [B, L, d_s]
            log_var: [B, L, d_s]
        Returns:
            K: [B, L, L]  kernel values in (0, 1]
        """
        iv = torch.exp(-log_var)                               # [B, L, d_s]
        mu_iv = mu * iv                                        # [B, L, d_s]
        mu2_iv_sum = (mu * mu_iv).sum(-1)                      # [B, L]
        q_sq = queries * queries                               # [B, L, d_s]

        # Three [B, L, L] terms via bmm — no [B, L, L, d_s] intermediate
        term1 = torch.bmm(q_sq, iv.transpose(1, 2))           # [B, L, L]
        term2 = torch.bmm(queries, mu_iv.transpose(1, 2))     # [B, L, L]

        mahal = term1 - 2.0 * term2 + mu2_iv_sum.unsqueeze(1) # [B, L, L]
        return torch.exp(-0.5 * mahal / self.tau)

    def _causal_render(
        self,
        features: torch.Tensor,
        alpha: torch.Tensor,
        K: torch.Tensor,
        causal_mask: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Causal alpha-compositing rendering.

        For each position t, renders meaning from visible tokens:
          w[t,j] = α_j · K[t,j] · T[t,j]
          T[t,j] = Π_{k<j} (1 − α_k · K[t,k])   (only over visible k)
          meaning[t] = Σ_j w[t,j] · f[j]

        Args:
            features:    [B, L, d_f]
            alpha:       [B, L]
            K:           [B, L, L]
            causal_mask: [L, L]
        Returns:
            meaning: [B, L, d_f]
            T_diag:  [B, L] — transmittance at the predicted position
                     (i.e. T[t,t]). Used by §2.1/§2.2.
        """
        # Effective opacity per (query_pos, key_pos)
        eff_a = alpha.unsqueeze(1) * K                         # [B, L, L]
        eff_a = eff_a * causal_mask                            # zero out future
        eff_a = eff_a.clamp(min=0.0, max=1.0 - 1e-6)

        # Transmittance via log-cumsum (numerically stable)
        log_1ma = torch.log1p(-eff_a)                          # [B, L, L]
        log_cum = log_1ma.cumsum(dim=-1)                       # [B, L, L]

        # Shift right: T[t, 0] = 1
        log_T = torch.cat(
            [torch.zeros_like(log_cum[:, :, :1]), log_cum[:, :, :-1]],
            dim=-1,
        )
        T = log_T.exp()                                        # [B, L, L]

        # Blending weights and render
        weights = eff_a * T                                    # [B, L, L]
        meaning = torch.bmm(weights, features)                 # [B, L, d_f]

        # Diagonal T[t,t] — confidence signal for §2.1 loss weighting
        # and §2.2 early-exit. Gathered here so callers don't have to
        # re-derive it from the [B, L, L] tensor.
        T_diag = T.diagonal(dim1=-2, dim2=-1)                  # [B, L]
        return meaning, T_diag

    def _causal_render_sparse(
        self,
        features: torch.Tensor,
        alpha: torch.Tensor,
        mahal: torch.Tensor,
        causal_mask: torch.Tensor,
        k: int,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Top-k sparse causal alpha-compositing render (§2.3, Tier B).

        For each query position t, keep only the k keys with smallest
        Mahalanobis distance (highest kernel weight) among causally
        visible keys (j <= t), then run log-cumsum + bmm over those
        k entries only. Cost: O(B·L·k) instead of O(B·L·L) for
        cumsum + render.

        Args:
            features:    [B, L, d_f]
            alpha:       [B, L]
            mahal:       [B, L, L] — Mahalanobis distance (pre-exp)
            causal_mask: [L, L]
            k:           max keys per query (clamped to L).
        Returns:
            meaning: [B, L, d_f]
            T_diag:  [B, L]
        """
        B, L, d_f = features.shape
        k = min(k, L)

        # Mask future keys by making their distance huge → never in top-k.
        huge = mahal.new_full((), 1e9)
        mahal_causal = torch.where(
            causal_mask.bool().unsqueeze(0),                  # [1, L, L]
            mahal,
            huge.expand_as(mahal),
        )

        # Smallest distance = highest kernel weight.
        # top_idx[:, t, :] are the k key positions selected for query t.
        _, top_idx = torch.topk(mahal_causal, k=k, dim=-1, largest=False)  # [B, L, k]

        # Transmittance must accumulate in causal order (ascending key
        # position), so sort the selected keys by index. This preserves
        # the left-to-right alpha-composite semantics.
        top_idx, _ = torch.sort(top_idx, dim=-1)              # [B, L, k]

        # Gather the corresponding kernel values and alpha.
        top_mahal = torch.gather(mahal_causal, -1, top_idx)   # [B, L, k]
        K_top = torch.exp(-0.5 * top_mahal / self.tau)         # [B, L, k]

        alpha_exp = alpha.unsqueeze(1).expand(B, L, L)        # [B, L, L]
        alpha_top = torch.gather(alpha_exp, -1, top_idx)      # [B, L, k]

        eff_a = (alpha_top * K_top).clamp(min=0.0, max=1.0 - 1e-6)

        # Log-cumsum over the k keys — cheaper than full-L cumsum.
        log_1ma = torch.log1p(-eff_a)                         # [B, L, k]
        log_cum = log_1ma.cumsum(dim=-1)
        log_T = torch.cat(
            [torch.zeros_like(log_cum[:, :, :1]), log_cum[:, :, :-1]],
            dim=-1,
        )
        T = log_T.exp()                                       # [B, L, k]
        weights = eff_a * T                                   # [B, L, k]

        # Gather feature rows for the selected keys and reduce. 1.2.2:
        # the advanced-indexing form `features[batch_idx, top_idx]` had
        # the right forward shape but its autograd path builds a
        # [B, L, L, d_f] intermediate on backward (1.2.1 OOM at step
        # 9.9k / 29.9k for sk / all). Flat `index_select` has
        # index_add backward that touches only selected rows.
        flat = features.reshape(B * L, d_f)
        offsets = (torch.arange(B, device=features.device) * L).view(B, 1, 1)
        global_idx = (top_idx + offsets).reshape(-1)          # [B*L*k]
        top_feats = flat.index_select(0, global_idx).view(B, L, k, d_f)
        meaning = (weights.unsqueeze(-1) * top_feats).sum(dim=2)  # [B, L, d_f]

        # Diagonal T[t,t] proxy for §2.1/§2.2. In dense render T[t,t] is
        # the transmittance accumulated over keys with position < t. In
        # the sparse selection, we approximate that as the fully-absorbed
        # transmittance across all selected keys (i.e. how much context
        # the query absorbed from its top-k neighbours). For queries where
        # t itself is in the top-k, use the accurate T at that slot.
        arange_L = torch.arange(L, device=mahal.device).view(1, L, 1)
        match = (top_idx == arange_L)                         # [B, L, k]
        has_self = match.any(dim=-1)                          # [B, L]
        self_pos = match.float().argmax(dim=-1)               # [B, L]
        T_self = torch.gather(T, -1, self_pos.unsqueeze(-1)).squeeze(-1)
        T_fallback = log_cum[..., -1].exp()                   # [B, L]
        T_diag = torch.where(has_self, T_self, T_fallback)
        return meaning, T_diag

    def _pairwise_mahal(
        self,
        queries: torch.Tensor,
        mu: torch.Tensor,
        log_var: torch.Tensor,
    ) -> torch.Tensor:
        """Pairwise Mahalanobis distance (pre-exp). Same factored form as
        `_pairwise_kernel` but returns the raw distance so sparse rendering
        can run top-k in distance space."""
        iv = torch.exp(-log_var)
        mu_iv = mu * iv
        mu2_iv_sum = (mu * mu_iv).sum(-1)
        q_sq = queries * queries
        term1 = torch.bmm(q_sq, iv.transpose(1, 2))
        term2 = torch.bmm(queries, mu_iv.transpose(1, 2))
        return term1 - 2.0 * term2 + mu2_iv_sum.unsqueeze(1)

    def _render_pass(
        self,
        mu: torch.Tensor,
        log_var: torch.Tensor,
        alpha: torch.Tensor,
        features: torch.Tensor,
        causal_mask: torch.Tensor,
        K_cached: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Single rendering pass: all heads in parallel → combine. Checkpointable.

        Returns (meaning, T_diag, K_all). K_all is returned so §2.4
        (shared kernel) can reuse it across passes; it is the kernel
        (not the raw distance) and is always dense at the [B*H, L, L]
        shape. When `K_cached` is provided it takes the sparse-path
        decision out of our hands: we render densely with the cached
        kernel. T_diag has shape [B*H, L].
        """
        B, L, d_s = mu.shape
        H = self.n_heads
        d_f = self.d_f

        # All head queries in one matmul: [B, L, d_s] → [B, L, H*d_s] → [B*H, L, d_s]
        all_q = self.query_proj(mu)                                # [B, L, H*d_s]
        all_q = all_q.view(B, L, H, d_s).permute(0, 2, 1, 3)     # [B, H, L, d_s]
        all_q = all_q.reshape(B * H, L, d_s)                      # [B*H, L, d_s]

        # Expand mu/log_var/alpha/features for all heads
        mu_h = mu.unsqueeze(1).expand(B, H, L, d_s).reshape(B * H, L, d_s)
        lv_h = log_var.unsqueeze(1).expand(B, H, L, d_s).reshape(B * H, L, d_s)
        al_h = alpha.unsqueeze(1).expand(B, H, L).reshape(B * H, L)
        ft_h = features.unsqueeze(1).expand(B, H, L, d_f).reshape(B * H, L, d_f)

        # §2.3 top-k sparsity gate: only active past warmup AND when the
        # kernel is sharp enough (small τ) for top-k to be meaningful.
        # Disabled when shared_kernel is driving this call with a cached K.
        sparse_active = (
            self.sparse_k > 0
            and K_cached is None
            and self.opt_step >= self.sparse_warmup_steps
            and float(self.tau.detach()) <= self.sparse_tau_gate
        )

        if sparse_active:
            mahal = self._pairwise_mahal(all_q, mu_h, lv_h)       # [B*H, L, L]
            m_all, T_all = self._causal_render_sparse(
                ft_h, al_h, mahal, causal_mask, self.sparse_k,
            )
            # Reconstitute K_all from mahal only if downstream needs it
            # (§2.4 shared-kernel path never combines with sparse in one
            # run; return None-equivalent sentinel). Use the dense kernel
            # exp for passes that might cache it; cheap vs. the render.
            K_all = torch.exp(-0.5 * mahal / self.tau)
        else:
            if K_cached is not None:
                K_all = K_cached
            else:
                K_all = self._pairwise_kernel(all_q, mu_h, lv_h)  # [B*H, L, L]
            m_all, T_all = self._causal_render(ft_h, al_h, K_all, causal_mask)

        # Reshape back: [B*H, L, d_f] → [B, H, L, d_f] → [B, L, H*d_f]
        m_all_r = m_all.view(B, H, L, d_f).permute(0, 2, 1, 3)    # [B, L, H, d_f]
        m_cat = m_all_r.reshape(B, L, H * d_f)                    # [B, L, H*d_f]
        meaning = self.head_proj(m_cat)                           # [B, L, d_f]

        # Aggregate T across heads for the outer loop (mean over heads
        # gives a per-query confidence signal).
        T_diag = T_all.view(B, H, L).mean(dim=1)                  # [B, L]
        return meaning, T_diag, K_all

    # ────────────────────────────────────────────────────────────
    # Forward
    # ────────────────────────────────────────────────────────────

    def forward(self, token_ids: torch.Tensor):
        """
        Causal language model forward pass.

        Args:
            token_ids: [B, L] token indices
        Returns:
            Default (no accel flags set):
                logits: [B, L, vocab_size]
                        logits[:, t, :] predicts token at position t+1
            When `return_accel_state=True` (set by accel flags):
                (logits, T_diag, passes_run)
                  T_diag:     [B, L] — final-pass transmittance at t=t
                  passes_run: int — number of passes actually executed
        """
        B, L = token_ids.shape
        device = token_ids.device

        # ── Activate Gaussians ──
        mu = self.tok_mu(token_ids)                            # [B, L, d_s]
        log_var = self.tok_log_var(token_ids)                  # [B, L, d_s]
        alpha = torch.sigmoid(
            self.tok_raw_alpha(token_ids).squeeze(-1)
        )                                                      # [B, L]
        features = self.tok_features(token_ids)                # [B, L, d_f]

        # ── Position modulation ──
        pos = torch.arange(L, device=device)
        mu = mu + self.pos_mu(pos).unsqueeze(0)

        # ── Causal mask: position t sees tokens 0..t ──
        causal_mask = torch.tril(torch.ones(L, L, device=device))

        # ── Multi-pass rendering ──
        meaning = None
        T_diag = None
        K_cache = None                  # §2.4 shared kernel
        T_prev_pass = None              # §2.2 adaptive exit
        passes_run = 0

        # §2.4 schedule: resolve the effective mode for this step.
        # `late` is just `mix` with a warmup that disables kernel reuse.
        if self.shk_schedule == "late" and self.opt_step < self.shk_switch_step:
            active_schedule = "off"
        elif self.shk_schedule == "late":
            active_schedule = "mix"
        else:
            active_schedule = self.shk_schedule  # "always" or "mix" or "off"

        for p in range(self.n_passes):
            # §2.4: once we've computed the kernel in pass 0, reuse it.
            # - "always": reuse cache on every p > 0.
            # - "mix"   : reuse cache only on the final pass.
            # - "off"   : never reuse (regular per-pass kernels).
            if not self.shared_kernel or active_schedule == "off":
                reuse = False
            elif active_schedule == "mix":
                reuse = (p == self.n_passes - 1) and p > 0
            else:  # "always"
                reuse = p > 0
            k_in = K_cache if reuse else None

            if self.use_checkpoint and self.training:
                meaning, T_diag, K_all = grad_checkpoint(
                    self._render_pass, mu, log_var, alpha, features,
                    causal_mask, k_in, use_reentrant=False,
                )
            else:
                meaning, T_diag, K_all = self._render_pass(
                    mu, log_var, alpha, features, causal_mask, K_cached=k_in,
                )
            # Cache from pass 0 if any downstream pass will reuse it.
            if self.shared_kernel and p == 0 and active_schedule != "off":
                K_cache = K_all.detach() if not self.training else K_all

            meaning = self.dropout(meaning)
            passes_run = p + 1

            # §2.2 adaptive early exit — only in training past min-step.
            # Measure on T_diag rather than full T to keep the comparison
            # cheap and batch-level (we skip the remaining passes for the
            # whole batch when the signal stabilises).
            if (
                self.adaptive_passes
                and self.training
                and self.opt_step >= self.ap_min_step
                and p < self.n_passes - 1
                and T_prev_pass is not None
            ):
                delta = (T_diag - T_prev_pass).abs().max().item()
                if delta < self.ap_eps:
                    break
            T_prev_pass = T_diag.detach()

            # Update Gaussian params for next pass
            if p < self.n_passes - 1:
                ctx = torch.cat([features, meaning], dim=-1)    # [B, L, 2·d_f]
                mu = mu + self.mu_update[p](ctx)
                alpha = alpha * self.alpha_gate[p](ctx).squeeze(-1)
                features = features + self.pass_ffn[p](ctx)

        # ── Output ──
        # Liger path: caller fuses `hidden @ lm_head.weight.T` + CE in a
        # single Triton kernel. Skip the materialised logits tensor.
        if self.return_hidden:
            hidden = self.ln_f(meaning)                        # [B, L, d_f]
            if self.return_accel_state:
                return hidden, T_diag, passes_run
            return hidden

        logits = self.lm_head(self.ln_f(meaning))              # [B, L, V]

        if self.return_accel_state:
            return logits, T_diag, passes_run
        return logits

    # ────────────────────────────────────────────────────────────
    # Incremental decoding (Planck 3.0 round 6): a cache of past Gaussians
    # ────────────────────────────────────────────────────────────

    def forward_cached(self, token_ids: torch.Tensor, cache: dict | None = None,
                       hidden: bool = False) -> tuple[torch.Tensor, dict]:
        """
        forward() for NEW tokens only, given the state of every earlier token.

        Exact, not an approximation: a token's Gaussian at every pass (μ, α, features)
        depends only on tokens at or before it, so earlier tokens never change when a
        token is appended. The cache keeps, per pass, the Gaussians of all tokens so far
        (log-variance is never updated, so it is stored once). A step then costs
        O(t) instead of O(t²) per pass.

        Args:
            token_ids: [B, n] new tokens (n = prompt length for the first call)
            cache:     None, or the dict returned by the previous call
            hidden:    return the post-LN hidden state instead of logits
        Returns:
            (logits or hidden [B, n, ·], cache covering all tokens so far)
        """
        if self.sparse_k or self.shared_kernel:
            raise NotImplementedError("forward_cached supports the dense, per-pass kernel only")
        B, n = token_ids.shape
        S = cache["n"] if cache is not None else 0
        if S + n > self.max_len:
            raise ValueError(f"{S + n} tokens exceed the {self.max_len}-token context")
        device = token_ids.device
        mu = self.tok_mu(token_ids) + self.pos_mu(torch.arange(S, S + n, device=device)).unsqueeze(0)
        log_var = self.tok_log_var(token_ids)
        alpha = torch.sigmoid(self.tok_raw_alpha(token_ids).squeeze(-1))
        features = self.tok_features(token_ids)
        lv_all = log_var if cache is None else torch.cat([cache["lv"], log_var], 1)
        # new query i sits at position S + i and sees keys 0 .. S + i
        mask = torch.ones(n, S + n, device=device).tril(diagonal=S)
        new = {"n": S + n, "lv": lv_all, "mu": [], "alpha": [], "feat": []}
        H, d_s, d_f = self.n_heads, self.d_s, self.d_f
        meaning = None
        for p in range(self.n_passes):
            if cache is None:
                mu_all, al_all, ft_all = mu, alpha, features
            else:
                mu_all = torch.cat([cache["mu"][p], mu], 1)
                al_all = torch.cat([cache["alpha"][p], alpha], 1)
                ft_all = torch.cat([cache["feat"][p], features], 1)
            new["mu"].append(mu_all)
            new["alpha"].append(al_all)
            new["feat"].append(ft_all)
            T_ = S + n
            q = self.query_proj(mu).view(B, n, H, d_s).permute(0, 2, 1, 3).reshape(B * H, n, d_s)
            mu_h = mu_all.unsqueeze(1).expand(B, H, T_, d_s).reshape(B * H, T_, d_s)
            lv_h = lv_all.unsqueeze(1).expand(B, H, T_, d_s).reshape(B * H, T_, d_s)
            al_h = al_all.unsqueeze(1).expand(B, H, T_).reshape(B * H, T_)
            ft_h = ft_all.unsqueeze(1).expand(B, H, T_, d_f).reshape(B * H, T_, d_f)
            K = self._pairwise_kernel(q, mu_h, lv_h)                       # [B*H, n, S+n]
            m_all, _ = self._causal_render(ft_h, al_h, K, mask)            # [B*H, n, d_f]
            meaning = self.head_proj(m_all.view(B, H, n, d_f).permute(0, 2, 1, 3).reshape(B, n, H * d_f))
            if p < self.n_passes - 1:
                ctx = torch.cat([features, meaning], dim=-1)
                mu = mu + self.mu_update[p](ctx)
                alpha = alpha * self.alpha_gate[p](ctx).squeeze(-1)
                features = features + self.pass_ffn[p](ctx)
        h = self.ln_f(meaning)
        return (h if hidden else self.lm_head(h)), new

    @staticmethod
    def expand_cache(cache: dict, k: int) -> dict:
        """One prefix, k continuations: repeat a batch-1 cache k times (shared question, many candidates)."""
        rep = lambda t: t.expand(k, *t.shape[1:])  # noqa: E731
        return {"n": cache["n"], "lv": rep(cache["lv"]), "mu": [rep(t) for t in cache["mu"]],
                "alpha": [rep(t) for t in cache["alpha"]], "feat": [rep(t) for t in cache["feat"]]}

    # ────────────────────────────────────────────────────────────
    # Generation
    # ────────────────────────────────────────────────────────────

    @torch.no_grad()
    def generate(
        self,
        prompt_ids: torch.Tensor,
        max_new: int = 200,
        temperature: float = 0.8,
        top_k: int = 50,
    ) -> torch.Tensor:
        """Autoregressive generation with top-k sampling."""
        self.eval()
        ids = prompt_ids.clone()

        # Generation never wants the accel-state tuple — always take
        # the plain-logits path even when flags are set.
        was_returning = self.return_accel_state
        self.return_accel_state = False
        for _ in range(max_new):
            ctx = ids[:, -self.max_len :]
            logits = self.forward(ctx)[:, -1, :]
            logits = logits / max(temperature, 1e-8)

            if top_k > 0:
                v, _ = logits.topk(min(top_k, logits.size(-1)))
                logits[logits < v[:, [-1]]] = float("-inf")

            probs = F.softmax(logits, dim=-1)
            next_id = torch.multinomial(probs, 1)
            ids = torch.cat([ids, next_id], dim=1)

        self.return_accel_state = was_returning
        return ids

    # ────────────────────────────────────────────────────────────
    # Utilities
    # ────────────────────────────────────────────────────────────

    def count_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def param_breakdown(self) -> dict[str, int]:
        """Parameter count by component."""
        groups = {
            "tok_mu": self.tok_mu.weight.numel(),
            "tok_log_var": self.tok_log_var.weight.numel(),
            "tok_raw_alpha": self.tok_raw_alpha.weight.numel(),
            "tok_features": self.tok_features.weight.numel(),
            "pos_mu": self.pos_mu.weight.numel(),
            "log_tau": 1,
            "query_proj": sum(p.numel() for p in self.query_proj.parameters()),
            "head_proj": sum(p.numel() for p in self.head_proj.parameters()),
            "mu_update": sum(
                p.numel() for m in self.mu_update for p in m.parameters()
            ),
            "alpha_gate": sum(
                p.numel() for m in self.alpha_gate for p in m.parameters()
            ),
            "pass_ffn": sum(
                p.numel() for m in self.pass_ffn for p in m.parameters()
            ),
            "ln_f": sum(p.numel() for p in self.ln_f.parameters()),
            "lm_head": self.lm_head.weight.numel(),
        }
        groups["total"] = sum(groups.values())
        return groups


def migrate_state_dict(state: dict) -> dict:
    """Convert a legacy (pre-e2956ff) Planck state_dict to current layout.

    Before e2956ff, query_proj was a ModuleList of n_heads separate Linear(d_s, d_s)
    projections, producing keys: query_proj.0.weight, query_proj.0.bias, ...
    Current layout is a single fused Linear(d_s, n_heads * d_s), producing
    query_proj.weight / query_proj.bias.

    Mathematically the fused layout is a block stack of the per-head layers,
    so the migration is a lossless concatenation. If the state already uses
    the fused layout, this is a no-op.
    """
    if "query_proj.weight" in state:
        return state  # already fused
    per_head_keys = sorted(
        (k for k in state if k.startswith("query_proj.") and k.endswith(".weight")),
        key=lambda k: int(k.split(".")[1]),
    )
    if not per_head_keys:
        return state  # unrecognized layout, let load_state_dict raise its own error
    weights = [state.pop(k) for k in per_head_keys]
    biases = [
        state.pop(k.replace(".weight", ".bias"))
        for k in per_head_keys
        if k.replace(".weight", ".bias") in state
    ]
    state["query_proj.weight"] = torch.cat(weights, dim=0)  # [H*d_s, d_s]
    if biases:
        state["query_proj.bias"] = torch.cat(biases, dim=0)  # [H*d_s]
    return state
