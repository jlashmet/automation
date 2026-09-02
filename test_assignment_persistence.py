from __future__ import print_function

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest


MODULE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto.py")
SPEC = importlib.util.spec_from_file_location("scene_issue_auto_assignment_test", MODULE_PATH)
auto = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(auto)


class AssignmentPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="voxel-auto-assignment-")
        self.addCleanup(shutil.rmtree, self.directory)
        self.remote = os.path.join(self.directory, "remote.git")
        subprocess.check_call(
            ["git", "init", "--bare", self.remote],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        seed = self._clone("seed")
        issue_dir = os.path.join(seed, "SceneIssues", "open", "task-001")
        os.makedirs(issue_dir)
        with open(os.path.join(issue_dir, "issue.json"), "w") as handle:
            json.dump({
                "id": "task-001",
                "status": "open",
                "note": "FEATURE assignment persistence fixture",
            }, handle, indent=2)
            handle.write("\n")
        self._git(seed, ["add", "."])
        self._git(seed, ["commit", "-m", "seed fixture"])
        self._git(seed, ["branch", "-M", "master"])
        self._git(seed, ["push", "-u", "origin", "master"])
        self._git(seed, [
            "push", "origin", "master:refs/heads/automation/assignments",
        ])

        self.computer1 = self._clone("computer-1")
        self.computer2 = self._clone("computer-2")
        self._saved_globals = {}
        for name in (
                "REPO_PATH", "SCENE_ISSUES_PATH", "OPEN_SCENE_ISSUES_PATH",
                "PENDING_SCENE_ISSUES_PATH", "REMOTE", "QUEUE_REF",
                "ASSIGNMENT_BRANCH", "ASSIGNMENT_REF", "ASSIGNMENT_REMOTE_REF"):
            self._saved_globals[name] = getattr(auto, name)
        self.addCleanup(self._restore_globals)

    def _restore_globals(self):
        for name, value in self._saved_globals.items():
            setattr(auto, name, value)

    def _clone(self, name):
        path = os.path.join(self.directory, name)
        subprocess.check_call(
            ["git", "clone", self.remote, path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._git(path, ["config", "user.name", "Assignment Test"])
        self._git(path, ["config", "user.email", "assignment-test@example.invalid"])
        return path

    def _git(self, repo, arguments):
        process = subprocess.Popen(
            ["git", "-C", repo] + list(arguments),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            raise AssertionError(
                "git %s failed: %s" % (
                    " ".join(arguments), stderr.decode("utf-8", "replace")))
        return stdout.decode("utf-8", "replace")

    def _use_repo(self, repo):
        auto.REPO_PATH = repo
        auto.SCENE_ISSUES_PATH = os.path.join(repo, "SceneIssues")
        auto.OPEN_SCENE_ISSUES_PATH = os.path.join(auto.SCENE_ISSUES_PATH, "open")
        auto.PENDING_SCENE_ISSUES_PATH = os.path.join(auto.SCENE_ISSUES_PATH, "pending")
        auto.REMOTE = "origin"
        auto.QUEUE_REF = "origin/master"
        auto.ASSIGNMENT_BRANCH = "automation/assignments"
        auto.ASSIGNMENT_REF = "refs/remotes/origin/automation/assignments"
        auto.ASSIGNMENT_REMOTE_REF = "refs/heads/automation/assignments"
        auto.fetch_remote()

    def test_claim_survives_machine_switch_and_stale_claim_cannot_overwrite(self):
        self._use_repo(self.computer1)
        registry1 = auto.load_registry(now=1000)
        open1 = auto.list_open_tasks()

        self._use_repo(self.computer2)
        registry2 = auto.load_registry(now=1000)
        open2 = auto.list_open_tasks()

        self._use_repo(self.computer1)
        self.assertEqual("task-001", auto.claim_new_task(
            "agent-1", "fixes/agent-1", "ci-test/fixes/agent-1",
            registry1, open1, now=1001))
        self.assertTrue(auto.save_registry(registry1))
        self.assertEqual("", self._git(self.computer1, ["status", "--porcelain"]))

        self._use_repo(self.computer2)
        self.assertEqual("task-001", auto.claim_new_task(
            "agent-2", "fixes/agent-2", "ci-test/fixes/agent-2",
            registry2, open2, now=1002))
        self.assertFalse(auto.save_registry(registry2))
        self.assertEqual("task-001", auto.get_agent_task("agent-1", registry2))
        self.assertIsNone(auto.get_agent_task("agent-2", registry2))

        computer3 = self._clone("computer-3")
        self._use_repo(computer3)
        registry3 = auto.load_registry(now=2000)
        info = registry3["tasks"]["task-001"]
        self.assertEqual("agent-1", info["owner"])
        self.assertEqual("fixes/agent-1", info["branch"])
        self.assertEqual("ci-test/fixes/agent-1", info["ci_branch"])
        self.assertEqual(2000, info["last_heartbeat"])

        raw = self._git(computer3, [
            "show",
            "origin/automation/assignments:SceneIssues/open/task-001/issue.json",
        ])
        durable = json.loads(raw)["assignment"]
        self.assertEqual("agent-1", durable["owner"])
        self.assertNotIn("last_heartbeat", durable)
        self.assertNotIn("last_prompted", durable)
        self.assertNotIn("prompt_count", durable)


if __name__ == "__main__":
    unittest.main()
