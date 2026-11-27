---
name: satz-sidecar-models-boundary
description: >-
  Use this skill when editing sidecar/ Python inference, planck_vendor/, shipped Planck
  weights, Hugging Face downloads, local model linking, or PyTorch CPU compatibility.
---

# Satz Sidecar & Local Models Boundary Skill

Models Module: [satz_local_models.py](../../../../sidecar/satz_local_models.py) · Server: [satz_models.py](../../../../sidecar/satz_models.py) · Error Log: [error_log.jsonl](../../evals/error_log.jsonl)

## Critical Invariants (Learned From Postmortems)
1. **Zero Runtime `../sgs` Dependency:** All inference and Brain embedding paths must run from `sidecar/planck_vendor/` and `sidecar/models/planck/` even when `../sgs` is missing. Never edit sibling `../sgs`.
2. **Shipped Planck Shard Cap (<90 MB):** Split checkpoints under `sidecar/models/planck/` via `torch_sharded_v1` `manifest.json` (`<90 MB` per `.part*`, never enable Git LFS).
3. **PyTorch CPU Engine Safety (`err-xreader-onednn-stopiteration`):** Keep `CrossReader` (`planck_vendor/src/planck3/xreader.py`) supporting `onednn` and safe float32 fallback on PyTorch `2.15+`.
4. **No Silent Deprecated/Missing-Model Failures (`err-cloud-cache-key-mismatch`):** Missing `gemma-4-e4b` (e.g., on clean macOS) must skip preload cleanly, log transparent fallbacks, and use `cloud_models_<pid>`.

## Verification
```powershell
..\sgs\.venv\Scripts\python.exe -m unittest sidecar.test_local_models sidecar.test_satz_models sidecar.test_dev_brain -v
```
Also verify isolated staged runtime execution (`python.exe -I` with `PYTHONNOUSERSITE=1` and zero `../sgs`).
