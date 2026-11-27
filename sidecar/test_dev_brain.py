#!/usr/bin/env python3
"""Tests for the Satz Development Hub, Brain Index Graph DB, Monitor, Eval, and Lifecycle Hooks."""
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

from dev_brain import DevBrain  # noqa: E402
from pre_commit_dev_sync import check_ui_and_weight_limits, check_version_parity  # noqa: E402
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
        self.assertGreaterEqual(len(plan_subdirs), 10)
        for pdir in plan_subdirs:
            self.assertTrue((pdir / "v1.md").is_file(), f"Missing v1.md in {pdir}")
            self.assertTrue((pdir / "tasks.md").is_file(), f"Missing tasks.md in {pdir}")

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
        self.assertIn("matcher", spec["PostToolUse"][0])

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
        self.assertNotIn("_template", msg)

    def test_session_start_and_pre_invocation_contracts_and_dedupe(self) -> None:
        before_hash = hashlib.sha256(self.brain.db_path.read_bytes()).hexdigest()

        # Claude Code SessionStart
        out_cc = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps({"hook_event_name": "SessionStart", "session_id": "cc-1"}))), \
             mock.patch("sys.stdout", out_cc):
            session_start_context.main()
        parsed_cc = json.loads(out_cc.getvalue())
        self.assertEqual(parsed_cc["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("Mandatory guardrails:", parsed_cc["hookSpecificOutput"]["additionalContext"])

        # PreInvocation injects DevBrain context once per conversation+prompt, skips invocationNum > 1
        with tempfile.TemporaryDirectory() as tmpd:
            cache_file = str(Path(tmpd) / "cache.json")
            with mock.patch.dict(os.environ, {"SATZ_HOOK_CACHE_PATH": cache_file}):
                out1 = io.StringIO()
                payload1 = {
                    "hookEventName": "PreInvocation",
                    "conversationId": "conv-ut",
                    "invocationNum": 1,
                    "lastUserInput": "release packaging and macos updater signature",
                }
                with mock.patch("sys.stdin", io.StringIO(json.dumps(payload1))), mock.patch("sys.stdout", out1):
                    pre_invocation_context.main()
                d1 = json.loads(out1.getvalue())
                injected = d1["injectSteps"][0]["systemMessage"]["systemMessage"]
                self.assertIn("[DevBrain Relevant Context]", injected)
                self.assertIn("RELEASE_RUNBOOK.md", injected)

                # Same prompt on second invocation or duplicate call -> {}
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
            with mock.patch.object(hook_common, "BEHAVIOR_LOG", temp_log):
                # 1. Block ../sgs edits (Antigravity)
                r1 = pre_tool_guard.evaluate_tool_call({
                    "hookEventName": "PreToolUse",
                    "toolCall": {"name": "edit_file", "args": {"Path": "../sgs/README.md", "Replacement": "x"}},
                })
                self.assertIsNotNone(r1)
                self.assertIn("read-only", r1)

                # 2. Block em dash in src/i18n/catalog.ts (Claude Code)
                r2 = pre_tool_guard.evaluate_tool_call({
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "src/i18n/catalog.ts", "new_string": "Hello \u2014 world"},
                })
                self.assertIsNotNone(r2)
                self.assertIn("em/en dash", r2)

                # 3. Block hardcoded CSS hex outside tokens.css, permit tokens.css
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

                # 4. Block mismatched git tag version
                r4 = pre_tool_guard.evaluate_tool_call({
                    "hookEventName": "PreToolUse",
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "git tag -a v9.9.9 -m rel"}},
                })
                self.assertIsNotNone(r4)
                self.assertIn("Blocked git tag v9.9.9", r4)

                # 5. Allow normal source edit cleanly (empty {})
                out = io.StringIO()
                with mock.patch("sys.stdin", io.StringIO(json.dumps({
                    "hookEventName": "PreToolUse",
                    "toolCall": {"name": "edit_file", "args": {"Path": "src/main.ts", "Replacement": "const x = 1;"}},
                }))), mock.patch("sys.stdout", out):
                    pre_tool_guard.main()
                self.assertEqual(json.loads(out.getvalue()), {})

    def test_post_edit_brain_sync_handles_antigravity_and_claude_dev_edits(self) -> None:
        with mock.patch.object(post_edit_brain_sync, "append_behavior_log") as log_mock:
            with mock.patch("scripts.dev_brain.DevBrain.reindex", return_value={"nodes": 80, "edges": 140}) as reidx_mock:
                res = post_edit_brain_sync.handle_post_tool({
                    "hookEventName": "PostToolUse",
                    "toolCall": {"name": "replace_file_content", "args": {"TargetFile": "dev/agents/INSTRUCTIONS.md"}},
                })
                self.assertEqual(res["action"], "reindexed")
                self.assertEqual(reidx_mock.call_count, 1)
                self.assertEqual(log_mock.call_count, 1)

    def test_stop_gate_check_loop_guard_and_broken_link_block(self) -> None:
        # Must immediately noop when continuationActive / stop_hook_active is true
        self.assertIsNone(stop_gate_check.evaluate_stop({"continuationActive": True, "terminationReason": "NO_TOOL_CALL"}))
        self.assertIsNone(stop_gate_check.evaluate_stop({"stop_hook_active": True}))
        self.assertIsNone(stop_gate_check.evaluate_stop({"continuationActive": False, "terminationReason": "USER_CANCELED"}))

        # Broken edge triggers continue/block cleanly
        fake_mon = {
            "stale_count": 0,
            "broken_edge_count": 1,
            "broken_links": [{"source": "dev/a.md", "target": "missing.md"}],
        }
        with mock.patch("scripts.dev_brain.DevBrain.monitor", return_value=fake_mon), \
             mock.patch.object(stop_gate_check, "_git_dirty_paths", return_value=[]):
            out = io.StringIO()
            with mock.patch("sys.stdin", io.StringIO(json.dumps({"continuationActive": False, "terminationReason": "NO_TOOL_CALL"}))), \
                 mock.patch("sys.stdout", out), \
                 mock.patch.object(stop_gate_check, "append_behavior_log"):
                stop_gate_check.main()
            parsed = json.loads(out.getvalue())
            self.assertEqual(parsed["decision"], "continue")
            self.assertIn("missing.md", parsed["reason"])


if __name__ == "__main__":
    unittest.main()
