#!/usr/bin/env python3
"""Stage clean sidecar/ sources, shipped Planck weights, and a relocatable
Python 3.12 runtime into src-tauri/target/staged-resources/ for Tauri bundling.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIDECAR_SRC = REPO_ROOT / "sidecar"
DEFAULT_STAGE_DIR = REPO_ROOT / "src-tauri" / "target" / "staged-resources"
REQ_FILE = SIDECAR_SRC / "requirements-runtime.txt"

_SKIP_DIR_NAMES = {"__pycache__", ".pytest_cache", ".git", ".mypy_cache"}
_SIDECAR_SUBDIRS = ("satz_tools", "planck_vendor", "models", "config")
_SIDECAR_EXTRA_FILES = ("news_registry_overlay.json", "requirements.txt", "requirements-runtime.txt")


def _parse_requirements(req_path: Path) -> tuple[list[str], list[str]]:
    torch_reqs: list[str] = []
    other_reqs: list[str] = []
    for raw in req_path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.lower().startswith("torch"):
            torch_reqs.append(line)
        else:
            other_reqs.append(line)
    return torch_reqs, other_reqs


def _ignore_sidecar_entries(_dir: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for n in names:
        if n in _SKIP_DIR_NAMES or n.endswith((".pyc", ".pyo")) or n.startswith("test_"):
            ignored.add(n)
    return ignored


def stage_sidecar(out_dir: Path) -> Path:
    dest = out_dir / "sidecar"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    for py_file in sorted(SIDECAR_SRC.glob("*.py")):
        if py_file.name.startswith("test_"):
            continue
        shutil.copy2(py_file, dest / py_file.name)

    for fname in _SIDECAR_EXTRA_FILES:
        src = SIDECAR_SRC / fname
        if src.is_file():
            shutil.copy2(src, dest / fname)

    for sub in _SIDECAR_SUBDIRS:
        src_sub = SIDECAR_SRC / sub
        if src_sub.is_dir():
            if sub == "models":
                # Stage shipped Planck artifacts only; never sweep dev user downloads
                planck_src = src_sub / "planck"
                if planck_src.is_dir():
                    shutil.copytree(
                        planck_src,
                        dest / "models" / "planck",
                        ignore=_ignore_sidecar_entries,
                    )
            else:
                shutil.copytree(
                    src_sub,
                    dest / sub,
                    ignore=_ignore_sidecar_entries,
                )

    print(f"[stage] sidecar staged at {dest}", flush=True)
    return dest


def _find_uv() -> str:
    uv_bin = shutil.which("uv")
    if uv_bin:
        return uv_bin
    for cand in (
        Path.home() / ".local" / "bin" / "uv",
        Path.home() / ".cargo" / "bin" / "uv",
        Path.home() / ".local" / "bin" / "uv.exe",
    ):
        if cand.is_file():
            return str(cand)
    raise RuntimeError(
        "uv CLI not found on PATH. Install uv (https://docs.astral.sh/uv/) to stage relocatable Python 3.12."
    )


def _staged_python_exe(py_root: Path) -> Path:
    if sys.platform == "win32":
        return py_root / "python.exe"
    for rel in ("bin/python3", "bin/python3.12", "bin/python"):
        cand = py_root / rel
        if cand.exists():
            return cand
    return py_root / "bin" / "python3"


def _verify_staged_python(py_exe: Path) -> bool:
    if not py_exe.is_file():
        return False
    check_code = (
        "import torch, transformers, sentencepiece, safetensors, huggingface_hub, "
        "cryptography, argon2, keyring, yaml, httpx, requests, lxml, trafilatura, "
        "ddgs, PIL, sklearn, numpy; print('OK', torch.__version__)"
    )
    proc = subprocess.run(
        [str(py_exe), "-I", "-c", check_code],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONNOUSERSITE": "1", "PYTHONUTF8": "1"},
    )
    if proc.returncode == 0:
        print(f"[stage] runtime check passed: {proc.stdout.strip()}", flush=True)
        return True
    print(f"[stage] runtime check failed: {proc.stderr.strip()}", flush=True)
    return False


def _slim_python_tree(py_root: Path) -> None:
    if sys.platform == "win32":
        stdlib_root = py_root / "Lib"
        prune_dirs = [
            stdlib_root / "test",
            stdlib_root / "idlelib",
            stdlib_root / "tkinter",
            stdlib_root / "turtledemo",
            stdlib_root / "ensurepip",
            py_root / "tcl",
        ]
    else:
        py_lib = next(iter(sorted((py_root / "lib").glob("python3.*"))), py_root / "lib" / "python3.12")
        prune_dirs = [
            py_lib / "test",
            py_lib / "idlelib",
            py_lib / "tkinter",
            py_lib / "turtledemo",
            py_lib / "ensurepip",
            py_root / "share",
        ]
    for d in prune_dirs:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
    for cache_dir in py_root.rglob("__pycache__"):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir, ignore_errors=True)


def stage_python_runtime(
    out_dir: Path,
    *,
    cuda: bool = False,
    force: bool = False,
    slim: bool = True,
) -> Path:
    py_root = out_dir / "python-runtime"
    req_hash = hashlib.sha256(REQ_FILE.read_bytes()).hexdigest()[:16]
    stamp_val = f"{sys.platform}-{platform.machine().lower()}-{'cuda' if cuda else 'cpu'}-{req_hash}"
    stamp_file = py_root / ".satz_runtime_stamp"

    staged_py = _staged_python_exe(py_root)
    if (
        not force
        and stamp_file.is_file()
        and stamp_file.read_text(encoding="utf-8").strip() == stamp_val
        and _verify_staged_python(staged_py)
    ):
        print(f"[stage] reusing cached python-runtime ({stamp_val})", flush=True)
        return py_root

    uv = _find_uv()
    print("[stage] ensuring relocatable Python 3.12 via uv...", flush=True)
    subprocess.run([uv, "python", "install", "3.12", "--managed-python"], check=True)
    find_proc = subprocess.run(
        [uv, "python", "find", "3.12", "--managed-python"],
        capture_output=True,
        text=True,
        check=True,
    )
    src_py = Path(find_proc.stdout.strip())
    src_root = src_py.parent if sys.platform == "win32" else src_py.parent.parent
    if not src_root.is_dir():
        raise RuntimeError(f"Managed Python root does not exist: {src_root}")

    tmp_root = out_dir / "python-runtime.staging"
    if tmp_root.exists():
        shutil.rmtree(tmp_root)
    print(f"[stage] copying standalone Python from {src_root} -> {tmp_root}", flush=True)
    shutil.copytree(src_root, tmp_root, symlinks=(sys.platform != "win32"))
    for em in tmp_root.rglob("EXTERNALLY-MANAGED"):
        em.unlink(missing_ok=True)

    staged_py_tmp = _staged_python_exe(tmp_root)
    torch_reqs, other_reqs = _parse_requirements(REQ_FILE)

    if torch_reqs:
        cmd_torch = [
            uv,
            "pip",
            "install",
            "--python",
            str(staged_py_tmp),
            "--break-system-packages",
            "--no-cache",
        ]
        if sys.platform == "win32" and not cuda:
            cmd_torch.extend(["--index-url", "https://download.pytorch.org/whl/cpu"])
        cmd_torch.extend(torch_reqs)
        print(f"[stage] installing PyTorch ({'cuda' if cuda else 'cpu'}): {' '.join(torch_reqs)}", flush=True)
        subprocess.run(cmd_torch, check=True)

    if other_reqs:
        cmd_other = [
            uv,
            "pip",
            "install",
            "--python",
            str(staged_py_tmp),
            "--break-system-packages",
            "--no-cache",
            "--no-upgrade",
            *other_reqs,
        ]
        print(f"[stage] installing {len(other_reqs)} runtime packages...", flush=True)
        subprocess.run(cmd_other, check=True)

    if slim:
        _slim_python_tree(tmp_root)

    if not _verify_staged_python(staged_py_tmp):
        raise RuntimeError("Staged python-runtime failed verification import check.")

    (tmp_root / ".satz_runtime_stamp").write_text(stamp_val + "\n", encoding="utf-8")
    if py_root.exists():
        shutil.rmtree(py_root)
    tmp_root.replace(py_root)
    print(f"[stage] python-runtime ready at {py_root}", flush=True)
    return py_root


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare staged sidecar & relocatable Python for Tauri bundle.")
    parser.add_argument("--out", default=str(DEFAULT_STAGE_DIR), help="Staging output root directory.")
    parser.add_argument("--sidecar-only", action="store_true", help="Only restage sidecar/ scripts & models.")
    parser.add_argument("--force-python", action="store_true", help="Rebuild python-runtime even if stamp matches.")
    parser.add_argument("--cuda", action="store_true", help="Use default/CUDA PyTorch wheel on Windows instead of CPU.")
    parser.add_argument("--no-slim", action="store_true", help="Keep stdlib test/tk folders & __pycache__.")
    args = parser.parse_args()

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stage_sidecar(out_dir)
    if not args.sidecar_only:
        stage_python_runtime(
            out_dir,
            cuda=bool(args.cuda),
            force=bool(args.force_python),
            slim=not bool(args.no_slim),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
