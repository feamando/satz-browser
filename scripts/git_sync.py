#!/usr/bin/env python3
"""
Automated, privacy-gated Git sync & push manager for Satz-Browser.

Eliminates manual branch checkouts, forgotten security/PII scans, version mismatches,
and stale Dev Brain indexes across Windows & macOS dev machines.

Never silently pushes to a remote during background jobs; executes push only when invoked
explicitly (`sync --push` / `push`), always enforcing `security_audit`, Dev Brain integrity,
and release gates beforehand.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
HOOKS_DIR = REPO_ROOT / "dev" / "agents" / "hooks"
for _p in (str(SCRIPTS_DIR), str(HOOKS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pre_commit_dev_sync  # noqa: E402
import security_audit  # noqa: E402


def _git(args: list[str], *, cwd: Path, check: bool = True, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        err = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {err}")
    return proc


def inspect_git_state(repo_root: Path | None = None) -> dict[str, Any]:
    root = (repo_root or REPO_ROOT).resolve()
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root, check=False).stdout.strip() or "HEAD"
    head_sha = _git(["rev-parse", "--short", "HEAD"], cwd=root, check=False).stdout.strip() or "unborn"
    upstream = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=root, check=False)
    upstream_ref = upstream.stdout.strip() if upstream.returncode == 0 else ""

    ahead, behind = 0, 0
    if upstream_ref:
        lr = _git(["rev-list", "--left-right", "--count", f"HEAD...{upstream_ref}"], cwd=root, check=False)
        if lr.returncode == 0:
            parts = lr.stdout.strip().split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])

    porcelain = [ln for ln in _git(["status", "--porcelain"], cwd=root, check=False).stdout.splitlines() if ln.strip()]
    hooks_installed = {
        "pre_commit": (root / ".git" / "hooks" / "pre-commit").is_file(),
        "pre_push": (root / ".git" / "hooks" / "pre-push").is_file(),
    }
    return {
        "branch": branch,
        "head_sha": head_sha,
        "upstream": upstream_ref or None,
        "ahead": ahead,
        "behind": behind,
        "dirty_count": len(porcelain),
        "dirty_preview": porcelain[:25],
        "hooks_installed": hooks_installed,
    }


def _auto_commit_message(porcelain_lines: list[str], branch: str) -> str:
    areas: list[str] = []
    for raw in porcelain_lines:
        path = raw[3:].strip().split(" -> ")[-1].replace("\\", "/")
        top = path.split("/", 1)[0]
        tag = f"dev/{path.split('/', 2)[1]}" if top == "dev" and "/" in path[4:] else top
        if tag and tag not in areas:
            areas.append(tag)
        if len(areas) >= 4:
            break
    scope = ", ".join(areas) if areas else branch
    return f"chore({scope}): sync {len(porcelain_lines)} update(s)"


def _ensure_branch(root: Path, target_branch: str, *, dry_run: bool) -> str:
    current = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root).stdout.strip()
    if not target_branch or target_branch == current:
        return current
    exists_local = _git(["show-ref", "--verify", f"refs/heads/{target_branch}"], cwd=root, check=False).returncode == 0
    if dry_run:
        return target_branch
    dirty = bool(_git(["status", "--porcelain"], cwd=root).stdout.strip())
    stashed = False
    if dirty:
        _git(["stash", "push", "--include-untracked", "-m", "satz-git-sync-autostash"], cwd=root)
        stashed = True
    try:
        if exists_local:
            _git(["checkout", target_branch], cwd=root)
        else:
            _git(["checkout", "-b", target_branch], cwd=root)
    finally:
        if stashed:
            _git(["stash", "pop"], cwd=root)
    return target_branch


def pull_latest(
    *,
    repo_root: Path | None = None,
    remote: str = "origin",
    branch: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    root = (repo_root or REPO_ROOT).resolve()
    state = inspect_git_state(root)
    target_branch = branch or state["branch"]
    if target_branch == "HEAD":
        raise RuntimeError("Detached HEAD state; specify --branch <name>.")

    actions: list[str] = []
    if not state["hooks_installed"]["pre_commit"] or not state["hooks_installed"]["pre_push"]:
        if dry_run:
            actions.append("install .git/hooks/pre-commit and .git/hooks/pre-push")
        else:
            security_audit.install_git_hooks(root)
            actions.append("installed git hooks")

    if branch and branch != state["branch"]:
        _ensure_branch(root, branch, dry_run=dry_run)
        actions.append(f"switched to branch {branch}")

    has_remote = _git(["remote"], cwd=root, check=False).stdout.strip()
    if remote in has_remote.splitlines():
        if dry_run:
            actions.append(f"git fetch {remote} && git pull --rebase --autostash {remote} {target_branch}")
        else:
            _git(["fetch", remote], cwd=root)
            rem_exists = _git(
                ["show-ref", "--verify", f"refs/remotes/{remote}/{target_branch}"], cwd=root, check=False
            ).returncode == 0
            if rem_exists:
                _git(["pull", "--rebase", "--autostash", remote, target_branch], cwd=root)
                actions.append(f"rebased cleanly onto {remote}/{target_branch}")

    if not dry_run and root == REPO_ROOT.resolve():
        from dev_brain import DevBrain

        DevBrain(root).reindex()
        actions.append("reindexed dev/brain")

    return {"ok": True, "dry_run": dry_run, "branch": target_branch, "actions": actions}


def sync_and_push(
    *,
    repo_root: Path | None = None,
    remote: str = "origin",
    branch: str = "",
    message: str = "",
    push: bool = False,
    tag: str = "",
    bump: str = "",
    release_notes: str = "",
    skip_gate: bool = False,
    full_gate: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = (repo_root or REPO_ROOT).resolve()
    state = inspect_git_state(root)
    target_branch = branch or state["branch"]
    if target_branch == "HEAD":
        raise RuntimeError("Detached HEAD state; pass --branch <name> to checkout/create automatically.")

    steps: list[str] = []
    effective_tag = tag.strip()
    effective_message = message.strip()

    # 1. Ensure Git security hooks exist on this clone
    if not (root / ".git" / "hooks" / "pre-push").is_file() or not (root / ".git" / "hooks" / "pre-commit").is_file():
        if dry_run:
            steps.append("would install .git/hooks/pre-commit and pre-push")
        else:
            security_audit.install_git_hooks(root)
            steps.append("installed .git/hooks/pre-commit and pre-push")

    # 2. Switch/create branch without requiring manual checkout when requested
    if branch and branch != state["branch"]:
        _ensure_branch(root, branch, dry_run=dry_run)
        steps.append(f"active branch -> {branch}")

    # 2b. Optional atomic semver bump before verification & commit
    bumped_version = ""
    if bump.strip():
        if root != REPO_ROOT.resolve():
            raise RuntimeError("--bump only operates on primary workspace repository.")
        import release_version

        bump_res = release_version.apply_version_bump(
            bump.strip(),
            notes=release_notes,
            dry_run=dry_run,
        )
        bumped_version = str(bump_res.get("target" if dry_run else "version") or "")
        steps.append(f"{'would bump' if dry_run else 'bumped'} version -> {bumped_version}")
        if push and not effective_tag and bumped_version:
            effective_tag = f"v{bumped_version}"
        if not effective_message and bumped_version:
            effective_message = f"chore(release): prepare v{bumped_version}"

    # 3. Reindex Dev Brain cleanly before staging if operating on primary repo
    if not dry_run and root == REPO_ROOT.resolve() and not skip_gate:
        from dev_brain import DevBrain

        DevBrain(root).reindex()
        steps.append("reindexed Dev Brain")

    # 4. Run full security/privacy audit + manifest/i18n/weight checks
    audit = security_audit.run_audit(mode="all", repo_root=root)
    if not audit["ok"]:
        preview = "; ".join(f"{f['category']}@{f['path']}:{f['line']}" for f in audit["findings"][:5])
        raise RuntimeError(f"Security/privacy audit blocked sync ({audit['finding_count']} finding(s)): {preview}")
    steps.append(f"security audit passed ({audit['files_scanned']} files)")

    if not skip_gate and root == REPO_ROOT.resolve():
        ver = pre_commit_dev_sync.check_version_parity()
        pre_commit_dev_sync.check_ui_and_weight_limits()
        steps.append(f"version parity ({ver}) & weight/dash checks passed")
        if full_gate:
            gate_res = subprocess.run(
                [sys.executable, str(HOOKS_DIR / "release_gate.py")],
                cwd=str(root),
                capture_output=True,
                text=True,
            )
            if gate_res.returncode != 0:
                raise RuntimeError(f"release_gate.py failed: {(gate_res.stderr or gate_res.stdout)[-400:]}")
            steps.append("full release_gate.py passed")

    # 5. Stage & commit dirty workspace changes cleanly
    porcelain = [ln for ln in _git(["status", "--porcelain"], cwd=root).stdout.splitlines() if ln.strip()]
    commit_msg = effective_message or _auto_commit_message(porcelain, target_branch)
    committed = False
    if porcelain:
        if dry_run:
            steps.append(f"would stage {len(porcelain)} path(s) and commit: {commit_msg!r}")
        else:
            _git(["add", "-A"], cwd=root)
            staged_audit = security_audit.run_audit(mode="staged", repo_root=root)
            if not staged_audit["ok"]:
                raise RuntimeError(f"Staged security audit blocked commit: {staged_audit['findings'][:3]}")
            _git(["commit", "-m", commit_msg], cwd=root)
            committed = True
            steps.append(f"committed: {commit_msg}")

    # 6. Fetch + rebase cleanly onto remote branch if present
    remotes = _git(["remote"], cwd=root, check=False).stdout.splitlines()
    if remote in remotes:
        if dry_run:
            steps.append(f"would fetch & rebase onto {remote}/{target_branch}")
        else:
            _git(["fetch", remote], cwd=root)
            rem_exists = _git(
                ["show-ref", "--verify", f"refs/remotes/{remote}/{target_branch}"], cwd=root, check=False
            ).returncode == 0
            if rem_exists:
                _git(["rebase", "--autostash", f"{remote}/{target_branch}"], cwd=root)
                steps.append(f"rebased cleanly onto {remote}/{target_branch}")

    # 7. Push commits (and optional verified release tag) when requested
    pushed = False
    if push:
        unpushed_audit = security_audit.run_audit(mode="unpushed", repo_root=root)
        if not unpushed_audit["ok"]:
            raise RuntimeError(f"Unpushed security audit blocked push: {unpushed_audit['findings'][:3]}")
        if effective_tag:
            if root == REPO_ROOT.resolve() and not dry_run:
                expected_ver = pre_commit_dev_sync.check_version_parity()
                if effective_tag.lstrip("v") != expected_ver:
                    raise RuntimeError(
                        f"Tag {effective_tag!r} does not match manifest version {expected_ver!r}"
                    )
            if dry_run:
                steps.append(f"would tag {effective_tag} and git push -u {remote} {target_branch} --tags")
            else:
                _git(["tag", "-a", effective_tag, "-m", f"Release {effective_tag}"], cwd=root)
                _git(["push", "-u", remote, target_branch, "--tags"], cwd=root)
                pushed = True
                steps.append(f"pushed {remote}/{target_branch} + tag {effective_tag}")
        else:
            if dry_run:
                steps.append(f"would git push -u {remote} {target_branch}")
            else:
                _git(["push", "-u", remote, target_branch], cwd=root)
                pushed = True
                steps.append(f"pushed {remote}/{target_branch}")

    return {
        "ok": True,
        "dry_run": dry_run,
        "branch": target_branch,
        "bumped_version": bumped_version or None,
        "tag": effective_tag or None,
        "committed": committed,
        "pushed": pushed,
        "commit_message": commit_msg if (porcelain or committed) else None,
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Automated privacy-gated Git sync and push manager")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_stat = sub.add_parser("status", help="Inspect branch, upstream drift, dirty count, and git hooks")
    p_stat.add_argument("--json", action="store_true")

    p_pull = sub.add_parser("pull", help="Fetch, autostash-rebase onto remote, install hooks, and reindex Dev Brain")
    p_pull.add_argument("--remote", default="origin")
    p_pull.add_argument("--branch", default="")
    p_pull.add_argument("--dry-run", action="store_true")

    p_sync = sub.add_parser("sync", help="Run security audit + gates + commit + rebase + optional push")
    p_sync.add_argument("--remote", default="origin")
    p_sync.add_argument("--branch", default="", help="Switch to or create branch safely without manual checkout")
    p_sync.add_argument("-m", "--message", default="", help="Commit message (auto-generated if omitted)")
    p_sync.add_argument("--push", action="store_true", help="Push branch after commit/rebase & pre-push security checks")
    p_sync.add_argument("--tag", default="", help="Optional verified release tag vX.Y.Z to push")
    p_sync.add_argument("--bump", default="", help="Optional atomic version bump (major|minor|fix|patch|X.Y.Z); auto-tags on --push")
    p_sync.add_argument("--release-notes", default="", help="Changelog note when --bump is used")
    p_sync.add_argument("--skip-gate", action="store_true", help="Skip repo-specific manifest/Brain reindex (for isolated tests)")
    p_sync.add_argument("--full-gate", action="store_true", help="Run full release_gate.py before commit/push")
    p_sync.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.cmd == "status":
        print(json.dumps(inspect_git_state(), indent=2))
        return 0
    if args.cmd == "pull":
        print(json.dumps(pull_latest(remote=args.remote, branch=args.branch, dry_run=args.dry_run), indent=2))
        return 0
    if args.cmd == "sync":
        print(
            json.dumps(
                sync_and_push(
                    remote=args.remote,
                    branch=args.branch,
                    message=args.message,
                    push=args.push,
                    tag=args.tag,
                    bump=args.bump,
                    release_notes=args.release_notes,
                    skip_gate=args.skip_gate,
                    full_gate=args.full_gate,
                    dry_run=args.dry_run,
                ),
                indent=2,
            )
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
