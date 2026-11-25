# Satz Regression Evals (`docs/evals/`)

Sanitized local regression fixtures captured directly from failed assistant turns using the one-click **"Save failure as eval"** button in Chat or `POST /evals/capture`.

## Fixture guarantees
- **Zero PII / secrets**: Personal email addresses (`gmail.com`, Brain `account` entities), Brain `person` names, street addresses, IBANs, phone numbers, booking/tracking codes, local user paths, URL secret parameters (`?token=...`), and API keys are stripped/pseudonymized before writing to disk.
- **Dual-target verification**: Every `eval_*.json` fixture is replayed in isolated temporary runtimes across both **Local Gemma** (`gemma-4-e4b`) and **Cloud** (`gemini` / harness) via `POST /evals/run` or `pytest sidecar/test_evals_and_redteam.py`.
- **Prompt-injection red-team gates**: Auto-built Skills (`Skills/*.md`), mined Skill proposals, and Domain Recipes must pass `run_skill_redteam_gate` / `validate_actor_rule_redteam` against `HOSTILE_PROMPT_INJECTION_CORPUS` before being accepted or executed.
