#!/usr/bin/env python3
"""Tests for Satz Dev Hub, Brain Index Graph DB, Lifecycle Hooks, Behavior->Skill, Error->Eval & Release CLI."""
from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
HOOKS_DIR = REPO_ROOT / "dev" / "agents" / "hooks"
for p in (str(REPO_ROOT / "sidecar"), str(SCRIPTS_DIR), str(HOOKS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import agent_background_worker  # noqa: E402
import dev_brain  # noqa: E402
import git_sync  # noqa: E402
import release_version  # noqa: E402
import security_audit  # noqa: E402
from dev_brain import DevBrain  # noqa: E402
from pre_commit_dev_sync import check_ui_and_weight_limits, check_version_parity  # noqa: E402
import behavior_eval_store  # noqa: E402
import hook_common  # noqa: E402
import post_edit_brain_sync  # noqa: E402
import pre_invocation_context  # noqa: E402
import pre_tool_guard  # noqa: E402
import session_start_context  # noqa: E402
import stop_gate_check  # noqa: E402


class TestDevPipelineAndBrain(unittest.TestCase):
    def setUp(self) -> None:
        self.brain = DevBrain(REPO_ROOT)

    def test_required_dev_folder_hierarchy_exists(self) -> None:
        expected_dirs = [
            "dev",
            "dev/docs",
            "dev/versions",
            "dev/versions/snapshots",
            "dev/analytics",
            "dev/agents",
            "dev/agents/hooks",
            "dev/agents/skills",
            "dev/agents/behavior",
            "dev/agents/roles",
            "dev/agents/evals",
            "dev/plans",
            "dev/brain",
            ".agents",
            ".claude",
        ]
        for rel in expected_dirs:
            self.assertTrue((REPO_ROOT / rel).is_dir(), f"Missing directory: {rel}")

        plan_subdirs = [d for d in (REPO_ROOT / "dev" / "plans").iterdir() if d.is_dir()]
        self.assertGreaterEqual(len(plan_subdirs), 12)
        for pdir in plan_subdirs:
            self.assertTrue((pdir / "v1.md").is_file(), f"Missing v1.md in {pdir}")
            self.assertTrue((pdir / "tasks.md").is_file(), f"Missing tasks.md in {pdir}")

        expected_skills = (
            "satz-release-manager",
            "satz-dev-brain",
            "satz-eval-auditor",
            "satz-ui-design-i18n",
            "satz-cross-platform-shell",
            "satz-sidecar-models-boundary",
            "satz-tools-safety-boundary",
            "satz-feature-planner",
            "satz-git-sync",
        )
        for skill_name in expected_skills:
            self.assertTrue(
                (REPO_ROOT / "dev" / "agents" / "skills" / skill_name / "SKILL.md").is_file(),
                f"Missing skill: {skill_name}",
            )

    def test_dev_brain_monitor_integrity_and_readonly_queries(self) -> None:
        mon = self.brain.monitor()
        self.assertTrue(mon["ok"], f"DevBrain monitor failed: {mon}")
        self.assertEqual(mon["stale_count"], 0)
        self.assertEqual(mon["broken_edge_count"], 0)
        self.assertEqual(mon["nodes"], mon["fts_nodes"])
        self.assertEqual(mon["nodes"], mon["embeddings"])
        self.assertGreater(mon["edges"], 20)
        self.assertTrue(mon["registry_and_brain_md_ok"])

        self.assertFalse(Path(str(self.brain.db_path) + "-wal").exists())
        self.assertFalse(Path(str(self.brain.db_path) + "-shm").exists())
        conn = sqlite3.connect(str(self.brain.db_path))
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertNotEqual(str(mode).lower(), "wal")
        finally:
            conn.close()

        before_hash = hashlib.sha256(self.brain.db_path.read_bytes()).hexdigest()
        hits = self.brain.search("unsigned macOS xattr release", include_neighbors=True)
        self.assertGreater(len(hits), 0)
        self.assertIn(
            hits[0]["path"],
            ("dev/docs/RELEASE_RUNBOOK.md", "dev/agents/skills/satz-release-manager/SKILL.md"),
        )
        node = self.brain.get_node("dev/docs/RELEASE_RUNBOOK.md", depth=2)
        self.assertIsNotNone(node)
        self.assertGreater(len(node["neighbors"]), 0)
        after_hash = hashlib.sha256(self.brain.db_path.read_bytes()).hexdigest()
        self.assertEqual(before_hash, after_hash)

    def test_dev_brain_retrieval_eval_accuracy(self) -> None:
        ev = self.brain.evaluate(min_mrr=0.80, min_recall5=0.90, record=False)
        self.assertTrue(ev["passed"], f"DevBrain eval below threshold: {ev}")
        self.assertGreaterEqual(ev["mrr"], 0.80)
        self.assertGreaterEqual(ev["recall_at_5"], 0.90)
        self.assertGreaterEqual(ev["term_accuracy"], 0.90)

    def test_hooks_version_parity_and_post_edit_skip_outside_dev(self) -> None:
        ver = check_version_parity()
        self.assertTrue(bool(ver))
        check_ui_and_weight_limits()

        with tempfile.TemporaryDirectory() as tmpd:
            env_patch = {
                "SATZ_BEHAVIOR_DB_PATH": str(Path(tmpd) / "raw.sqlite"),
                "SATZ_ERROR_LOG_PATH": str(Path(tmpd) / "err.jsonl"),
                "SATZ_DISABLE_BG_WORKER": "1",
            }
            with mock.patch.dict(os.environ, env_patch):
                fake_stdin = io.StringIO(json.dumps({"toolInput": {"Path": "src/main.ts"}}))
                fake_stdout = io.StringIO()
                with mock.patch("sys.stdin", fake_stdin), mock.patch("sys.stdout", fake_stdout):
                    rc = post_edit_brain_sync.main()
                self.assertEqual(rc, 0)
                self.assertEqual(json.loads(fake_stdout.getvalue()), {})

    def test_hook_configs_are_valid_json_and_wire_all_events(self) -> None:
        ag = json.loads((REPO_ROOT / ".agents" / "hooks.json").read_text(encoding="utf-8"))
        spec = ag["satz-agent-lifecycle"]
        self.assertIsInstance(spec["SessionStart"], list)
        self.assertIsInstance(spec["PreInvocation"], list)
        self.assertIsInstance(spec["Stop"], list)
        self.assertIn("matcher", spec["PreToolUse"][0])
        self.assertIn("run_command", spec["PostToolUse"][0]["matcher"])

        cc = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
        cc_hooks = cc["hooks"]
        for evt in ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"):
            self.assertIn(evt, cc_hooks)
            self.assertIn("matcher", cc_hooks[evt][0])
            self.assertIn("hooks", cc_hooks[evt][0])

    def test_hook_runner_executes_cleanly_from_agents_cwd(self) -> None:
        env = dict(os.environ)
        env["SATZ_PYTHON"] = sys.executable
        res = subprocess.run(
            ["node", "../dev/agents/hooks/hook_runner.mjs", "session_start_context"],
            cwd=str(REPO_ROOT / ".agents"),
            input=json.dumps({"hookEventName": "SessionStart", "conversationId": "ut-1"}),
            text=True,
            capture_output=True,
            timeout=15,
            env=env,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        msg = data["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("dev/agents/INSTRUCTIONS.md", msg)
        self.assertIn("satz-release-manager", msg)
        self.assertIn("satz-ui-design-i18n", msg)
        self.assertNotIn("_template", msg)

    def test_hook_runner_pre_tool_guard_fail_open_and_host_formats(self) -> None:
        env = dict(os.environ)
        env["SATZ_PYTHON"] = sys.executable

        # Normal pre_tool_guard dispatch across Antigravity and Claude Code payloads
        ag_res = subprocess.run(
            ["node", "../dev/agents/hooks/hook_runner.mjs", "pre_tool_guard"],
            cwd=str(REPO_ROOT / ".agents"),
            input=json.dumps({
                "hookEventName": "PreToolUse",
                "toolCall": {"name": "run_command", "args": {"CommandLine": "git status"}},
            }),
            text=True,
            capture_output=True,
            timeout=15,
            env=env,
        )
        self.assertEqual(ag_res.returncode, 0, ag_res.stderr)
        self.assertEqual(json.loads(ag_res.stdout), {"decision": "ask"})

        cc_res = subprocess.run(
            ["node", "../dev/agents/hooks/hook_runner.mjs", "pre_tool_guard"],
            cwd=str(REPO_ROOT / ".agents"),
            input=json.dumps({
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "git status"},
            }),
            text=True,
            capture_output=True,
            timeout=15,
            env=env,
        )
        self.assertEqual(cc_res.returncode, 0, cc_res.stderr)
        self.assertEqual(json.loads(cc_res.stdout), {})

        # Fail-open path (isolated runner missing pre_tool_guard.py) must emit ask for Antigravity, {} for Claude Code
        with tempfile.TemporaryDirectory() as tmpd:
            isolated_runner = Path(tmpd) / "hook_runner.mjs"
            isolated_runner.write_text(
                (HOOKS_DIR / "hook_runner.mjs").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            ag_failopen = subprocess.run(
                ["node", str(isolated_runner), "pre_tool_guard"],
                cwd=tmpd,
                input=json.dumps({
                    "hookEventName": "PreToolUse",
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "echo hi"}},
                }),
                text=True,
                capture_output=True,
                timeout=15,
                env=env,
            )
            self.assertEqual(ag_failopen.returncode, 0, ag_failopen.stderr)
            self.assertEqual(json.loads(ag_failopen.stdout), {"decision": "ask"})

            cc_failopen = subprocess.run(
                ["node", str(isolated_runner), "pre_tool_guard"],
                cwd=tmpd,
                input=json.dumps({
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "echo hi"},
                }),
                text=True,
                capture_output=True,
                timeout=15,
                env=env,
            )
            self.assertEqual(cc_failopen.returncode, 0, cc_failopen.stderr)
            self.assertEqual(json.loads(cc_failopen.stdout), {})

    def test_session_start_and_pre_invocation_contracts_skill_boost_and_dedupe(self) -> None:
        before_hash = hashlib.sha256(self.brain.db_path.read_bytes()).hexdigest()

        out_cc = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps({"hook_event_name": "SessionStart", "session_id": "cc-1"}))), \
             mock.patch("sys.stdout", out_cc):
            session_start_context.main()
        parsed_cc = json.loads(out_cc.getvalue())
        self.assertEqual(parsed_cc["hookSpecificOutput"]["hookEventName"], "SessionStart")
        ctx = parsed_cc["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Mandatory guardrails:", ctx)
        self.assertIn("Available repo skills", ctx)
        self.assertIn("satz-sidecar-models-boundary", ctx)

        with tempfile.TemporaryDirectory() as tmpd:
            cache_file = str(Path(tmpd) / "cache.json")
            raw_db = str(Path(tmpd) / "raw.sqlite")
            env_patch = {
                "SATZ_HOOK_CACHE_PATH": cache_file,
                "SATZ_BEHAVIOR_DB_PATH": raw_db,
                "SATZ_DISABLE_BG_WORKER": "1",
            }
            with mock.patch.dict(os.environ, env_patch):
                out1 = io.StringIO()
                payload1 = {
                    "hookEventName": "PreInvocation",
                    "conversationId": "conv-ut",
                    "invocationNum": 1,
                    "lastUserInput": "release packaging major minor fix version and macos updater signature",
                }
                with mock.patch("sys.stdin", io.StringIO(json.dumps(payload1))), mock.patch("sys.stdout", out1):
                    pre_invocation_context.main()
                d1 = json.loads(out1.getvalue())
                injected = d1["injectSteps"][0]["systemMessage"]["systemMessage"]
                self.assertIn("[Recommended Skills]", injected)
                self.assertIn("satz-release-manager/SKILL.md", injected)
                self.assertIn("[DevBrain Relevant Context]", injected)
                self.assertGreaterEqual(behavior_eval_store.count_unanalyzed(Path(raw_db)), 1)

                out_dup = io.StringIO()
                with mock.patch("sys.stdin", io.StringIO(json.dumps(payload1))), mock.patch("sys.stdout", out_dup):
                    pre_invocation_context.main()
                self.assertEqual(json.loads(out_dup.getvalue()), {})

                out_loop = io.StringIO()
                payload2 = {**payload1, "invocationNum": 2}
                with mock.patch("sys.stdin", io.StringIO(json.dumps(payload2))), mock.patch("sys.stdout", out_loop):
                    pre_invocation_context.main()
                self.assertEqual(json.loads(out_loop.getvalue()), {})

        after_hash = hashlib.sha256(self.brain.db_path.read_bytes()).hexdigest()
        self.assertEqual(before_hash, after_hash)

    def test_pre_tool_guard_policies_antigravity_and_claude(self) -> None:
        with tempfile.TemporaryDirectory() as tmpd:
            temp_log = Path(tmpd) / "behavior.jsonl"
            env_patch = {
                "SATZ_BEHAVIOR_DB_PATH": str(Path(tmpd) / "raw.sqlite"),
                "SATZ_DISABLE_BG_WORKER": "1",
            }
            with mock.patch.object(hook_common, "BEHAVIOR_LOG", temp_log), mock.patch.dict(os.environ, env_patch):
                r1 = pre_tool_guard.evaluate_tool_call({
                    "hookEventName": "PreToolUse",
                    "toolCall": {"name": "edit_file", "args": {"Path": "../sgs/README.md", "Replacement": "x"}},
                })
                self.assertIsNotNone(r1)
                self.assertIn("read-only", r1)

                r2 = pre_tool_guard.evaluate_tool_call({
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "src/i18n/catalog.ts", "new_string": "Hello \u2014 world"},
                })
                self.assertIsNotNone(r2)
                self.assertIn("em/en dash", r2)

                r3 = pre_tool_guard.evaluate_tool_call({
                    "hookEventName": "PreToolUse",
                    "toolCall": {"name": "edit_file", "args": {"Path": "src/design-system/components.css", "Replacement": "color: #ff00aa;"}},
                })
                self.assertIsNotNone(r3)
                self.assertIn("hex color", r3)

                ok_tokens = pre_tool_guard.evaluate_tool_call({
                    "hookEventName": "PreToolUse",
                    "toolCall": {"name": "edit_file", "args": {"Path": "src/design-system/tokens.css", "Replacement": "--accent: #ff00aa;"}},
                })
                self.assertIsNone(ok_tokens)

                r4 = pre_tool_guard.evaluate_tool_call({
                    "hookEventName": "PreToolUse",
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "git tag -a v9.9.9 -m rel"}},
                })
                self.assertIsNotNone(r4)
                self.assertIn("Blocked git tag v9.9.9", r4)

                # Antigravity permitted tool call returns decision='ask'; Claude Code returns {}
                out_ag = io.StringIO()
                with mock.patch("sys.stdin", io.StringIO(json.dumps({
                    "hookEventName": "PreToolUse",
                    "toolCall": {"name": "edit_file", "args": {"Path": "src/main.ts", "Replacement": "const x = 1;"}},
                }))), mock.patch("sys.stdout", out_ag):
                    pre_tool_guard.main()
                self.assertEqual(json.loads(out_ag.getvalue()), {"decision": "ask"})

                out_cc = io.StringIO()
                with mock.patch("sys.stdin", io.StringIO(json.dumps({
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "src/main.ts", "new_string": "const x = 1;"},
                }))), mock.patch("sys.stdout", out_cc):
                    pre_tool_guard.main()
                self.assertEqual(json.loads(out_cc.getvalue()), {})

    def test_post_edit_brain_sync_handles_dev_edits_and_tool_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpd:
            env_patch = {
                "SATZ_BEHAVIOR_DB_PATH": str(Path(tmpd) / "raw.sqlite"),
                "SATZ_ERROR_LOG_PATH": str(Path(tmpd) / "err.jsonl"),
                "SATZ_DISABLE_BG_WORKER": "1",
            }
            with mock.patch.dict(os.environ, env_patch), mock.patch.object(post_edit_brain_sync, "append_behavior_log") as log_mock:
                with mock.patch("dev_brain.DevBrain.reindex", return_value={"nodes": 80, "edges": 140}) as reidx_mock:
                    res = post_edit_brain_sync.handle_post_tool({
                        "hookEventName": "PostToolUse",
                        "toolCall": {"name": "replace_file_content", "args": {"TargetFile": "dev/agents/INSTRUCTIONS.md"}},
                    })
                    self.assertEqual(res["action"], "reindexed")
                    self.assertEqual(reidx_mock.call_count, 1)
                    self.assertEqual(log_mock.call_count, 1)

                # Tool execution failure captures deduplicated error incident without reindexing dev/
                post_edit_brain_sync.handle_post_tool({
                    "hookEventName": "PostToolUse",
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "cargo test"}},
                    "error": "exit status 101: unresolved import",
                })
                err_lines = Path(tmpd, "err.jsonl").read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(err_lines), 1)
                self.assertIn("cargo test", err_lines[0])
                self.assertIn("unresolved import", err_lines[0])

    def test_stop_gate_check_loop_guard_and_broken_link_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmpd:
            env_patch = {
                "SATZ_BEHAVIOR_DB_PATH": str(Path(tmpd) / "raw.sqlite"),
                "SATZ_ERROR_LOG_PATH": str(Path(tmpd) / "err.jsonl"),
                "SATZ_DISABLE_BG_WORKER": "1",
            }
            with mock.patch.dict(os.environ, env_patch):
                self.assertIsNone(stop_gate_check.evaluate_stop({"continuationActive": True, "terminationReason": "NO_TOOL_CALL"}))
                self.assertIsNone(stop_gate_check.evaluate_stop({"stop_hook_active": True}))
                self.assertIsNone(stop_gate_check.evaluate_stop({"continuationActive": False, "terminationReason": "USER_CANCELED"}))

                fake_mon = {
                    "stale_count": 0,
                    "broken_edge_count": 1,
                    "broken_links": [{"source": "dev/a.md", "target": "missing.md"}],
                }
                with mock.patch("dev_brain.DevBrain.monitor", return_value=fake_mon), \
                     mock.patch.object(stop_gate_check, "_git_dirty_paths", return_value=[]):
                    out = io.StringIO()
                    with mock.patch("sys.stdin", io.StringIO(json.dumps({"continuationActive": False, "terminationReason": "NO_TOOL_CALL"}))), \
                         mock.patch("sys.stdout", out), \
                         mock.patch.object(stop_gate_check, "append_behavior_log"):
                        stop_gate_check.main()
                    parsed = json.loads(out.getvalue())
                    self.assertEqual(parsed["decision"], "continue")
                    self.assertIn("missing.md", parsed["reason"])

    def test_background_worker_clusters_prompts_synthesizes_skill_and_auto_eval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpd:
            tmp_root = Path(tmpd)
            (tmp_root / "dev" / "agents" / "skills").mkdir(parents=True)
            (tmp_root / "dev" / "agents" / "evals").mkdir(parents=True)
            raw_db = tmp_root / "dev" / "agents" / "behavior" / "raw_events.sqlite"

            for i in range(3):
                behavior_eval_store.record_event(
                    harness="antigravity",
                    conv_id=f"c-{i}",
                    event_type="prompt",
                    prompt_text="Always verify release manifest version parity and build signed windows bundle",
                    db_path=raw_db,
                )
                behavior_eval_store.record_event(
                    harness="antigravity",
                    conv_id=f"c-{i}",
                    event_type="tool_use",
                    tool_name="edit_file",
                    rel_paths=["src-tauri/tauri.conf.json"],
                    db_path=raw_db,
                )
            behavior_eval_store.record_event(
                harness="antigravity",
                conv_id="c-err",
                event_type="pre_tool_deny",
                tool_name="edit_file",
                ok=False,
                error_text="Blocked em/en dash in src/i18n/catalog.ts",
                db_path=raw_db,
            )

            with mock.patch.object(agent_background_worker, "append_behavior_log"), \
                 mock.patch.object(dev_brain.DevBrain, "monitor", return_value={"broken_edge_count": 0}):
                summary = agent_background_worker.run_cycle(
                    repo_root=tmp_root,
                    db_path=raw_db,
                    min_cluster=3,
                )
            self.assertEqual(summary["clusters_found"], 1)
            self.assertEqual(len(summary["skills_written"]), 1)
            slug = summary["skills_written"][0]
            prop_md = tmp_root / "dev" / "agents" / "behavior" / "proposals" / slug / "SKILL.md"
            self.assertTrue(prop_md.is_file())
            self.assertTrue((tmp_root / "dev" / "agents" / "evals" / "auto_eval_cases.yaml").is_file())
            self.assertTrue((tmp_root / "dev" / "agents" / "evals" / "eval_history.jsonl").is_file())

            with mock.patch.object(agent_background_worker, "append_behavior_log"):
                approved = agent_background_worker.approve_proposal(slug, repo_root=tmp_root)
            self.assertTrue(approved["ok"])
            self.assertTrue((tmp_root / "dev" / "agents" / "skills" / slug / "SKILL.md").is_file())
            self.assertFalse(prop_md.exists())

    def test_release_version_cli_and_planck_manifests(self) -> None:
        self.assertEqual(release_version.compute_next_version("0.5.0", "fix"), "0.5.1")
        self.assertEqual(release_version.compute_next_version("0.5.1", "minor"), "0.6.0")
        self.assertEqual(release_version.compute_next_version("0.6.2", "major"), "1.0.0")
        models = release_version.inspect_planck_manifests(verify_hashes=False)
        self.assertGreaterEqual(len(models), 2)
        for m in models:
            self.assertEqual(m["missing_parts"], [])
            self.assertEqual(m["oversize_parts"], [])

    def test_security_audit_repo_clean_scrubbing_and_pre_push_block(self) -> None:
        res = security_audit.run_audit(mode="all", repo_root=REPO_ROOT)
        self.assertTrue(res["ok"], f"Security audit reported findings: {res['findings'][:5]}")

        # Verify detection of secrets, private keys, personal emails, and IBANs (constructed at runtime)
        tok_prefix = "sk-" + "proj-"
        priv_hdr = "-----BEGIN OPENSSH " + "PRIVATE KEY-----"
        dirty_sample = (
            f"OPENAI={tok_prefix}RealLeakKey9876543210abcdef\n"
            "email=someone@gmail.com\n"
            "iban=DE89370400440532013000\n"
            f"key={priv_hdr}\n"
        )
        findings = security_audit.scan_text_content("dev/docs/sample.md", dirty_sample)
        cats = {f["category"] for f in findings}
        self.assertIn("api_or_auth_token", cats)
        self.assertIn("unanonymized_email", cats)
        self.assertIn("iban_pii", cats)
        self.assertIn("private_key_or_secret", cats)

        scrubbed = security_audit.redact_text(dirty_sample)
        self.assertEqual(security_audit.scan_text_content("dev/docs/sample.md", scrubbed), [])

        # Behavior/error stores also scrub sensitive values before writing
        with tempfile.TemporaryDirectory() as tmpd:
            err_log = Path(tmpd) / "err.jsonl"
            behavior_eval_store.record_error_incident(
                scope="tool:test",
                summary=dirty_sample,
                root_cause="simulated test",
                error_log_path=err_log,
            )
            saved = err_log.read_text(encoding="utf-8")
            self.assertEqual(security_audit.scan_text_content("dev/agents/evals/error_log.jsonl", saved), [])

        # PreToolUse blocks git push whenever security audit reports unpushed leaks
        fake_fail = {"ok": False, "finding_count": 1, "findings": [{"category": "api_or_auth_token", "path": "x.py", "line": 2}]}
        with mock.patch.object(pre_tool_guard.security_audit, "run_audit", return_value=fake_fail):
            deny_reason = pre_tool_guard.evaluate_tool_call({
                "hookEventName": "PreToolUse",
                "toolCall": {"name": "run_command", "args": {"CommandLine": "git push origin main"}},
            })
            self.assertIsNotNone(deny_reason)
            self.assertIn("Blocked git push", deny_reason)

        # PreToolUse blocks direct file writes containing secret tokens in tracked files
        sample_tok = "AIza" + "SyActualSecretToken9876543210abcd"
        deny_write = pre_tool_guard.evaluate_tool_call({
            "hookEventName": "PreToolUse",
            "toolCall": {
                "name": "edit_file",
                "args": {"Path": "src/main.ts", "Replacement": f"const k = '{sample_tok}';"},
            },
        })
        self.assertIsNotNone(deny_write)
        self.assertIn("Blocked security/privacy leak", deny_write)

    def test_git_sync_workflow_and_pre_push_security_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmpd:
            tmp = Path(tmpd)
            remote_bare = tmp / "remote.git"
            work = tmp / "work"
            subprocess.run(["git", "init", "--bare", str(remote_bare)], check=True, capture_output=True)
            subprocess.run(["git", "clone", str(remote_bare), str(work)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(work), "config", "user.name", "Satz Test"], check=True)
            subprocess.run(["git", "-C", str(work), "config", "user.email", "tester@example.test"], check=True)
            (work / "README.md").write_text("# Init\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(work), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(work), "commit", "-m", "init"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(work), "push", "-u", "origin", "HEAD:main"], check=True, capture_output=True)

            # Auto branch switch/create + commit + push without manual git checkout
            (work / "notes.md").write_text("clean dev change\n", encoding="utf-8")
            res = git_sync.sync_and_push(
                repo_root=work,
                branch="feature/auto-sync",
                push=True,
                skip_gate=True,
            )
            self.assertTrue(res["ok"])
            self.assertTrue(res["committed"])
            self.assertTrue(res["pushed"])
            cur_branch = subprocess.run(
                ["git", "-C", str(work), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            self.assertEqual(cur_branch, "feature/auto-sync")

            # Introducing an unredacted token must block git_sync push
            bad_secret = "sk-" + "proj-LeakedSecretToken1234567890"
            (work / "leak.txt").write_text(f"TOKEN={bad_secret}\n", encoding="utf-8")
            with self.assertRaises(RuntimeError) as ctx:
                git_sync.sync_and_push(repo_root=work, push=True, skip_gate=True)
            self.assertIn("Security/privacy audit blocked", str(ctx.exception))

    def test_release_workflow_ci_preflight_updater_manifest_and_dry_run_bump(self) -> None:
        import yaml

        aligned = check_version_parity()
        pref = release_version.run_ci_preflight(tag=f"v{aligned}")
        self.assertTrue(pref["ok"])
        self.assertEqual(pref["version"], aligned)
        with self.assertRaises(AssertionError):
            release_version.run_ci_preflight(tag="v99.99.99")

        # Validate workflows YAML contracts for automated dual-OS CI and non-prerelease updater feed
        ci_wf = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
        self.assertEqual(ci_wf["jobs"]["verify"]["strategy"]["matrix"]["os"], ["windows-latest", "macos-latest"])

        rel_wf = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"))
        self.assertIn("prepare-release", rel_wf["jobs"])
        self.assertIn("build-tauri", rel_wf["jobs"])
        self.assertIn("publish-release", rel_wf["jobs"])
        on_cfg = rel_wf.get("on") or rel_wf.get(True)
        dispatch_pre = on_cfg["workflow_dispatch"]["inputs"]["prerelease"]["default"]
        self.assertFalse(dispatch_pre)
        build_step = rel_wf["jobs"]["build-tauri"]["steps"][-1]
        self.assertFalse(build_step["with"]["prerelease"])
        self.assertIn("release_id", str(build_step["with"]["releaseId"]))

        # Verify updater manifest validation rejects single-OS or broken sigs, accepts dual-OS
        with tempfile.TemporaryDirectory() as tmpd:
            manifest = Path(tmpd) / "latest.json"
            valid_sig = "A" * 64
            manifest.write_text(json.dumps({
                "version": aligned,
                "platforms": {
                    "windows-x86_64": {"url": f"https://github.com/feamando/satz-browser/releases/download/v{aligned}/satz.exe", "signature": valid_sig},
                    "darwin-aarch64": {"url": f"https://github.com/feamando/satz-browser/releases/download/v{aligned}/satz.app.tar.gz", "signature": valid_sig},
                },
            }), encoding="utf-8")
            ok_res = release_version.verify_updater_manifest(manifest_path=manifest, expected_version=aligned)
            self.assertTrue(ok_res["ok"])
            self.assertEqual(ok_res["platforms"], ["darwin-aarch64", "windows-x86_64"])

            manifest.write_text(json.dumps({
                "version": aligned,
                "platforms": {
                    "windows-x86_64": {"url": "https://example.invalid/satz.exe", "signature": valid_sig},
                },
            }), encoding="utf-8")
            with self.assertRaises(AssertionError) as miss_ctx:
                release_version.verify_updater_manifest(manifest_path=manifest, expected_version=aligned)
            self.assertIn("darwin", str(miss_ctx.exception))

        # Sequential updater shutdown before install in src/updater.ts
        updater_src = (REPO_ROOT / "src" / "updater.ts").read_text(encoding="utf-8")
        self.assertIn("await update.download(", updater_src)
        self.assertIn('await invoke("prepare_for_update")', updater_src)
        self.assertIn("await update.install()", updater_src)
        self.assertNotIn("downloadAndInstall(async", updater_src)

        # Dry-run bump + tag preview in git_sync must not modify manifests
        dry = git_sync.sync_and_push(bump="fix", push=True, dry_run=True)
        self.assertTrue(dry["ok"])
        self.assertTrue(dry["dry_run"])
        self.assertEqual(dry["tag"], f"v{dry['bumped_version']}")
        self.assertEqual(check_version_parity(), aligned)


if __name__ == "__main__":
    unittest.main()
