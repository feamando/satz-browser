# Tasks: `v0.5p-action-providers`

- **Plan:** [v1.md](v1.md)
- **Status:** Complete (Historical Baseline)

## Checklist
- [x] Implement `sidecar/satz_providers.py` & `satz_passwords.py` credential masking/aliases
- [x] Wire `get_default_providers`, `propose_set_default_provider`, and vertical API failover in `sidecar/satz_web_harness.py`
- [x] Add `BehaviorMiner.mine_provider_suggestions` in `sidecar/satz_skills.py`
- [x] Build Settings UI registry controls (`src/knowledge.ts`, `src/api.ts`, `src/types.ts`, `src/main.ts`)
- [x] Verify `sidecar/test_providers.py` and full regression suite
