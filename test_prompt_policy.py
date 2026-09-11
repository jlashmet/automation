from __future__ import print_function

import importlib.util
import os
import unittest


MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
MODULE_PATH = os.path.join(MODULE_DIR, "auto.py")
SPEC = importlib.util.spec_from_file_location("scene_issue_auto_prompt_policy", MODULE_PATH)
auto = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(auto)


class PromptPolicyTests(unittest.TestCase):
    def test_bootstrap_without_dunder_file(self):
        with open(MODULE_PATH, "rb") as handle:
            source = handle.read()
        namespace = {
            "__name__": "scene_issue_auto_no_file_test",
            "getBundlePath": lambda: MODULE_DIR,
        }
        exec(compile(source, "auto.py", "exec"), namespace, namespace)
        self.assertIn("task_prompt", namespace)
        self.assertTrue(namespace["_CORE_PATH"].endswith("auto_core.py"))

    def test_target_is_mounting_force_only(self):
        self.assertEqual(auto.TARGET_REPOSITORY, "jlashmet/mounting-force-2")
        self.assertTrue(auto.DEFAULT_TARGET_REPO_PATH.endswith("/mounting-force-2"))
        self.assertEqual(auto.GITHUB_REPOSITORY, "jlashmet/mounting-force-2")
        self.assertNotIn("voxel", auto.REPO_PATH.lower())

    def test_feature_prompt_is_bounded_reusable_and_two_state(self):
        prompt = auto.task_prompt(4, "feature-id", auto.FEATURE_WORK_KIND)
        self.assertIn("jlashmet/mounting-force-2", prompt)
        self.assertIn("SceneIssues/feature-readme.md", prompt)
        self.assertIn("no opportunistic enhancements", prompt)
        self.assertIn("semantic/config-driven", prompt)
        self.assertIn("refactor adjacent systems", prompt)
        self.assertIn("SceneIssues/open/feature-id", prompt)
        self.assertIn("SceneIssues/closed/feature-id", prompt)
        self.assertNotIn("SceneIssues/pending/", prompt)

    def test_issue_prompt_requires_chat_on_steroids_and_master(self):
        prompt = auto.task_prompt(2, "issue-id", auto.ISSUE_WORK_KIND)
        self.assertIn("Chat on Steroids", prompt)
        self.assertIn("Work directly on `master`", prompt)
        self.assertIn("push to `origin/master`", prompt)
        self.assertNotIn("fixes/agent-2", prompt)
        self.assertNotIn("ci-test/fixes/agent-2", prompt)

    def test_prompt_requires_retrying_transient_chat_on_steroids_failures(self):
        prompt = auto.task_prompt(2, "issue-id", auto.ISSUE_WORK_KIND)
        self.assertIn("fail intermittently", prompt)
        self.assertIn("transient failures", prompt)
        self.assertIn("keep retrying the same operation", prompt)
        self.assertIn("rather than abandoning the tool or switching workflows", prompt)

    def test_prompt_requires_periodic_origin_master_reconciliation(self):
        prompt = auto.task_prompt(3, "issue-id", auto.ISSUE_WORK_KIND)
        self.assertIn("Periodically pull from `origin/master`", prompt)
        self.assertIn("resolve any conflicts carefully", prompt)
        self.assertIn("preserving valid changes from both sides", prompt)
        self.assertIn("immediately before pushing", prompt)

    def test_generic_continuation_keeps_same_master_policy(self):
        prompt = auto.continuation_prompt(5, "feature-id", {
            "work_kind": auto.FEATURE_WORK_KIND,
        })
        self.assertIn("SceneIssues/open/feature-id", prompt)
        self.assertNotIn("SceneIssues/pending/", prompt)
        self.assertIn("next unchecked", prompt)
        self.assertIn("Record blockers", prompt)
        self.assertIn("Chat on Steroids", prompt)
        self.assertIn("Periodically pull from `origin/master`", prompt)
        self.assertIn("commit directly on `master`", prompt)

    def test_old_branch_cleanup_redirects_to_master(self):
        prompt = auto.branch_cleanup_prompt(9, "abc123")
        self.assertIn("Do not continue work on an old agent/feature branch", prompt)
        self.assertIn("current `master`", prompt)
        self.assertIn("periodically pull `origin/master`", prompt)
        self.assertIn("push to `origin/master`", prompt)

    def test_unconfirmed_assignment_retries_even_while_ci_is_active(self):
        info = {
            "last_prompted": 0,
            "prompt_count": 0,
            "prompt_confirmed": False,
            "ci_activity": {"state": "in_progress"},
        }
        self.assertTrue(auto.should_nudge(info, now=100000))


if __name__ == "__main__":
    unittest.main()
