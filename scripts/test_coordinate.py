"""Exercise observable helper behavior with an isolated herdr service substitute."""

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("coordinate", Path(__file__).with_name("coordinate.py"))
coordinate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(coordinate)


class CoordinateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.agents = [
            {"pane_id": "p1", "terminal_id": "t1", "agent_session": {"value": "s1"}, "tokens": {}},
            {"pane_id": "p2", "terminal_id": "t2", "agent_session": {"value": "s2"}, "tokens": {
                "coop_repo": "/repo/.git", "coop_files": "src/peer.py", "coop_state": "working",
            }},
        ]
        self.calls = []
        self.fail_list = False
        self.fail_publish = False
        self.branch = "main"
        self.addCleanup(patch.stopall)
        patch.object(coordinate.tempfile, "gettempdir", return_value=self.temp.name).start()
        patch.object(coordinate, "command", side_effect=self.command).start()
        patch.dict(coordinate.os.environ, {"HERDR_SOCKET_PATH": "test-socket"}).start()

    def command(self, *args):
        self.calls.append(args)
        if args[0] == "git":
            if "--git-common-dir" in args:
                return "/repo/.git\n/repo"
            if "--abbrev-ref" in args:
                return self.branch
            return "0123456789"
        if args == ("herdr", "agent", "list"):
            if self.fail_list:
                raise RuntimeError("unreachable")
            return json.dumps({"result": {"agents": self.agents}})
        if args[:3] == ("herdr", "pane", "report-metadata"):
            if self.fail_publish:
                raise RuntimeError("publish failed")
            for offset, value in enumerate(args):
                if value == "--token":
                    key, token = args[offset + 1].split("=", 1)
                    if token:
                        self.agents[0]["tokens"][key] = token[:80]
                    else:
                        self.agents[0]["tokens"].pop(key, None)
            return ""
        self.fail("Unexpected operation: " + str(args))

    def run_helper(self, *args):
        output = io.StringIO()
        with patch("sys.argv", ["coordinate.py", "--pane", "p1", *args]), contextlib.redirect_stdout(output):
            coordinate.main()
        return json.loads(output.getvalue())

    def publications(self):
        return [call for call in self.calls if call[:3] == ("herdr", "pane", "report-metadata")]

    def test_publish_then_unchanged_check_and_revision_noise(self):
        first = self.run_helper("--task", "Work", "--file", "src/own.py", "--model", "gpt-6-luna", "--effort", "medium")
        self.assertTrue(first["published"])
        self.assertIn("p2", first["peers"])
        self.assertEqual(first["self"]["declaration"]["coop_model"], "gpt-6-luna")
        self.assertEqual(first["self"]["declaration"]["coop_effort"], "medium")
        self.agents[1].update(revision=99, agent_status="idle", terminal_title="new")
        self.assertEqual(self.run_helper(), {"published": False, "unchanged": 1})
        self.assertEqual(self.run_helper("--task", "Work", "--file", "src/own.py", "--model", "gpt-6-luna", "--effort", "medium"), {"published": False, "unchanged": 1})
        self.assertEqual(len(self.publications()), 1)
        self.assertEqual(sum(call == ("herdr", "agent", "list") for call in self.calls), 3)

    def test_changed_claim_and_disappeared_peer_are_reported(self):
        self.run_helper()
        self.agents[1]["tokens"]["coop_files"] = "src/changed.py"
        self.assertIn("p2", self.run_helper()["peers"])
        self.agents.pop()
        missing = self.run_helper()
        self.assertEqual(missing["removed"], ["p2"])
        self.assertIn("p2", self.run_helper()["missing_unreleased"])

    def test_long_declaration_and_literal_shell_characters(self):
        files = ["src/" + "a" * 100, "$(touch /tmp/never)`literal`"]
        first = self.run_helper("--task", "Work", "--file", files[0], "--file", files[1], "--note", "n" * 200)
        second = self.run_helper("--full")
        self.assertEqual(second["self"]["declaration"], first["self"]["declaration"])
        self.assertEqual(second["self"]["declaration"]["coop_files"], ",".join(files))

    def test_failure_does_not_claim_success_and_publish_is_retried(self):
        self.fail_list = True
        with self.assertRaises(RuntimeError):
            self.run_helper("--task", "Work")
        self.assertEqual(self.publications(), [])
        self.fail_list = False
        self.fail_publish = True
        with self.assertRaises(RuntimeError):
            self.run_helper("--task", "Work")
        self.fail_publish = False
        self.assertTrue(self.run_helper("--task", "Work")["published"])

    def test_handoff_survives_session_replacement_without_automatic_adoption(self):
        self.run_helper("--task", "Work", "--model", "gpt-6-luna", "--effort", "unknown", "--handoff", "Agreement: peer owns Git. Next: review.")
        self.agents[0]["agent_session"] = {"value": "replacement"}
        result = self.run_helper("--full")
        self.assertIn("peer owns Git", result["prior_self_unconfirmed"]["handoff"])
        self.assertFalse(result["published"])
        self.assertEqual(len(self.publications()), 1)

    def test_model_effort_changes_are_republished_and_unknown_is_explicit(self):
        first = self.run_helper("--task", "Work", "--model", "gpt-6-luna", "--effort", "unknown")
        self.assertEqual(first["self"]["declaration"]["coop_effort"], "unknown")
        changed = self.run_helper("--task", "Work", "--model", "gpt-6.1-sol", "--effort", "high")
        self.assertTrue(changed["published"])
        self.assertEqual(changed["self"]["declaration"]["coop_model"], "gpt-6.1-sol")
        self.assertEqual(changed["self"]["declaration"]["coop_effort"], "high")

    def test_remote_removal_restores_declaration_and_done_releases_files(self):
        self.run_helper("--task", "Work", "--file", "src/own.py")
        self.agents[0]["tokens"].clear()
        self.assertTrue(self.run_helper("--task", "Work", "--file", "src/own.py")["published"])
        self.run_helper("--task", "Work", "--state", "done", "--note", "Tests passed")
        self.assertNotIn("coop_files", self.agents[0]["tokens"])

    def test_other_repos_are_filtered_but_undeclared_peers_are_visible(self):
        self.agents.append({"pane_id": "p3", "terminal_id": "t3", "tokens": {"coop_repo": "/other/.git"}})
        self.agents.append({"pane_id": "p4", "terminal_id": "t4", "tokens": {}})
        self.assertEqual(set(self.run_helper()["peers"]), {"p2", "p4"})

    def test_detached_head_and_unknown_pane(self):
        self.branch = "HEAD"
        self.assertEqual(self.run_helper()["branch"], "detached:0123456789")
        self.agents[0]["pane_id"] = "different"
        with self.assertRaises(RuntimeError):
            self.run_helper("--task", "Work")
        self.assertEqual(self.publications(), [])

    def test_foreign_detail_path_is_not_read(self):
        self.agents[1]["tokens"]["coop_detail"] = "/etc/passwd"
        self.assertEqual(self.run_helper()["peers"]["p2"]["completeness"], "metadata-only")

    def test_peer_full_detail_is_used_only_when_identity_and_metadata_match(self):
        self.run_helper("--task", "Peer work", "--note", "x" * 160)
        peer = copy.deepcopy(self.agents[0])
        self.agents = [{"pane_id": "p1-new", "terminal_id": "new", "tokens": {}}, peer]
        with patch("sys.argv", ["coordinate.py", "--pane", "p1-new"]), contextlib.redirect_stdout(io.StringIO()) as output:
            coordinate.main()
        result = json.loads(output.getvalue())
        self.assertEqual(result["peers"]["p1"]["declaration"]["coop_note"], "x" * 160)
        self.agents[1]["tokens"]["coop_note"] = "different"
        with patch("sys.argv", ["coordinate.py", "--pane", "p1-new"]), contextlib.redirect_stdout(io.StringIO()) as output:
            coordinate.main()
        self.assertEqual(json.loads(output.getvalue())["peers"]["p1"]["completeness"], "metadata-only")


if __name__ == "__main__":
    unittest.main()
