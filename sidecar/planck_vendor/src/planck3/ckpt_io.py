"""
Sharded & precision-normalized checkpoint loader for shipped Planck models.

GitHub rejects individual files >= 100 MB without Git LFS, so shipped Planck
weights live as < 70 MB binary slices alongside a `manifest.json` file. This
module loads both standard single `.pt` checkpoints and sharded `manifest.json`
/ `.pt.partNNN` checkpoints transparently into CPU memory, upcasting any fp16
tensors cleanly to fp32.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any


def _upcast_fp16_state_dict(sd: dict[str, Any]) -> dict[str, Any]:
    import torch

    out: dict[str, Any] = {}
    for k, v in sd.items():
        if hasattr(v, "dtype") and v.dtype == torch.float16:
            out[k] = v.float()
        else:
            out[k] = v
    return out


def load_sharded_or_pt(path: str | Path) -> dict[str, Any]:
    import torch

    p = Path(path)
    if p.is_dir():
        manifest = p / "manifest.json"
        if manifest.is_file():
            p = manifest
        else:
            for cand_name in ("reader.pt", "best.pt", "final.pt", "model.pt"):
                if (p / cand_name).is_file():
                    p = p / cand_name
                    break

    if p.name == "manifest.json" or p.suffix.lower() == ".json":
        meta = json.loads(p.read_text(encoding="utf-8"))
        parts = [p.parent / str(name) for name in (meta.get("parts") or [])]
        if not parts:
            raise FileNotFoundError(f"Empty parts list in checkpoint manifest: {p}")
        buf = io.BytesIO()
        for part_path in parts:
            if not part_path.is_file():
                raise FileNotFoundError(f"Missing checkpoint shard: {part_path}")
            buf.write(part_path.read_bytes())
        buf.seek(0)
        ck = torch.load(buf, map_location="cpu", weights_only=False)
    elif p.is_file():
        ck = torch.load(p, map_location="cpu", weights_only=False)
    else:
        part0 = Path(f"{p}.part000")
        if part0.is_file():
            buf = io.BytesIO()
            idx = 0
            while True:
                part_p = Path(f"{p}.part{idx:03d}")
                if not part_p.is_file():
                    break
                buf.write(part_p.read_bytes())
                idx += 1
            buf.seek(0)
            ck = torch.load(buf, map_location="cpu", weights_only=False)
        else:
            raise FileNotFoundError(f"Checkpoint not found: {path}")

    if isinstance(ck, dict):
        for container_key in ("lm", "model"):
            if isinstance(ck.get(container_key), dict):
                ck[container_key] = _upcast_fp16_state_dict(ck[container_key])
        if "lm" not in ck and "model" not in ck and "tok_mu.weight" in ck:
            ck = _upcast_fp16_state_dict(ck)
    return ck


def resolve_tokenizer_path(
    raw_tokenizer: str | Path | None,
    checkpoint_path: str | Path | None = None,
) -> Path:
    vendor_root = Path(__file__).resolve().parent.parent.parent
    sidecar_root = vendor_root.parent
    candidates: list[Path] = []
    if raw_tokenizer:
        rt = Path(raw_tokenizer)
        candidates.append(rt)
        if checkpoint_path:
            cp = Path(checkpoint_path)
            candidates.append(cp.parent / rt.name)
            candidates.append(cp.parent.parent / rt.name)
        candidates.append(vendor_root / rt)
        candidates.append(sidecar_root / "models" / "planck" / rt.name)
        candidates.append(Path.cwd() / rt)
    candidates.extend(
        [
            sidecar_root / "models" / "planck" / "tokenizer.model",
            vendor_root / "data" / "wikipedia" / "tokenizer.model",
        ]
    )
    for cand in candidates:
        try:
            if cand.is_file():
                return cand
        except OSError:
            continue
    return Path(raw_tokenizer or "tokenizer.model")
