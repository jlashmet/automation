from __future__ import print_function

import importlib.util
import os
import unittest


MODULE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto.py")
SPEC = importlib.util.spec_from_file_location("scene_issue_auto_prompt_policy", MODULE_PATH)
auto = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(auto)


class PromptPolicyTests(unittest.TestCase):
    def test_feature_prompt_keeps_work_bounded_and_reusable(self):
        prompt = auto.task_prompt(4, "feature-id", auto.FEATURE_WORK_KIND)
        self.assertIn("SceneIssues/README.md", prompt)
        self.assertNotIn("SceneIssues/feature-readme.md", prompt)
        self.assertIn("do not add opportunistic enhancements", prompt)
        self.assertIn("next unchecked", prompt)
        self.assertIn("semantic/config-driven", prompt)
        self.assertIn("same gate fails twice", prompt)

    def test_issue_prompt_uses_canonical_guide(self):
        prompt = auto.task_prompt(2, "issue-id", auto.ISSUE_WORK_KIND)
        self.assertIn("SceneIssues/README.md", prompt)
        self.assertNotIn("SceneIssues/issue-readme.md", prompt)
        self.assertLessEqual(len(prompt.split()), 160)

    def test_completed_ci_failure_reuses_only_assigned_transport(self):
        prompt = auto.continuation_prompt(9, "water", {
            "completion_gate": {
                "state": "failure",
                "ci_branch": "ci-test/fixes/agent-9",
                "ci_head": "abc123",
            },
        })
        self.assertIn("completed failure", prompt)
        self.assertIn("reuse only this assigned CI transport", prompt)
        self.assertIn("Never replace active CI", prompt)

    def test_generic_continuation_is_queue_state_aware(self):
        prompt = auto.continuation_prompt(5, "feature-id", {
            "work_kind": auto.FEATURE_WORK_KIND,
        })
        self.assertIn("SceneIssues/open/feature-id", prompt)
        self.assertIn("SceneIssues/pending/feature-id", prompt)
        self.assertIn("do not move it backward", prompt)
        self.assertIn("SceneIssues/README.md", prompt)
        self.assertNotIn("feature-readme", prompt)
        self.assertIn("next unchecked", prompt)


if __name__ == "__main__":
    unittest.main()
