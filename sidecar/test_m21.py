"""Unit and integration tests for Milestone M21 (One Command Bar)."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

SIDECAR_DIR = Path(__file__).resolve().parent
REPO_ROOT = SIDECAR_DIR.parent
SGS_ROOT = REPO_ROOT.parent / "sgs"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))
if str(SGS_ROOT) not in sys.path:
    sys.path.insert(0, str(SGS_ROOT))

from satz_models import SatzSidecarRuntime


class TestM21CommandBar(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="satz_test_m21_"))
        self.store_path = self.temp_dir / "planck_store.sqlite"
        self.runtime = SatzSidecarRuntime(sgs_root=SGS_ROOT, store_path=self.store_path)
        self.runtime.mail.pipeline.stop_worker()
        self.runtime.passwords.create_profile("nikita", "123456")

    def tearDown(self) -> None:
        try:
            self.runtime.close()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_m21_six_example_lines_route_correctly_by_default(self) -> None:
        """
        Section 7 (M21) Gate:
        Verify the 6 example lines (URL, URL + question, question, mail term, Brain term, command)
        each route correctly by default with explicit privacy disclosure.
        """
        # 1. URL: "dw.com" -> default route is open_url ("loads dw.com")
        r_url = self.runtime.rank_command_bar_routes("dw.com", web_enabled=False)
        self.assertGreaterEqual(len(r_url), 3)
        self.assertEqual(r_url[0]["kind"], "open_url")
        self.assertEqual(r_url[0]["url"], "https://dw.com")
        self.assertEqual(r_url[0]["privacy"], "loads dw.com")
        self.assertTrue(r_url[0]["leaves_machine"])

        # 2. URL + question: "dw.com what are the top stories today?" -> default route is url_and_question
        r_url_q = self.runtime.rank_command_bar_routes(
            "dw.com what are the top stories today?",
            web_enabled=False,
        )
        self.assertGreaterEqual(len(r_url_q), 3)
        self.assertEqual(r_url_q[0]["kind"], "url_and_question")
        self.assertEqual(r_url_q[0]["url"], "https://dw.com")
        self.assertEqual(r_url_q[0]["question"], "what are the top stories today?")
        self.assertEqual(r_url_q[0]["privacy"], "loads dw.com · local model")
        self.assertTrue(r_url_q[0]["leaves_machine"])

        # 3. Question: "what is the capital of Portugal?" -> default route is ask_model
        # 3a. With web_enabled=False -> "local only"
        r_q_local = self.runtime.rank_command_bar_routes(
            "what is the capital of Portugal?",
            web_enabled=False,
        )
        self.assertEqual(r_q_local[0]["kind"], "ask_model")
        self.assertEqual(r_q_local[0]["question"], "what is the capital of Portugal?")
        self.assertEqual(r_q_local[0]["privacy"], "local only")
        self.assertFalse(r_q_local[0]["leaves_machine"])

        # 3b. With web_enabled=True -> "web search · duckduckgo"
        r_q_web = self.runtime.rank_command_bar_routes(
            "what is the capital of Portugal?",
            web_enabled=True,
        )
        self.assertEqual(r_q_web[0]["kind"], "ask_model")
        self.assertEqual(r_q_web[0]["privacy"], "web search · duckduckgo")
        self.assertTrue(r_q_web[0]["leaves_machine"])

        # 4. Mail term: "mail: Jordan Reyes" (and bare "Jordan Reyes") -> default route is search_mail
        for mail_line in ("mail: Jordan Reyes", "Jordan Reyes"):
            r_mail = self.runtime.rank_command_bar_routes(mail_line, web_enabled=False)
            self.assertEqual(r_mail[0]["kind"], "search_mail", f"Failed on {mail_line!r}")
            self.assertEqual(r_mail[0]["query"], "Jordan Reyes")
            self.assertEqual(r_mail[0]["privacy"], "local only")
            self.assertFalse(r_mail[0]["leaves_machine"])

        # 5. Brain term: "brain: zalando" (and bare "zalando") -> default route is search_brain
        for brain_line in ("brain: zalando", "zalando"):
            r_brain = self.runtime.rank_command_bar_routes(brain_line, web_enabled=False)
            self.assertEqual(r_brain[0]["kind"], "search_brain", f"Failed on {brain_line!r}")
            self.assertEqual(r_brain[0]["query"], "zalando")
            self.assertEqual(r_brain[0]["privacy"], "local only")
            self.assertFalse(r_brain[0]["leaves_machine"])

        # 6. Command: "home", "new conversation", "bookmark", "compare", "lock" -> default route is run_command
        expected_cmds = {
            "home": "home",
            "new conversation": "new_conversation",
            "bookmark": "bookmark",
            "compare": "compare",
            "lock": "lock",
        }
        for cmd_line, expected_id in expected_cmds.items():
            r_cmd = self.runtime.rank_command_bar_routes(cmd_line, web_enabled=False)
            self.assertEqual(r_cmd[0]["kind"], "run_command", f"Failed on {cmd_line!r}")
            self.assertEqual(r_cmd[0]["command_id"], expected_id)
            self.assertEqual(r_cmd[0]["privacy"], "local only")
            self.assertFalse(r_cmd[0]["leaves_machine"])

    def test_drives_command_bar_prefixes_route_to_search_drives(self) -> None:
        for line, expected_q in (
            ("drive: AHM", "AHM"),
            ("files: budget", "budget"),
            ("search drives Q4", "Q4"),
            ("open drives", ""),
        ):
            routes = self.runtime.rank_command_bar_routes(line, web_enabled=False)
            self.assertEqual(routes[0]["kind"], "search_drives", f"Failed on {line!r}")
            self.assertEqual(routes[0]["query"], expected_q)
            self.assertEqual(routes[0]["privacy"], "local only")
            self.assertFalse(routes[0]["leaves_machine"])


if __name__ == "__main__":
    unittest.main()
