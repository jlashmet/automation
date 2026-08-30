from __future__ import print_function

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest


MODULE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto.py")
SPEC = importlib.util.spec_from_file_location("scene_issue_auto_folder_state", MODULE_PATH)
auto = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(auto)


class FolderStateTests(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="automation-folder-state-")
        self.addCleanup(shutil.rmtree, self.repo)
        self.previous_repo = auto.REPO_PATH
        auto.REPO_PATH = self.repo
        self.addCleanup(setattr, auto, "REPO_PATH", self.previous_repo)
        self.git("init", "-q")
        self.git("config", "user.name", "Auto Test")
        self.git("config", "user.email", "auto@example.invalid")

    def git(self, *arguments):
        output = subprocess.check_output(["git", "-C", self.repo] + list(arguments))
        return output.decode("utf-8")

    def write_issue(self, folder, task_id, value):
        directory = os.path.join(self.repo, "SceneIssues", folder, task_id)
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, "issue.json"), "w") as handle:
            json.dump(value, handle)

    def publish_master(self):
        self.git("add", ".")
        self.git("commit", "-qm", "queue state")
        head = self.git("rev-parse", "HEAD").strip()
        self.git("update-ref", "refs/remotes/origin/master", head)
        return head

    def test_open_queue_uses_folder_not_status_and_closed_wins_duplicates(self):
        self.write_issue("open", "open-stale-status", {"status": "fixed"})
        self.write_issue("open", "pending-duplicate", {"status": "open"})
        self.write_issue("pending", "pending-duplicate", {"status": "fixed"})
        self.write_issue("open", "closed-duplicate", {"status": "open"})
        self.write_issue("closed", "closed-duplicate", {"status": "open"})
        self.publish_master()

        self.assertEqual(["open-stale-status"], auto.list_open_tasks())

    def test_closed_folder_releases_worker_even_when_metadata_says_open(self):
        self.write_issue("closed", "capture", {"status": "open"})
        master_head = self.publish_master()
        registry = {"version": 1, "tasks": {"capture": {
            "status": "in_progress",
            "owner": "agent-3",
            "branch": "fixes/agent-3",
            "ci_branch": "ci-test/fixes/agent-3",
        }}}

        changed = auto.reconcile_assignments(registry, now=123)

        self.assertTrue(changed)
        info = registry["tasks"]["capture"]
        self.assertEqual("fixed", info["status"])
        self.assertEqual(master_head, info["completion_commit"])
        self.assertEqual(123, info["completed_at"])
        self.assertIsNone(auto.get_agent_task("agent-3", registry))
        self.assertIn("closed folder contains status=open",
                      info["completion_audit_warnings"])


if __name__ == "__main__":
    unittest.main()
