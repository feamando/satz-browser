#!/usr/bin/env python3
"""
Pre-push & continuous security/privacy monitor for Satz-Browser.

Reuses regexes and sanitization helpers from `sidecar/satz_evals.py` to detect:
1. Private keys, signing keys, vaults, profile archives, and local runtime DBs.
2. API keys, OAuth/VCS/cloud tokens, Bearer headers, and secret URL query parameters.
3. Unscrubbed local OS home directory paths (`C:\\Users\\<user>`, `/Users/<user>`, `/home/<user>`).
4. Unanonymized real/personal emails, IBANs, or PII outside synthetic unit-test fixtures.
5. Hidden strings inside committed SQLite databases (`dev/brain/brain_index.sqlite`).

Also provides text/file anonymization (`scrub_text`) and cross-platform Git hook installation.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SIDECAR_DIR = REPO_ROOT / "sidecar"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))

from satz_brain import ADDRESS_LINE_RE, BOOKING_OR_TRACKING_RE, EMAIL_RE  # noqa: E402
from satz_evals import (  # noqa: E402
    _API_SECRET_RE,
    _IBAN_RE,
    _PERSONAL_MAIL_DOMAINS,
    _POSIX_USER_PATH_RE,
    _URL_SECRET_PARAM_RE,
    _WIN_USER_PATH_RE,
    sanitize_text_for_eval,
)

PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----"
)
EXTRA_SECRET_RE = re.compile(
    r"(?:github_pat_[0-9A-Za-z_]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[0-9A-Za-z-]{10,}|"
    r"sk_live_[0-9A-Za-z]{16,}|rk_live_[0-9A-Za-z]{16,}|"
    r"TAURI_SIGNING_PRIVATE_KEY\s*[:=]\s*['\"]?[A-Za-z0-9+/=]{16,})"
)

BLOCKED_FILENAMES = {
    ".env",
    "vault.enc",
    "planck_store.sqlite",
    "mail.sqlite",
    "drives.sqlite",
    "raw_events.sqlite",
    "telemetry.sqlite",
    "id_rsa",
    "id_ed25519",
    ".minisign.key",
}
BLOCKED_EXTENSIONS = {".pem", ".key", ".p12", ".pfx", ".kdbx", ".satzprofile"}
TEXT_SCAN_EXTS = {
    ".py", ".ts", ".js", ".mjs", ".rs", ".toml", ".json", ".jsonl",
    ".yaml", ".yml", ".md", ".css", ".html", ".ps1", ".sh", ".txt",
}

SYNTHETIC_TEST_MARKERS = re.compile(
    r"(?:test|fake|mock|dummy|example|sample|placeholder|neverechoed|should_be_stripped|redacted|1234567890|abc123|0000)",
    re.I,
)
SAFE_USERNAMES = {
    "user", "username", "yourname", "alice", "bob", "nikita", "runner", "runneradmin",
    "admin", "runner_user", "<user>", "<username>", "<user_home>", "...",
}
WIN_PATH_STRICT_RE = re.compile(r"[A-Za-z]:\\Users\\([A-Za-z0-9._-]+)", re.I)
POSIX_PATH_STRICT_RE = re.compile(r"(?:/Users/|/home/)([A-Za-z0-9._-]+)")
SAFE_EMAIL_LITERALS = {
    "you@gmail.com",
    "alice@gmail.com",
    "work@gmail.com",
    "peer@gmail.com",
    "demo@gmail.com",
    "tester@gmail.com",
    "name@company.example",
    "anna@x.com",
    "clara@studiob.de",
    "notifications@github.com",
    "noreply@github.com",
}
SAFE_EMAIL_DOMAIN_SUFFIXES = (".example", ".test", ".local", ".invalid", "@users.noreply.github.com")
RESTRICTED_DOMAINS = ("hellofresh.com", "hellofresh.de")
EVAL_ANONYMIZED_EMAIL_RE = re.compile(r"^(?:sender|user)-\d+@")
PROSE_BEARER_WORDS = {"token", "tokens", "header", "headers", "auth"}


def _active_usernames() -> set[str]:
    names: set[str] = set()
    for candidate in (
        os.environ.get("USERNAME", ""),
        os.environ.get("USER", ""),
        getpass.getuser() if callable(getattr(getpass, "getuser", None)) else "",
    ):
        clean = str(candidate or "").strip().lower()
        if clean and len(clean) >= 3 and clean not in SAFE_USERNAMES:
            names.add(clean)
    return names


def redact_text(text: str) -> str:
    """Scrub API keys, private keys, secret URL params, OS usernames, IBANs, and emails."""
    raw = str(text or "")
    if not raw:
        return ""
    scrubbed = PRIVATE_KEY_RE.sub("[PRIVATE_KEY_REDACTED]", raw)
    scrubbed = EXTRA_SECRET_RE.sub("[SECRET_KEY]", scrubbed)
    scrubbed = sanitize_text_for_eval(scrubbed)

    def _mask_user_path(m: re.Match[str]) -> str:
        val = m.group(0)
        parts = re.split(r"[\\/]", val)
        if parts and parts[-1].lower() not in SAFE_USERNAMES:
            return "<USER_HOME>"
        return val

    scrubbed = _WIN_USER_PATH_RE.sub(_mask_user_path, scrubbed)
    scrubbed = _POSIX_USER_PATH_RE.sub(_mask_user_path, scrubbed)
    return scrubbed


def _is_test_or_fixture_path(rel_posix: str) -> bool:
    low = rel_posix.lower()
    base = low.rsplit("/", 1)[-1]
    return (
        base.startswith("test_")
        or "/test_" in low
        or low.startswith("docs/smoke/")
        or low == "sidecar/satz_evals.py"
    )


def scan_text_content(
    rel_posix: str,
    text: str,
    *,
    strict_eval_path: bool | None = None,
) -> list[dict[str, Any]]:
    """Return security/privacy findings found in `text` for repo-relative path `rel_posix`."""
    findings: list[dict[str, Any]] = []
    if not text:
        return findings

    low_rel = rel_posix.lower()
    is_test_file = _is_test_or_fixture_path(rel_posix)
    in_eval_or_behavior = (
        strict_eval_path
        if strict_eval_path is not None
        else (
            low_rel.startswith("dev/agents/evals/")
            or low_rel.startswith("dev/agents/behavior/")
            or low_rel.startswith("docs/evals/")
        )
    )
    os_users = _active_usernames()

    for line_no, line in enumerate(text.splitlines(), start=1):
        if "security-audit: allow" in line:
            continue

        # 1. Private key blocks & hard secret assignments (never permitted in repo files)
        if PRIVATE_KEY_RE.search(line) or EXTRA_SECRET_RE.search(line):
            # Allow documentation regex examples describing the rule inside security_audit / pre_tool_guard / satz_evals
            if not (low_rel in ("scripts/security_audit.py", "dev/agents/hooks/pre_tool_guard.py", "sidecar/satz_evals.py")):
                findings.append(
                    {
                        "severity": "high",
                        "category": "private_key_or_secret",
                        "path": rel_posix,
                        "line": line_no,
                        "snippet": line.strip()[:100],
                    }
                )

        # 2. Cloud/HF/API tokens
        for m in _API_SECRET_RE.finditer(line):
            tok = m.group(0)
            if tok.lower().startswith("bearer "):
                body = tok.split(None, 1)[1].strip()
                if len(body) < 14 or body.lower() in PROSE_BEARER_WORDS:
                    continue
                if is_test_file and ("refreshed-token" in body.lower() or SYNTHETIC_TEST_MARKERS.search(body)):
                    continue
            if is_test_file and SYNTHETIC_TEST_MARKERS.search(tok):
                continue
            if "security_audit.py" in low_rel or "pre_tool_guard.py" in low_rel:
                continue
            if "..." in tok or "<" in tok:
                continue
            findings.append(
                {
                    "severity": "high",
                    "category": "api_or_auth_token",
                    "path": rel_posix,
                    "line": line_no,
                    "snippet": f"{tok[:10]}...[redacted]",
                }
            )

        # 3. Secret URL params
        for m in _URL_SECRET_PARAM_RE.finditer(line):
            val = m.group(2)
            cleaned_val = val.strip(")`\"',;:")
            if cleaned_val in ("[REDACTED]", "...", "YOUR_KEY") or cleaned_val.startswith(("<", "{", "$")):
                continue
            if cleaned_val.lower().rstrip(".") in ("abc", "xyz", "foo", "bar", "123", "example"):
                continue
            if low_rel in ("docs/evals/readme.md", "scripts/security_audit.py"):
                continue
            if is_test_file:
                # Allow benign query placeholders, flagging high-entropy tokens
                if len(val) < 28 or SYNTHETIC_TEST_MARKERS.search(val):
                    continue
            findings.append(
                {
                    "severity": "high",
                    "category": "url_secret_param",
                    "path": rel_posix,
                    "line": line_no,
                    "snippet": f"{m.group(1)}[redacted]",
                }
            )

        # 4. Local OS user home paths (e.g. C:\Users\<actual_user>)
        for pat in (WIN_PATH_STRICT_RE, POSIX_PATH_STRICT_RE):
            for m in pat.finditer(line):
                full_p = m.group(0)
                user_seg = m.group(1).lower()
                if user_seg in SAFE_USERNAMES:
                    continue
                if is_test_file and user_seg not in os_users:
                    continue
                if user_seg in os_users or not is_test_file:
                    findings.append(
                        {
                            "severity": "medium",
                            "category": "local_user_path_leak",
                            "path": rel_posix,
                            "line": line_no,
                            "snippet": full_p[:80],
                        }
                    )

        # 5. Unanonymized corporate/personal emails
        for m in EMAIL_RE.finditer(line):
            addr = m.group(0).lower()
            dom = addr.split("@", 1)[1] if "@" in addr else ""
            if addr.endswith((".png", ".jpg", ".svg", ".webp")):
                continue
            if addr in SAFE_EMAIL_LITERALS or any(addr.endswith(s) for s in SAFE_EMAIL_DOMAIN_SUFFIXES):
                continue
            if in_eval_or_behavior and EVAL_ANONYMIZED_EMAIL_RE.match(addr):
                continue
            if is_test_file:
                continue
            is_private = dom in _PERSONAL_MAIL_DOMAINS or dom in RESTRICTED_DOMAINS or in_eval_or_behavior
            if is_private:
                findings.append(
                    {
                        "severity": "medium",
                        "category": "unanonymized_email",
                        "path": rel_posix,
                        "line": line_no,
                        "snippet": f"***@{dom}",
                    }
                )

        # 6. IBANs in non-test files
        if not is_test_file and _IBAN_RE.search(line):
            findings.append(
                {
                    "severity": "high",
                    "category": "iban_pii",
                    "path": rel_posix,
                    "line": line_no,
                    "snippet": "[IBAN detected]",
                }
            )

    return findings


def _scan_sqlite_file(db_path: Path, rel_posix: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not db_path.is_file():
        return findings
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=2.0)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for tbl in tables:
            if tbl.startswith("nodes_fts"):
                continue
            for row in conn.execute(f'SELECT * FROM "{tbl}"').fetchall():
                joined = " ".join(str(col) for col in row if isinstance(col, str))
                if not joined:
                    continue
                for f in scan_text_content(f"{rel_posix}#{tbl}", joined, strict_eval_path=True):
                    findings.append(f)
                    if len(findings) >= 15:
                        return findings
    except Exception:
        return findings
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return findings


def _git_files_for_mode(mode: str, repo_root: Path) -> list[str]:
    def _git(args: list[str]) -> list[str]:
        res = subprocess.run(["git", *args], cwd=str(repo_root), capture_output=True, text=True, timeout=5)
        if res.returncode != 0:
            return []
        return [ln.strip().replace("\\", "/") for ln in res.stdout.splitlines() if ln.strip()]

    if mode == "staged":
        return _git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    if mode == "unpushed":
        upstream = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
        files: set[str] = set()
        if upstream:
            files.update(_git(["diff", "--name-only", "--diff-filter=ACMR", f"{upstream[0]}..HEAD"]))
        else:
            files.update(_git(["ls-files"]))
        # Also include currently modified/staged paths so pre-push checks catch dirty unpushed files too
        files.update(_git(["diff", "--name-only", "--diff-filter=ACMR"]))
        files.update(_git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"]))
        return sorted(files)

    tracked = set(_git(["ls-files"]))
    tracked.update(_git(["ls-files", "--others", "--exclude-standard"]))
    for extra_root in ("dev", "scripts", "sidecar", "src"):
        base = repo_root / extra_root
        if not base.is_dir():
            continue
        for fp in base.rglob("*"):
            if not fp.is_file():
                continue
            rel = fp.relative_to(repo_root).as_posix()
            # Skip gitignored raw local captures/logs
            if rel.endswith(("raw_events.sqlite", "worker.log")) or "/__pycache__/" in rel:
                continue
            tracked.add(rel)
    return sorted(tracked)


def run_audit(
    *,
    mode: str = "all",
    paths: list[str] | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    root = (repo_root or REPO_ROOT).resolve()
    target_rels = sorted(set(p.replace("\\", "/") for p in paths)) if paths is not None else _git_files_for_mode(mode, root)
    findings: list[dict[str, Any]] = []
    scanned = 0

    for rel in target_rels:
        fp = root / rel
        if not fp.is_file():
            continue
        scanned += 1
        base = fp.name.lower()
        ext = fp.suffix.lower()
        if base in BLOCKED_FILENAMES or ext in BLOCKED_EXTENSIONS:
            # Allow only dev/brain/brain_index.sqlite among sqlite files
            if rel != "dev/brain/brain_index.sqlite":
                findings.append(
                    {
                        "severity": "critical",
                        "category": "blocked_sensitive_file",
                        "path": rel,
                        "line": 0,
                        "snippet": f"Sensitive file `{rel}` must never be committed or pushed.",
                    }
                )
                continue

        if ext == ".sqlite" and rel == "dev/brain/brain_index.sqlite":
            findings.extend(_scan_sqlite_file(fp, rel))
            continue

        if ext in TEXT_SCAN_EXTS or ext == "":
            try:
                if fp.stat().st_size > 2 * 1024 * 1024:
                    continue
                content = fp.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            findings.extend(scan_text_content(rel, content))

    return {
        "ok": len(findings) == 0,
        "mode": mode,
        "files_scanned": scanned,
        "finding_count": len(findings),
        "findings": findings,
    }


def install_git_hooks(repo_root: Path | None = None) -> dict[str, Any]:
    root = (repo_root or REPO_ROOT).resolve()
    hooks_dir = root / ".git" / "hooks"
    if not hooks_dir.is_dir():
        raise RuntimeError(f"Git hooks directory not found: {hooks_dir}")

    pre_commit = hooks_dir / "pre-commit"
    pre_push = hooks_dir / "pre-push"
    baked_py = Path(sys.executable).resolve().as_posix()
    baked_audit = (REPO_ROOT / "scripts" / "security_audit.py").resolve().as_posix()
    baked_sync = (REPO_ROOT / "dev" / "agents" / "hooks" / "pre_commit_dev_sync.py").resolve().as_posix()

    launcher = (
        "#!/usr/bin/env sh\n"
        "set -e\n"
        'ROOT="$(git rev-parse --show-toplevel)"\n'
        'PY=""\n'
        f'for c in "$SATZ_PYTHON" "$ROOT/.venv/Scripts/python.exe" "$ROOT/.venv/bin/python3" "$ROOT/../sgs/.venv/Scripts/python.exe" "$ROOT/../sgs/.venv/bin/python3" "{baked_py}" "/opt/homebrew/bin/python3" "/usr/local/bin/python3" "/usr/bin/python3"; do\n'
        '  if [ -n "$c" ] && [ -f "$c" ]; then\n'
        '    case "$c" in *WindowsApps*) continue ;; esac\n'
        '    PY="$c"; break\n'
        "  fi\n"
        "done\n"
        'if [ -z "$PY" ]; then\n'
        '  for cmd in python python3; do\n'
        '    cand="$(command -v "$cmd" 2>/dev/null || true)"\n'
        '    case "$cand" in ""|*WindowsApps*) continue ;; esac\n'
        '    PY="$cand"; break\n'
        "  done\n"
        "fi\n"
        'if [ -z "$PY" ]; then echo "[satz-git-hook] Usable Python runtime not found" >&2; exit 1; fi\n'
        f'AUDIT_PY="$ROOT/scripts/security_audit.py"\n'
        f'if [ ! -f "$AUDIT_PY" ]; then AUDIT_PY="{baked_audit}"; fi\n'
        f'SYNC_PY="$ROOT/dev/agents/hooks/pre_commit_dev_sync.py"\n'
        f'if [ ! -f "$SYNC_PY" ]; then SYNC_PY="{baked_sync}"; fi\n'
    )

    pre_commit.write_text(
        launcher
        + 'exec "$PY" "$AUDIT_PY" scan --mode staged\n',
        encoding="utf-8",
    )
    pre_push.write_text(
        launcher
        + '"$PY" "$AUDIT_PY" scan --mode unpushed\n'
        + 'if [ -f "$ROOT/package.json" ] && [ -f "$SYNC_PY" ]; then\n'
        + '  exec "$PY" "$SYNC_PY" --check-only\n'
        + "fi\n",
        encoding="utf-8",
    )

    for hook_path in (pre_commit, pre_push):
        try:
            mode_bits = hook_path.stat().st_mode
            hook_path.chmod(mode_bits | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception:
            pass

    return {
        "ok": True,
        "installed": [pre_commit.relative_to(root).as_posix(), pre_push.relative_to(root).as_posix()],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Satz-Browser Pre-Push Privacy & Security Auditor")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="Scan tracked/staged/unpushed files for secrets, private keys, and PII")
    p_scan.add_argument("--mode", choices=("all", "staged", "unpushed"), default="all")
    p_scan.add_argument("--json", action="store_true")

    p_scrub = sub.add_parser("scrub-text", help="Anonymize secrets, usernames, and personal emails in text or file")
    p_scrub.add_argument("file", nargs="?", help="Optional file path (reads stdin if omitted)")
    p_scrub.add_argument("--in-place", action="store_true")

    sub.add_parser("install-git-hooks", help="Install cross-platform pre-commit and pre-push security hooks")

    args = parser.parse_args()
    if args.cmd == "scan":
        res = run_audit(mode=args.mode)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            if res["ok"]:
                print(f"[security-audit] OK ({res['files_scanned']} files scanned in mode={args.mode}, 0 findings)")
            else:
                print(
                    f"[security-audit] BLOCKED ({res['finding_count']} finding(s) across {res['files_scanned']} files in mode={args.mode}):",
                    file=sys.stderr,
                )
                for f in res["findings"][:25]:
                    print(
                        f"  - [{f['severity']}] {f['category']} at {f['path']}:{f['line']} :: {f['snippet']}",
                        file=sys.stderr,
                    )
        return 0 if res["ok"] else 1

    if args.cmd == "scrub-text":
        if args.file:
            p = Path(args.file)
            cleaned = redact_text(p.read_text(encoding="utf-8", errors="ignore"))
            if args.in_place:
                p.write_text(cleaned, encoding="utf-8")
                print(f"Scrubbed in place: {p}")
            else:
                print(cleaned)
        else:
            print(redact_text(sys.stdin.read()))
        return 0

    if args.cmd == "install-git-hooks":
        print(json.dumps(install_git_hooks(), indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
