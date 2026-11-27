---
name: satz-tools-safety-boundary
description: >-
  Use this skill when adding or editing declarative @satz_tool handlers, ToolRegistry,
  Settings/News chat cards, confirm gates, or prompt-injection defenses in sidecar/.
---

# Satz Tools & Read/Act Safety Boundary Skill

Registry: [__init__.py](../../../../sidecar/satz_tools/__init__.py) · Evals: [satz_evals.py](../../../../sidecar/satz_evals.py)

## Security & Architecture Rules
1. **Strict Origin & Read/Act Isolation:** Keep local management tools (`settings_*`, `news_settings`) isolated to dedicated local management conversations (`origin` in `settings`, `news_settings`, `news_perspectives`) and guarded against arbitrary web/email prompt injection.
2. **Single-Use Confirmation Gates:** External mutations (mail send, unsubscribe, provider changes, destructive ops) require explicit user action via single-use `confirm_gate` tokens — never allow page/email text to auto-commit.
3. **RAM-Only Secret Staging:** Secret values staged during Settings flows must be redacted from message history and wiped immediately on `/profile/lock` or profile switches.
4. **Prompt-Injection Red-Team Gate:** Any new tool, actor rule, or skill mining path must pass `HOSTILE_PROMPT_INJECTION_CORPUS` checks in `sidecar/satz_evals.py`.

## Verification
```powershell
..\sgs\.venv\Scripts\python.exe -m unittest sidecar.test_settings_tools sidecar.test_evals_and_redteam sidecar.test_web_harness -v
```
