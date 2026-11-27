#!/usr/bin/env python3
"""Atomic semver (`major`/`minor`/`fix`), shipped-model verification, and release helper for Satz-Browser."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
HOOK_DIR = REPO_ROOT / "dev" / "agents" / "hooks"
for _p in (str(SCRIPTS_DIR), str(HOOK_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pre_commit_dev_sync  # noqa: E402
import security_audit  # noqa: E402
from dev_brain import DevBrain  # noqa: E402

PACKAGE_JSON = REPO_ROOT / "package.json"
PACKAGE_LOCK = REPO_ROOT / "package-lock.json"
CARGO_TOML = REPO_ROOT / "src-tauri" / "Cargo.toml"
TAURI_CONF = REPO_ROOT / "src-tauri" / "tauri.conf.json"
CHANGELOG_MD = REPO_ROOT / "dev" / "versions" / "CHANGELOG.md"
PLANCK_DIR = REPO_ROOT / "sidecar" / "models" / "planck"
MAX_SHARD_BYTES = 90 * 1024 * 1024

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
CARGO_VER_RE = re.compile(r'(?m)^version\s*=\s*"([^"]+)"')


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _sha256_parts(parts: list[Path]) -> str:
    h = hashlib.sha256()
    for p in parts:
        with p.open("rb") as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
    return h.hexdigest()


def read_versions() -> dict[str, str]:
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    tauri_cfg = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    cargo_raw = CARGO_TOML.read_text(encoding="utf-8")
    m = CARGO_VER_RE.search(cargo_raw)
    return {
        "package_json": str(pkg.get("version") or ""),
        "cargo_toml": m.group(1).strip() if m else "",
        "tauri_conf": str(tauri_cfg.get("version") or ""),
    }


def compute_next_version(current: str, bump_or_ver: str) -> str:
    m_cur = SEMVER_RE.fullmatch(current.strip())
    if not m_cur:
        raise ValueError(f"Current version is not strict X.Y.Z semver: {current!r}")
    maj, mino, pat = int(m_cur.group(1)), int(m_cur.group(2)), int(m_cur.group(3))
    kind = bump_or_ver.strip().lower()
    if kind in ("fix", "patch"):
        return f"{maj}.{mino}.{pat + 1}"
    if kind == "minor":
        return f"{maj}.{mino + 1}.0"
    if kind == "major":
        return f"{maj + 1}.0.0"
    v_clean = bump_or_ver.strip().lstrip("v")
    if SEMVER_RE.fullmatch(v_clean):
        return v_clean
    raise ValueError(f"Expected major | minor | fix | patch | X.Y.Z, got: {bump_or_ver!r}")


def inspect_planck_manifests(*, verify_hashes: bool = False) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if not PLANCK_DIR.is_dir():
        return results
    for manifest_path in sorted(PLANCK_DIR.glob("*/manifest.json")):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        parts = [manifest_path.parent / str(p) for p in (data.get("parts") or [])]
        missing = [p.name for p in parts if not p.is_file()]
        oversize = [p.name for p in parts if p.is_file() and p.stat().st_size > MAX_SHARD_BYTES]
        total_actual = sum(p.stat().st_size for p in parts if p.is_file())
        hash_ok: bool | None = None
        if verify_hashes and parts and not missing:
            hash_ok = _sha256_parts(parts) == str(data.get("sha256") or "")
        results.append(
            {
                "model": manifest_path.parent.name,
                "manifest": manifest_path.relative_to(REPO_ROOT).as_posix(),
                "model_version": data.get("model_version"),
                "precision": data.get("precision"),
                "parts": len(parts),
                "total_bytes": total_actual,
                "expected_bytes": data.get("total_bytes"),
                "missing_parts": missing,
                "oversize_parts": oversize,
                "sha256_ok": hash_ok,
            }
        )
    return results


def _discover_release_binaries() -> list[dict[str, Any]]:
    rel_root = REPO_ROOT / "src-tauri" / "target" / "release"
    if not rel_root.is_dir():
        return []
    candidates: list[Path] = []
    for name in ("satz-browser.exe", "satz.exe", "satz-browser", "satz"):
        p = rel_root / name
        if p.is_file():
            candidates.append(p)
    bundle_dir = rel_root / "bundle"
    if bundle_dir.is_dir():
        for fp in sorted(bundle_dir.rglob("*")):
            if fp.is_file() and fp.suffix.lower() in (".exe", ".msi", ".dmg", ".sig", ".gz", ".zip"):
                candidates.append(fp)

    items: list[dict[str, Any]] = []
    for fp in candidates:
        st = fp.stat()
        items.append(
            {
                "path": fp.relative_to(REPO_ROOT).as_posix(),
                "bytes": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    return items


def apply_version_bump(
    bump_or_ver: str,
    *,
    notes: str = "",
    model_version: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    versions = read_versions()
    current = pre_commit_dev_sync.check_version_parity()
    target = compute_next_version(current, bump_or_ver)
    models = inspect_planck_manifests(verify_hashes=True)
    for m in models:
        if m["missing_parts"] or m["oversize_parts"] or m["sha256_ok"] is False:
            raise AssertionError(f"Planck model integrity check failed for {m['model']}: {m}")

    if dry_run:
        return {
            "dry_run": True,
            "current": current,
            "target": target,
            "manifests_before": versions,
            "models": models,
        }

    # Update package.json, package-lock.json, tauri.conf.json, and Cargo.toml atomically.
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    pkg["version"] = target
    PACKAGE_JSON.write_text(json.dumps(pkg, indent=2) + "\n", encoding="utf-8")

    if PACKAGE_LOCK.is_file():
        lock = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))
        lock["version"] = target
        packages = lock.get("packages")
        if isinstance(packages, dict) and isinstance(packages.get(""), dict):
            packages[""]["version"] = target
        PACKAGE_LOCK.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")

    tauri_cfg = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    tauri_cfg["version"] = target
    TAURI_CONF.write_text(json.dumps(tauri_cfg, indent=2) + "\n", encoding="utf-8")

    cargo_raw = CARGO_TOML.read_text(encoding="utf-8")
    cargo_new, count = CARGO_VER_RE.subn(f'version = "{target}"', cargo_raw, count=1)
    if count != 1:
        raise RuntimeError("Could not update version field in src-tauri/Cargo.toml")
    CARGO_TOML.write_text(cargo_new, encoding="utf-8")

    if model_version and PLANCK_DIR.is_dir():
        for manifest_path in sorted(PLANCK_DIR.glob("*/manifest.json")):
            mdata = json.loads(manifest_path.read_text(encoding="utf-8"))
            parts = [manifest_path.parent / str(p) for p in (mdata.get("parts") or [])]
            if parts and all(p.is_file() for p in parts):
                mdata["total_bytes"] = sum(p.stat().st_size for p in parts)
                mdata["sha256"] = _sha256_parts(parts)
            mdata["model_version"] = model_version.strip()
            mdata["min_app_version"] = target
            manifest_path.write_text(json.dumps(mdata, indent=2) + "\n", encoding="utf-8")

    if CHANGELOG_MD.is_file():
        existing_cl = CHANGELOG_MD.read_text(encoding="utf-8")
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        note_line = notes.strip() or f"Version bump `{current}` -> `{target}` via `scripts/release_version.py`."
        header = f"## [{target}] - {date_str}\n### Changed\n- {note_line}\n\n"
        anchor = "All notable milestone releases and pipeline changes for `satz-browser`."
        if anchor in existing_cl and f"## [{target}]" not in existing_cl:
            parts_cl = existing_cl.split("\n\n", 2)
            if len(parts_cl) >= 2:
                updated_cl = parts_cl[0] + "\n\n" + parts_cl[1] + "\n\n" + header + (parts_cl[2] if len(parts_cl) > 2 else "")
                CHANGELOG_MD.write_text(updated_cl, encoding="utf-8")

    pre_commit_dev_sync.check_version_parity()
    snap_path = DevBrain(REPO_ROOT).capture_version_snapshot()
    DevBrain(REPO_ROOT).reindex()

    return {
        "ok": True,
        "previous": current,
        "version": target,
        "snapshot": snap_path.relative_to(REPO_ROOT).as_posix(),
        "models": inspect_planck_manifests(verify_hashes=False),
    }


def read_versions_for_root(repo_root: Path | None = None) -> dict[str, str]:
    root = (repo_root or REPO_ROOT).resolve()
    pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
    tauri_cfg = json.loads((root / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    cargo_raw = (root / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    m = CARGO_VER_RE.search(cargo_raw)
    out = {
        "package_json": str(pkg.get("version") or ""),
        "cargo_toml": m.group(1).strip() if m else "",
        "tauri_conf": str(tauri_cfg.get("version") or ""),
    }
    lock_path = root / "package-lock.json"
    if lock_path.is_file():
        lock_cfg = json.loads(lock_path.read_text(encoding="utf-8"))
        out["package_lock"] = str(lock_cfg.get("version") or "")
    return out


def run_ci_preflight(*, tag: str = "", repo_root: Path | None = None) -> dict[str, Any]:
    root = (repo_root or REPO_ROOT).resolve()
    versions = read_versions_for_root(root)
    core = {versions["package_json"], versions["cargo_toml"], versions["tauri_conf"]}
    if "" in core or len(core) != 1:
        raise AssertionError(f"Release manifest version mismatch: {versions}")
    aligned = versions["package_json"]
    if "package_lock" in versions and versions["package_lock"] != aligned:
        raise AssertionError(f"package-lock.json version {versions['package_lock']!r} != {aligned!r}")

    clean_tag = tag.strip()
    if clean_tag:
        stripped = clean_tag[1:] if clean_tag.startswith("v") else clean_tag
        if not SEMVER_RE.fullmatch(stripped) or stripped != aligned:
            raise AssertionError(f"Release tag {clean_tag!r} does not match manifest version {aligned!r}")

    planck_dir = root / "sidecar" / "models" / "planck"
    models: list[dict[str, Any]] = []
    if planck_dir.is_dir():
        for manifest_path in sorted(planck_dir.glob("*/manifest.json")):
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            parts = [manifest_path.parent / str(p) for p in (data.get("parts") or [])]
            missing = [p.name for p in parts if not p.is_file()]
            oversize = [p.name for p in parts if p.is_file() and p.stat().st_size > MAX_SHARD_BYTES]
            hash_ok = _sha256_parts(parts) == str(data.get("sha256") or "") if parts and not missing else False
            if missing or oversize or not hash_ok:
                raise AssertionError(
                    f"Planck shard/hash check failed for {manifest_path.parent.name}: "
                    f"missing={missing}, oversize={oversize}, hash_ok={hash_ok}"
                )
            models.append({"model": manifest_path.parent.name, "parts": len(parts), "sha256_ok": hash_ok})

    audit = security_audit.run_audit(mode="all", repo_root=root)
    if not audit["ok"]:
        raise AssertionError(
            f"Security audit failed ({audit['finding_count']} finding(s)): {audit['findings'][:3]}"
        )

    return {
        "ok": True,
        "version": aligned,
        "tag": clean_tag or f"v{aligned}",
        "manifests": versions,
        "models": models,
        "security_files_scanned": audit["files_scanned"],
    }


def verify_updater_manifest(
    *,
    manifest_path: Path,
    expected_version: str = "",
    require_platforms: tuple[str, ...] = ("windows", "darwin"),
) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise AssertionError(f"Missing updater manifest file: {manifest_path}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError("Updater manifest JSON root must be an object.")

    version = str(data.get("version") or "").strip().lstrip("v")
    if not SEMVER_RE.fullmatch(version):
        raise AssertionError(f"Updater manifest missing valid semver version: {data.get('version')!r}")
    exp = expected_version.strip().lstrip("v")
    if exp and version != exp:
        raise AssertionError(f"Updater manifest version {version!r} != expected {exp!r}")

    platforms = data.get("platforms")
    if not isinstance(platforms, dict) or not platforms:
        raise AssertionError("Updater manifest must contain a non-empty 'platforms' map.")

    for key, entry in platforms.items():
        if not isinstance(entry, dict):
            raise AssertionError(f"Platform entry {key!r} must be an object.")
        url = str(entry.get("url") or "").strip()
        sig = str(entry.get("signature") or "").strip()
        if not url.startswith("https://"):
            raise AssertionError(f"Platform {key!r} missing valid HTTPS download URL: {url!r}")
        if len(sig) < 40:
            raise AssertionError(f"Platform {key!r} missing valid Tauri updater signature.")

    platform_keys = sorted(platforms.keys())
    missing_os = [pref for pref in require_platforms if pref and not any(k.startswith(pref) for k in platform_keys)]
    if missing_os:
        raise AssertionError(
            f"Updater manifest missing required platform(s) {missing_os}; present={platform_keys}"
        )

    return {
        "ok": True,
        "version": version,
        "platforms": platform_keys,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Satz-Browser release version & binary manager")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_stat = sub.add_parser("status", help="Inspect manifest semver parity, model manifests, and local binaries")
    p_stat.add_argument("--verify-hashes", action="store_true")

    p_bump = sub.add_parser("bump", help="Bump major/minor/fix or explicit X.Y.Z across all 3 manifests")
    p_bump.add_argument("target", help="major | minor | fix | patch | X.Y.Z")
    p_bump.add_argument("--notes", default="")
    p_bump.add_argument("--model-version", default=None, help="Optional shipped Planck model version stamp")
    p_bump.add_argument("--dry-run", action="store_true")

    p_pre = sub.add_parser("ci-preflight", help="Validate tag, manifest parity, Planck shards, and security audit")
    p_pre.add_argument("--tag", default="", help="Expected release tag (e.g. v0.5.1)")

    p_upd = sub.add_parser("verify-updater-manifest", help="Validate Tauri latest.json signatures and dual-OS entries")
    p_upd.add_argument("--file", required=True, help="Path to downloaded latest.json")
    p_upd.add_argument("--expected-version", default="", help="Expected X.Y.Z semver")
    p_upd.add_argument("--require-platforms", default="windows,darwin", help="Comma-separated required OS prefixes")

    args = parser.parse_args()
    if args.cmd == "status":
        versions = read_versions()
        try:
            aligned = pre_commit_dev_sync.check_version_parity()
            parity_ok = True
        except AssertionError:
            aligned = None
            parity_ok = False
        print(
            json.dumps(
                {
                    "parity_ok": parity_ok,
                    "aligned_version": aligned,
                    "manifests": versions,
                    "shipped_models": inspect_planck_manifests(verify_hashes=args.verify_hashes),
                    "local_binaries": _discover_release_binaries(),
                },
                indent=2,
            )
        )
        return 0 if parity_ok else 1

    if args.cmd == "bump":
        res = apply_version_bump(
            args.target,
            notes=args.notes,
            model_version=args.model_version,
            dry_run=args.dry_run,
        )
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "ci-preflight":
        try:
            print(json.dumps(run_ci_preflight(tag=args.tag), indent=2))
            return 0
        except AssertionError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
            return 1

    if args.cmd == "verify-updater-manifest":
        req = tuple(p.strip() for p in str(args.require_platforms).split(",") if p.strip())
        try:
            print(
                json.dumps(
                    verify_updater_manifest(
                        manifest_path=Path(args.file),
                        expected_version=args.expected_version,
                        require_platforms=req,
                    ),
                    indent=2,
                )
            )
            return 0
        except AssertionError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
            return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
