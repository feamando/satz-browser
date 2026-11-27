---
name: satz-git-sync
description: >-
  Use this skill whenever syncing branches across Windows/macOS, committing changes,
  pulling/rebasing upstream updates without manual git checkout, or running privacy-gated
  git push workflows for satz-browser.
---

# Satz Automated Git Sync & Push Skill

Sync CLI: [git_sync.py](../../../../scripts/git_sync.py) · Security Auditor: [security_audit.py](../../../../scripts/security_audit.py)

## Rules
1. Never push to GitHub autonomously without explicit user intent; always run `sync --dry-run` first when previewing a push.
2. Never force-push (`git push --force`) over remote work or commit secrets/PII; `scripts/git_sync.py` enforces `security_audit.py` and `.git/hooks/pre-commit` / `.git/hooks/pre-push` automatically.
3. Reindex `dev/brain/` before committing any `dev/` edits so committed SQLite indexes stay synchronized across machines.

## Standard Commands
- **Check branch, ahead/behind drift, and Git hooks:**
  `python scripts/git_sync.py status`
- **Pull & rebase cleanly on Windows or macOS without manual checkout:**
  `python scripts/git_sync.py pull`
- **Preview commit + rebase + push safely (`--dry-run`):**
  `python scripts/git_sync.py sync --push --dry-run`
- **Commit, rebase onto `origin`, pass security/Brain gates, and push:**
  `python scripts/git_sync.py sync -m "<concise message>" --push`
- **Create/switch branch cleanly without manual `git checkout`:**
  `python scripts/git_sync.py sync --branch <branch-name> --push`
