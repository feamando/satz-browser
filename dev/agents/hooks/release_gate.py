#!/usr/bin/env python3
"""Release Gate validator run prior to tagging or bundling standalone Satz releases."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOKS_DIR = Path(__file__).resolve().parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pre_commit_dev_sync import check_privacy_and_secrets, check_ui_and_weight_limits, check_version_parity


def _run(cmd: list[str], label: str, *, extra_env: dict[str, str] | None = None) -> None:
    print(f"[release-gate] {label}: {' '.join(cmd)}", flush=True)
    env = dict(os.environ)
    cargo_bin = Path.home() / ".cargo" / "bin"
    if cargo_bin.is_dir() and str(cargo_bin) not in env.get("PATH", ""):
        env["PATH"] = f"{cargo_bin}{os.pathsep}{env.get('PATH', '')}"
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        shell=(sys.platform == "win32" and cmd[0] in ("npm", "node", "npx")),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Release gate step failed ({proc.returncode}): {label}")


def _check_runtime_imports() -> None:
    required = (
        ("PIL", "pillow"),
        ("argon2", "argon2-cffi"),
        ("keyring", "keyring"),
        ("httpx", "httpx"),
        ("torch", "torch"),
        ("transformers", "transformers"),
        ("trafilatura", "trafilatura"),
        ("ddgs", "ddgs"),
    )
    missing = []
    for mod_name, pkg_name in required:
        try:
            __import__(mod_name)
        except ImportError:
            missing.append(pkg_name)
    if missing:
        raise RuntimeError(
            "Python environment is missing sidecar/requirements-runtime.txt package(s): "
            + ", ".join(missing)
            + ". Install with uv pip install -r sidecar/requirements-runtime.txt."
        )


def _staged_python_path() -> Path | None:
    base = REPO_ROOT / "src-tauri" / "target" / "staged-resources"
    if not (base / "sidecar" / "satz_models.py").is_file():
        return None
    cands = (
        [base / "python-runtime" / "python.exe"]
        if sys.platform == "win32"
        else [base / "python-runtime" / "bin" / "python3", base / "python-runtime" / "bin" / "python3.12"]
    )
    return next((c for c in cands if c.is_file()), None)


def main() -> int:
    parser = argparse.ArgumentParser(description="Satz Release Gate validator")
    parser.add_argument("--quick", action="store_true", help="Skip Rust cargo test & full sidecar suite")
    args = parser.parse_args()

    ver = check_version_parity()
    check_ui_and_weight_limits()
    check_privacy_and_secrets(mode="all")
    print(f"[release-gate] Version & privacy security audit verified: {ver}", flush=True)

    _run(["npm", "run", "build"], "Frontend tsc + Vite build")
    _run(["node", "scripts/i18n_extract.mjs", "--check"], "i18n catalog & AST check")

    if not args.quick:
        _check_runtime_imports()
        _run(["cargo", "test", "--manifest-path", "src-tauri/Cargo.toml"], "Rust cargo test")
        _run(
            [
                sys.executable,
                "-m",
                "unittest",
                "sidecar.test_local_models",
                "sidecar.test_i18n",
                "sidecar.test_m16",
                "sidecar.test_m18",
                "sidecar.test_satz_models",
                "sidecar.test_settings_tools",
                "sidecar.test_web_harness",
                "sidecar.test_satz_news",
                "sidecar.test_telemetry",
                "sidecar.test_translation",
                "sidecar.test_profile_transfer",
                "sidecar.test_dev_brain",
            ],
            "Sidecar unittest regression suite",
            extra_env={
                "SATZ_MEMORY_KEYRING": "1",
                "SATZ_DISABLE_AUTO_NEWS_SYNC": "1",
                "PYTHONUTF8": "1",
            },
        )
        staged_py = _staged_python_path()
        if staged_py is not None:
            staged_sidecar = REPO_ROOT / "src-tauri" / "target" / "staged-resources" / "sidecar"
            smoke_code = (
                "import pathlib, sys, tempfile; "
                f"sys.path.insert(0, {str(staged_sidecar)!r}); "
                "from satz_models import SatzSidecarRuntime; "
                "\nwith tempfile.TemporaryDirectory(prefix='satz_gate_') as td:\n"
                "    d = pathlib.Path(td)\n"
                "    rt = SatzSidecarRuntime(sgs_root=d/'no_sgs', store_path=d/'s.sqlite')\n"
                "    try:\n"
                "        assert not rt.sgs_root.exists()\n"
                "        rt.passwords.create_profile('GateSmoke', '123456')\n"
                "        res = rt.run_read('planck (reader)', 'Who created Ada?', [{'id':'1','url':'https://example.org','title':'T','text':'In 1843 Ada published notes.'}])\n"
                "        assert 'answer' in res\n"
                "    finally:\n"
                "        rt.close()\n"
            )
            _run(
                [str(staged_py), "-I", "-c", smoke_code],
                "Isolated staged python-runtime (-I, zero ../sgs)",
                extra_env={
                    "PYTHONNOUSERSITE": "1",
                    "PYTHONUTF8": "1",
                    "SATZ_MEMORY_KEYRING": "1",
                    "SATZ_DISABLE_AUTO_NEWS_SYNC": "1",
                },
            )

    from dev_brain import DevBrain

    brain = DevBrain(REPO_ROOT)
    brain.reindex()
    mon = brain.monitor()
    if not mon["ok"]:
        raise RuntimeError(f"Dev Brain monitor failed: {mon}")
    ev = brain.evaluate(min_mrr=0.70, min_recall5=0.85)
    print(
        f"[release-gate] Dev Brain eval: hit@1={ev['hit_at_1']:.3f} recall@5={ev['recall_at_5']:.3f} mrr={ev['mrr']:.3f}",
        flush=True,
    )
    if not ev["passed"]:
        raise RuntimeError(f"Dev Brain eval below release gate threshold: {ev}")

    print("[release-gate] ALL GATES PASSED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
