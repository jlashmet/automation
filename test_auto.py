from __future__ import print_function

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest


MODULE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto.py")
SPEC = importlib.util.spec_from_file_location("scene_issue_auto", MODULE_PATH)
auto = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(auto)


class RegistryTests(unittest.TestCase):
    def test_conversation_limit_starts_new_chat_and_resets_prompt_state(self):
        registry = {"version": 1, "tasks": {"capture": {
            "status": "in_progress",
            "owner": "agent-2",
            "last_prompted": 123,
            "prompt_count": 7,
        }}}
        events = []
        previous_exists = auto.image_exists
        previous_click = auto.click_image
        previous_wait = getattr(auto, "wait", None)
        had_wait = hasattr(auto, "wait")
        auto.image_exists = lambda filename, timeout: filename == "new_chat.png"
        auto.click_image = lambda filename, timeout: events.append((filename, timeout)) or True
        auto.wait = lambda seconds: events.append(("wait", seconds))

        def restore():
            auto.image_exists = previous_exists
            auto.click_image = previous_click
            if had_wait:
                auto.wait = previous_wait
            else:
                delattr(auto, "wait")

        self.addCleanup(restore)

        recovered = auto.recover_long_conversation("agent-2", registry)

        self.assertTrue(recovered)
        self.assertEqual([("new_chat.png", 2), ("wait", 2)], events)
        self.assertEqual(0, registry["tasks"]["capture"]["last_prompted"])
        self.assertEqual(0, registry["tasks"]["capture"]["prompt_count"])
        self.assertFalse(registry["tasks"]["capture"]["prompt_confirmed"])

    def test_new_chat_gets_assignment_or_current_gate_context(self):
        active = auto.message_for_nudge(2, "capture", {
            "last_prompted": 99,
        }, started_new_chat=True)
        completion = auto.message_for_nudge(2, "capture", {
            "last_prompted": 0,
            "completion_gate": {
                "state": "close_and_merge",
            },
        }, started_new_chat=True)
        queued = auto.message_for_nudge(2, "capture", {
            "last_prompted": 0,
            "ci_activity": {"state": "queued", "ci_head": "abc123"},
        }, started_new_chat=True)

        self.assertIn("Fix only `SceneIssues/open/capture`", active)
        self.assertIn("SceneIssues/closed/capture", completion)
        self.assertIn("origin/master", completion)
        self.assertIn("abc123", queued)
        self.assertIn("monitor it without replacing", queued)

    def test_send_message_requires_running_response_confirmation(self):
        events = []
        previous_exists = auto.image_exists
        previous_click_image = auto.click_image
        replacements = {
            "click": lambda match: events.append(("click", match)),
            "paste": lambda text: events.append(("paste", text)),
            "wait": lambda seconds: events.append(("wait", seconds)),
        }
        missing = object()
        previous_globals = {
            name: getattr(auto, name, missing) for name in replacements
        }
        for name, value in replacements.items():
            setattr(auto, name, value)
        response_running = [True]

        def fake_exists(filename, timeout):
            if filename == "textbox.png":
                return "textbox-match"
            if filename == "in_progress.png":
                return response_running[0]
            return False

        auto.image_exists = fake_exists
        auto.click_image = lambda filename, timeout: filename == "submit.png"

        def restore():
            auto.image_exists = previous_exists
            auto.click_image = previous_click_image
            for name, value in previous_globals.items():
                if value is missing:
                    delattr(auto, name)
                else:
                    setattr(auto, name, value)

        self.addCleanup(restore)

        self.assertTrue(auto.send_message("do the task"))
        response_running[0] = False
        self.assertFalse(auto.send_message("retry the task"))
        self.assertIn(("paste", "do the task"), events)
        self.assertIn(("paste", "retry the task"), events)

    def test_switch_to_tab_scrolls_to_bottom_before_returning(self):
        events = []

        class FakeKey(object):
            CMD = "cmd"
            END = "end"

        replacements = {
            "keyDown": lambda value: events.append(("down", value)),
            "keyUp": lambda value: events.append(("up", value)),
            "type": lambda value: events.append(("type", value)),
            "wait": lambda value: events.append(("wait", value)),
            "Key": FakeKey,
        }
        missing = object()
        previous = {name: getattr(auto, name, missing) for name in replacements}
        for name, value in replacements.items():
            setattr(auto, name, value)

        def restore():
            for name, value in previous.items():
                if value is missing:
                    delattr(auto, name)
                else:
                    setattr(auto, name, value)

        self.addCleanup(restore)

        auto.switch_to_tab(4)

        self.assertEqual([
            ("down", "cmd"),
            ("type", "4"),
            ("up", "cmd"),
            ("wait", 1),
            ("type", "end"),
            ("wait", 1),
        ], events)

    def test_assignment_prompt_names_only_the_agents_persistent_branches(self):
        prompt = auto.task_prompt(3, "20260825-capture")

        self.assertIn("`fixes/agent-3`", prompt)
        self.assertIn("`ci-test/fixes/agent-3`", prompt)
        self.assertIn("SceneIssues/open/20260825-capture", prompt)
        self.assertIn("SceneIssues/pending/20260825-capture", prompt)
        self.assertIn("SceneIssues/closed/20260825-capture", prompt)
        self.assertIn("competing hypotheses", prompt)
        self.assertIn("behavioral regression", prompt)
        self.assertIn("exact-SHA CI", prompt)
        self.assertIn("push that exact branch head to `origin/master`", prompt)
        self.assertLessEqual(len(prompt.split()), 170)

    def test_claims_are_oldest_first_and_exclusive(self):
        registry = {"version": 1, "tasks": {}}
        tasks = ["20260825-b", "20260824-a"]

        first = auto.claim_new_task(
            "agent-1", "fixes/agent-1", "ci-test/fixes/agent-1",
            registry, tasks, now=100)
        second = auto.claim_new_task(
            "agent-2", "fixes/agent-2", "ci-test/fixes/agent-2",
            registry, tasks, now=101)

        self.assertEqual("20260824-a", first)
        self.assertEqual("20260825-b", second)
        self.assertEqual("agent-1", registry["tasks"][first]["owner"])
        self.assertEqual("agent-2", registry["tasks"][second]["owner"])

    def test_stale_claim_is_recovered_with_history(self):
        registry = {"version": 1, "tasks": {}}
        previous_check = auto.branch_has_unmerged_work
        auto.branch_has_unmerged_work = lambda unused_branch: False
        self.addCleanup(setattr, auto, "branch_has_unmerged_work", previous_check)
        auto.claim_new_task(
            "agent-1", "fixes/agent-1", "ci-test/fixes/agent-1",
            registry, ["capture"], now=10)

        claimed = auto.claim_new_task(
            "agent-2", "fixes/agent-2", "ci-test/fixes/agent-2",
            registry, ["capture"], now=10 + auto.STALE_SECONDS + 1)

        self.assertEqual("capture", claimed)
        info = registry["tasks"]["capture"]
        self.assertEqual("agent-2", info["owner"])
        self.assertEqual("agent-1", info["lease_history"][0]["owner"])
        self.assertEqual("stale", info["lease_history"][0]["ended_as"])

    def test_stale_claim_with_unmerged_work_requires_handoff(self):
        registry = {"version": 1, "tasks": {}}
        auto.claim_new_task(
            "agent-1", "fixes/agent-1", "ci-test/fixes/agent-1",
            registry, ["capture"], now=10)
        previous_check = auto.branch_has_unmerged_work
        auto.branch_has_unmerged_work = lambda branch: branch == "fixes/agent-1"
        self.addCleanup(setattr, auto, "branch_has_unmerged_work", previous_check)

        claimed = auto.claim_new_task(
            "agent-2", "fixes/agent-2", "ci-test/fixes/agent-2",
            registry, ["capture"], now=10 + auto.STALE_SECONDS + 1)

        self.assertIsNone(claimed)
        info = registry["tasks"]["capture"]
        self.assertEqual("agent-1", info["owner"])
        self.assertTrue(info["handoff_required"])

    def test_continuation_prompt_explains_failed_ci_gate(self):
        info = {"completion_gate": {
            "state": "failure",
            "ci_branch": "ci-test/fixes/agent-4",
            "ci_head": "abc123",
            "fix_commit": "def456",
        }}

        prompt = auto.continuation_prompt(4, "20260825-capture", info)

        self.assertIn("ci/single-test=failure", prompt)
        self.assertIn("ci-test/fixes/agent-4", prompt)
        self.assertIn("abc123", prompt)
        self.assertIn("infrastructure failure", prompt)
        self.assertIn("update the assigned CI ref once", prompt)

    def test_completion_prompt_closes_and_merges_the_assigned_issue(self):
        prompt = auto.continuation_prompt(2, "20260825-capture", {
            "completion_gate": {
                "state": "close_and_merge",
            },
        })

        self.assertIn("SceneIssues/pending/20260825-capture", prompt)
        self.assertIn("SceneIssues/closed/20260825-capture", prompt)
        self.assertIn("push its exact head to `origin/master`", prompt)
        self.assertIn("do not wait for the coordinator", prompt)

    def test_queued_ci_is_not_nudged(self):
        info = {
            "last_prompted": 0,
            "prompt_count": 4,
            "completion_gate": {"state": "queued"},
        }

        self.assertFalse(auto.should_nudge(info, now=100000))

        active_info = {
            "last_prompted": 0,
            "prompt_count": 4,
            "ci_activity": {"state": "in_progress"},
        }
        self.assertFalse(auto.should_nudge(active_info, now=100000))

    def test_refresh_ci_activity_records_exact_head_run(self):
        registry = {"version": 1, "tasks": {"capture": {
            "status": "in_progress",
            "ci_branch": "ci-test/fixes/agent-1",
        }}}
        previous_runs = auto.github_active_single_test_runs
        previous_head = auto.branch_head
        auto.github_active_single_test_runs = lambda: {"abc123": {
            "state": "queued",
            "ci_head": "abc123",
            "run_id": 42,
            "run_url": "https://example.invalid/run/42",
            "run_created_at": "2026-08-26T12:00:00Z",
        }}
        auto.branch_head = lambda unused_branch: "abc123"
        self.addCleanup(setattr, auto, "github_active_single_test_runs", previous_runs)
        self.addCleanup(setattr, auto, "branch_head", previous_head)

        changed = auto.refresh_ci_activity(registry)

        self.assertTrue(changed)
        self.assertEqual("queued", registry["tasks"]["capture"]["ci_activity"]["state"])
        self.assertEqual(42, registry["tasks"]["capture"]["ci_activity"]["run_id"])

    def test_nudge_interval_backs_off_and_caps(self):
        self.assertEqual(auto.NUDGE_INTERVAL_SECONDS, auto.nudge_interval({}))
        self.assertEqual(auto.NUDGE_INTERVAL_SECONDS * 2,
                         auto.nudge_interval({"prompt_count": 2}))
        self.assertEqual(auto.MAX_NUDGE_INTERVAL_SECONDS,
                         auto.nudge_interval({"prompt_count": 20}))

    def test_input_box_immediately_continues_a_finished_response(self):
        info = {"status": "in_progress", "response_active": True}

        self.assertFalse(auto.response_became_idle(info, textbox_visible=False))
        self.assertTrue(info["response_active"])
        self.assertTrue(auto.response_became_idle(info, textbox_visible=True))
        self.assertNotIn("response_active", info)
        self.assertFalse(auto.response_became_idle(info, textbox_visible=True))

        already_idle_at_startup = {"status": "in_progress"}
        self.assertTrue(auto.response_became_idle(
            already_idle_at_startup, textbox_visible=True))
        self.assertFalse(auto.response_became_idle(
            already_idle_at_startup, textbox_visible=True))

    def test_legacy_unconfirmed_prompt_is_retried_immediately(self):
        info = {"status": "in_progress", "last_prompted": 99999, "prompt_count": 2}

        self.assertTrue(auto.should_nudge(info, now=100000))

        registry = {"tasks": {"capture": info}}
        auto.mark_prompted("capture", registry, now=100000)
        self.assertTrue(info["prompt_confirmed"])
        self.assertFalse(auto.should_nudge(info, now=100001))

    def test_completion_gates_remain_actionable(self):
        self.assertTrue(auto.should_nudge({
            "completion_gate": {"state": "close_and_merge"},
        }, now=100000))
        self.assertTrue(auto.should_nudge({
            "completion_gate": {"state": "merge_to_master"},
        }, now=100000))

    def test_registry_round_trip(self):
        directory = tempfile.mkdtemp(prefix="voxel-auto-registry-")
        self.addCleanup(shutil.rmtree, directory)
        path = os.path.join(directory, "registry.json")
        expected = {"version": 1, "tasks": {"capture": {"status": "fixed"}}}

        auto.save_registry(expected, path)

        self.assertEqual(expected, auto.load_registry(path))
        self.assertFalse(os.path.exists(path + ".tmp-%d" % os.getpid()))


class GitCompletionTests(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="voxel-auto-git-")
        self.addCleanup(shutil.rmtree, self.repo)
        self.previous_repo = auto.REPO_PATH
        auto.REPO_PATH = self.repo
        self.addCleanup(setattr, auto, "REPO_PATH", self.previous_repo)
        self.git("init", "-q")
        self.git("config", "user.name", "Auto Test")
        self.git("config", "user.email", "auto@example.invalid")
        self.issue_dir = os.path.join(
            self.repo, "SceneIssues", "open", "20260825-capture")
        os.makedirs(self.issue_dir)
        self.write_issue({"status": "open"})
        self.git("add", ".")
        self.git("commit", "-qm", "queue capture")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.git("update-ref", "refs/remotes/origin/master", self.base)

    def git(self, *arguments):
        output = subprocess.check_output(["git", "-C", self.repo] + list(arguments))
        return output.decode("utf-8")

    def write_issue(self, value):
        with open(os.path.join(self.issue_dir, "issue.json"), "w") as handle:
            json.dump(value, handle)

    def publish_pending_branch(self, fix_commit=None, add_verification=True):
        marker = os.path.join(self.repo, "production-fix.txt")
        with open(marker, "w") as handle:
            handle.write("fixed\n")
        self.git("add", marker)
        self.git("commit", "-qm", "production fix")
        actual_fix = self.git("rev-parse", "HEAD").strip()
        pending_dir = os.path.join(
            self.repo, "SceneIssues", "pending", "20260825-capture")
        os.makedirs(os.path.dirname(pending_dir), exist_ok=True)
        os.rename(self.issue_dir, pending_dir)
        self.issue_dir = pending_dir
        self.write_issue({
            "status": "pending",
            "resolutionSummary": "The fixture is fixed.",
            "regressionTest": "Example.Tests.CapturedViewIsFixed",
            "fixCommit": fix_commit or actual_fix,
        })
        if add_verification:
            with open(os.path.join(pending_dir, "verification-final.png"), "wb") as handle:
                handle.write(b"test image")
        self.git("add", "SceneIssues")
        self.git("commit", "-qm", "resolve capture")
        head = self.git("rev-parse", "HEAD").strip()
        self.git("update-ref", "refs/remotes/origin/fixes/agent-1", head)
        return actual_fix, head

    def close_issue_on_feature_branch(self, fix_commit):
        pending_dir = os.path.join(
            self.repo, "SceneIssues", "pending", "20260825-capture")
        closed_dir = os.path.join(
            self.repo, "SceneIssues", "closed", "20260825-capture")
        os.makedirs(os.path.dirname(closed_dir), exist_ok=True)
        os.rename(pending_dir, closed_dir)
        self.issue_dir = closed_dir
        self.write_issue({
            "status": "fixed",
            "resolvedUtc": "2026-08-25T13:00:00Z",
            "resolutionSummary": "The fixture is fixed.",
            "regressionTest": "Example.Tests.CapturedViewIsFixed",
            "fixCommit": fix_commit,
        })
        self.git("add", "SceneIssues")
        self.git("commit", "-qm", "complete capture")
        head = self.git("rev-parse", "HEAD").strip()
        self.git("update-ref", "refs/remotes/origin/fixes/agent-1", head)
        return head

    def publish_ci_branch(self, head):
        self.git("update-ref", "refs/remotes/origin/ci-test/fixes/agent-1", head)

    def promote_to_master(self, head):
        self.git("update-ref", "refs/remotes/origin/master", head)

    def mock_ci(self, status, run=None):
        previous_status = auto.github_status_context
        previous_run = auto.github_actions_run
        auto.github_status_context = lambda unused_sha, unused_context: status
        auto.github_actions_run = lambda unused_sha: run
        self.addCleanup(setattr, auto, "github_status_context", previous_status)
        self.addCleanup(setattr, auto, "github_actions_run", previous_run)

    def test_lists_only_open_issues_from_remote_master(self):
        self.assertEqual(["20260825-capture"], auto.list_open_tasks())

    def test_accepts_pending_issue_with_ancestor_fix_commit(self):
        fix_commit, head = self.publish_pending_branch()

        terminal = auto.pending_issue_state("20260825-capture", "fixes/agent-1")

        self.assertEqual("pending", terminal["status"])
        self.assertEqual(fix_commit, terminal["fix_commit"])
        self.assertEqual(head, terminal["branch_head"])

    def test_rejects_worker_branch_that_introduces_a_capture(self):
        extra_dir = os.path.join(self.repo, "SceneIssues", "open", "worker-created")
        os.makedirs(extra_dir)
        with open(os.path.join(extra_dir, "issue.json"), "w") as handle:
            json.dump({"status": "open"}, handle)
        self.git("add", extra_dir)
        self.git("commit", "-qm", "incorrectly add capture on worker branch")
        self.publish_pending_branch()

        introduced = auto.branch_introduced_issue_paths("fixes/agent-1")
        terminal = auto.pending_issue_state("20260825-capture", "fixes/agent-1")

        self.assertEqual(["SceneIssues/open/worker-created/issue.json"], introduced)
        self.assertIsNone(terminal)

    def test_rejects_feature_branch_ci_request_or_unrelated_capture_edits(self):
        other_dir = os.path.join(self.repo, "SceneIssues", "open", "other-capture")
        os.makedirs(other_dir)
        with open(os.path.join(other_dir, "issue.json"), "w") as handle:
            json.dump({"status": "open"}, handle)
        self.git("add", other_dir)
        self.git("commit", "-qm", "queue another capture")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.git("update-ref", "refs/remotes/origin/master", self.base)

        with open(os.path.join(other_dir, "plan.md"), "w") as handle:
            handle.write("unrelated edit\n")
        os.makedirs(os.path.join(self.repo, ".github"), exist_ok=True)
        with open(os.path.join(self.repo, ".github", "test-request.json"), "w") as handle:
            json.dump({"test": "wrong branch"}, handle)
        self.git("add", ".")
        self.git("commit", "-qm", "contaminate feature branch")
        self.publish_pending_branch()

        violations = auto.branch_policy_violations(
            "20260825-capture", "fixes/agent-1")
        terminal = auto.pending_issue_state("20260825-capture", "fixes/agent-1")

        self.assertIn(".github/test-request.json", violations)
        self.assertIn("SceneIssues/open/other-capture/plan.md", violations)
        self.assertIsNone(terminal)

    def test_rejects_pending_issue_without_final_verification_image(self):
        self.publish_pending_branch(add_verification=False)

        terminal = auto.pending_issue_state("20260825-capture", "fixes/agent-1")

        self.assertIsNone(terminal)

    def test_rejects_fixed_issue_with_unrelated_fix_commit(self):
        self.publish_pending_branch(fix_commit="0" * 40)

        terminal = auto.pending_issue_state("20260825-capture", "fixes/agent-1")

        self.assertIsNone(terminal)

    def test_rejects_pending_issue_that_was_not_moved_from_open(self):
        marker = os.path.join(self.repo, "production-fix.txt")
        with open(marker, "w") as handle:
            handle.write("fixed\n")
        self.git("add", marker)
        self.git("commit", "-qm", "production fix")
        fix_commit = self.git("rev-parse", "HEAD").strip()
        self.write_issue({
            "status": "pending",
            "resolutionSummary": "The fixture is fixed.",
            "regressionTest": "Example.Tests.CapturedViewIsFixed",
            "fixCommit": fix_commit,
        })
        self.git("add", os.path.join(self.issue_dir, "issue.json"))
        self.git("commit", "-qm", "incorrectly resolve without moving")
        head = self.git("rev-parse", "HEAD").strip()
        self.git("update-ref", "refs/remotes/origin/fixes/agent-1", head)

        terminal = auto.pending_issue_state("20260825-capture", "fixes/agent-1")

        self.assertIsNone(terminal)

    def test_blocked_issue_is_not_pending(self):
        pending_dir = os.path.join(
            self.repo, "SceneIssues", "pending", "20260825-capture")
        os.makedirs(os.path.dirname(pending_dir), exist_ok=True)
        os.rename(self.issue_dir, pending_dir)
        self.issue_dir = pending_dir
        self.write_issue({
            "status": "blocked",
            "resolutionSummary": "Waiting for external evidence.",
        })
        self.git("add", "SceneIssues")
        self.git("commit", "-qm", "incorrectly close blocked capture")
        head = self.git("rev-parse", "HEAD").strip()
        self.git("update-ref", "refs/remotes/origin/fixes/agent-1", head)

        terminal = auto.pending_issue_state("20260825-capture", "fixes/agent-1")

        self.assertIsNone(terminal)

    def test_reconcile_prompts_verified_pending_issue_to_close_and_merge(self):
        fix_commit, head = self.publish_pending_branch()
        self.publish_ci_branch(head)
        registry = {"version": 1, "tasks": {
            "20260825-capture": {
                "status": "in_progress",
                "owner": "agent-1",
                "branch": "fixes/agent-1",
                "ci_branch": "ci-test/fixes/agent-1",
            }
        }}

        self.mock_ci("success")

        changed = auto.reconcile_assignments(registry)

        self.assertTrue(changed)
        info = registry["tasks"]["20260825-capture"]
        self.assertEqual("in_progress", info["status"])
        self.assertEqual("close_and_merge", info["completion_gate"]["state"])
        self.assertEqual(fix_commit, info["completion_gate"]["fix_commit"])
        self.assertEqual(head, info["completion_gate"]["completion_commit"])
        self.assertEqual("20260825-capture", auto.get_agent_task("agent-1", registry))

    def test_reconcile_prompts_closed_feature_branch_to_merge_master(self):
        fix_commit, head = self.publish_pending_branch()
        self.publish_ci_branch(head)
        closed_head = self.close_issue_on_feature_branch(fix_commit)
        registry = {"version": 1, "tasks": {
            "20260825-capture": {
                "status": "in_progress",
                "owner": "agent-1",
                "branch": "fixes/agent-1",
                "ci_branch": "ci-test/fixes/agent-1",
            }
        }}
        self.mock_ci("success")

        changed = auto.reconcile_assignments(registry, now=200)

        self.assertTrue(changed)
        info = registry["tasks"]["20260825-capture"]
        self.assertEqual("in_progress", info["status"])
        self.assertEqual("merge_to_master", info["completion_gate"]["state"])
        self.assertEqual(closed_head, info["completion_gate"]["completion_commit"])

    def test_reconcile_marks_fixed_after_worker_merges_closed_branch(self):
        fix_commit, head = self.publish_pending_branch()
        self.publish_ci_branch(head)
        closed_head = self.close_issue_on_feature_branch(fix_commit)
        self.promote_to_master(closed_head)
        registry = {"version": 1, "tasks": {
            "20260825-capture": {
                "status": "in_progress",
                "owner": "agent-1",
                "branch": "fixes/agent-1",
                "ci_branch": "ci-test/fixes/agent-1",
            }
        }}
        self.mock_ci("success")

        changed = auto.reconcile_assignments(registry, now=300)

        self.assertTrue(changed)
        self.assertEqual("fixed", registry["tasks"]["20260825-capture"]["status"])
        self.assertEqual(300, registry["tasks"]["20260825-capture"]["completed_at"])

    def test_reconcile_waits_for_green_targeted_ci(self):
        unused_fix_commit, head = self.publish_pending_branch()
        self.publish_ci_branch(head)
        self.promote_to_master(head)
        registry = {"version": 1, "tasks": {
            "20260825-capture": {
                "status": "in_progress",
                "owner": "agent-1",
                "branch": "fixes/agent-1",
                "ci_branch": "ci-test/fixes/agent-1",
            }
        }}
        self.mock_ci(None, {
            "state": "queued",
            "run_id": 123,
            "run_url": "https://example.invalid/run/123",
            "run_created_at": "2026-08-25T12:00:00Z",
        })

        changed = auto.reconcile_assignments(registry)

        self.assertTrue(changed)
        self.assertEqual("in_progress", registry["tasks"]["20260825-capture"]["status"])
        gate = registry["tasks"]["20260825-capture"]["completion_gate"]
        self.assertEqual("queued", gate["state"])
        self.assertEqual(head, gate["ci_head"])
        self.assertEqual(123, gate["run_id"])

    def test_reconcile_green_fix_requests_close_and_merge(self):
        unused_fix_commit, head = self.publish_pending_branch()
        self.publish_ci_branch(head)
        registry = {"version": 1, "tasks": {
            "20260825-capture": {
                "status": "in_progress",
                "owner": "agent-1",
                "branch": "fixes/agent-1",
                "ci_branch": "ci-test/fixes/agent-1",
            }
        }}

        self.mock_ci("success")
        changed = auto.reconcile_assignments(registry, now=100)

        self.assertTrue(changed)
        info = registry["tasks"]["20260825-capture"]
        self.assertEqual("in_progress", info["status"])
        self.assertEqual("close_and_merge", info["completion_gate"]["state"])

    def test_reconcile_clears_stale_ci_gate_when_issue_is_not_terminal(self):
        registry = {"version": 1, "tasks": {
            "20260825-capture": {
                "status": "in_progress",
                "owner": "agent-1",
                "branch": "fixes/agent-1",
                "ci_branch": "ci-test/fixes/agent-1",
                "completion_gate": {"state": "failure"},
            }
        }}

        changed = auto.reconcile_assignments(registry)

        self.assertTrue(changed)
        self.assertNotIn("completion_gate", registry["tasks"]["20260825-capture"])


if __name__ == "__main__":
    unittest.main()
