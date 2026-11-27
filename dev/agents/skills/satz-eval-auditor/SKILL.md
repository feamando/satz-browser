---
name: satz-eval-auditor
description: >-
  Use this skill to run app regression evals, prompt-injection red-team gates,
  Dev Brain retrieval evals, and to record engineering errors in dev/agents/evals/error_log.jsonl.
---

# Satz Eval & Error Auditor Skill

Registry: [evals/](../../evals/) · App Eval Engine: [satz_evals.py](../../../../sidecar/satz_evals.py)

## Steps
1. Run Dev Brain accuracy evaluation: `python scripts/dev_brain.py eval`
2. Run runtime regression & red-team tests:
   `python -m unittest sidecar.test_evals_and_redteam sidecar.test_local_models sidecar.test_settings_tools sidecar.test_web_harness -v`
3. Append any newly discovered build/runtime regressions or root causes to `dev/agents/evals/error_log.jsonl` using `{ts, id, scope, severity, summary, root_cause, fix_ref}`.
4. Run `python scripts/dev_brain.py reindex` so future searches surface the new postmortem immediately.
