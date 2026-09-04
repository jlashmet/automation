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

    def test_feature_prompt_is_bounded_reusable_and_two_state(self):
        prompt = auto.task_prompt(4, "feature-id", auto.FEATURE_WORK_KIND)
        self.assertIn("SceneIssues/feature-readme.md", prompt)
        self.assertIn("no opportunistic enhancements", prompt)
        self.assertIn("semantic/config-driven", prompt)
        self.assertIn("Do not refactor adjacent systems", prompt)
        self.assertIn("SceneIssues/open/feature-id", prompt)
        self.assertIn("SceneIssues/closed/feature-id", prompt)
        self.assertNotIn("SceneIssues/pending/", prompt)

    def test_issue_prompt_stays_concise(self):
        prompt = auto.task_prompt(2, "issue-id", auto.ISSUE_WORK_KIND)
        self.assertIn("SceneIssues/issue-readme.md", prompt)
        self.assertIn("minimal repro/root cause", prompt)
        self.assertNotIn("SceneIssues/pending/", prompt)
        self.assertLessEqual(len(prompt.split()), 150)

    def test_completed_ci_failure_reuses_only_assigned_transport(self):
        prompt = auto.continuation_prompt(9, "water", {
            "completion_gate": {
                "state": "failure",
                "ci_branch": "ci-test/fixes/agent-9",
                "ci_head": "abc123",
            },
        })
        self.assertIn("reuse this same CI transport", prompt)
        self.assertIn("Never replace active CI", prompt)

    def test_generic_continuation_keeps_task_open_until_close(self):
        prompt = auto.continuation_prompt(5, "feature-id", {
            "work_kind": auto.FEATURE_WORK_KIND,
        })
        self.assertIn("SceneIssues/open/feature-id", prompt)
        self.assertNotIn("SceneIssues/pending/", prompt)
        self.assertIn("next unchecked", prompt)
        self.assertIn("external prerequisite", prompt)

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
