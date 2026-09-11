# -*- coding: utf-8 -*-
"""Coordinator entrypoint. Workflow policy lives in the mounting-force-2 repository."""
from __future__ import print_function

import os
import sys
import traceback


TARGET_REPOSITORY = "jlashmet/mounting-force-2"
DEFAULT_TARGET_REPO_PATH = "/Users/jlashmet/code/mounting-force-2"


def _script_dir():
    """Locate sibling coordinator modules under CPython and Oculix/Jython."""
    configured = os.environ.get("AUTOMATION_DIR")
    if configured:
        return os.path.abspath(configured)
    file_name = globals().get("__file__")
    if file_name:
        return os.path.dirname(os.path.abspath(file_name))
    if sys.argv and sys.argv[0]:
        candidate = os.path.abspath(str(sys.argv[0]))
        if os.path.isfile(candidate):
            return os.path.dirname(candidate)
    get_bundle_path = globals().get("getBundlePath")
    if get_bundle_path:
        bundle_path = getBundlePath()
        if bundle_path:
            return os.path.abspath(str(bundle_path))
    return os.getcwd()


def _fatal_startup(message):
    text = "Automation startup failed: %s" % message
    try:
        sys.stderr.write(text + "\n")
        traceback.print_exc()
    except Exception:
        pass
    popup = globals().get("popup")
    if popup:
        try:
            popup(text)
        except Exception:
            pass


_LOCAL_SCRIPT_DIR = _script_dir()
_set_bundle_path = globals().get("setBundlePath")
if _set_bundle_path:
    try:
        _set_bundle_path(_LOCAL_SCRIPT_DIR)
    except Exception:
        pass

try:
    _IMPL_PATH = os.path.join(_LOCAL_SCRIPT_DIR, "auto_runtime.py")
    _ENTRY_NAME = globals().get("__name__", "__main__")
    globals()["__name__"] = "scene_issue_auto_runtime"
    with open(_IMPL_PATH, "rb") as _impl_handle:
        _impl_code = compile(_impl_handle.read(), _IMPL_PATH, "exec")
    eval(_impl_code, globals(), globals())
    globals()["__name__"] = _ENTRY_NAME
    SCRIPT_DIR = _LOCAL_SCRIPT_DIR
except Exception as _startup_error:
    globals()["__name__"] = globals().get("_ENTRY_NAME", "__main__")
    _fatal_startup(_startup_error)
    raise


REPO_PATH = os.path.abspath(os.environ.get("MOUNTING_FORCE_REPO_PATH", DEFAULT_TARGET_REPO_PATH))
GITHUB_REPOSITORY = TARGET_REPOSITORY
SCENE_ISSUES_PATH = os.path.join(REPO_PATH, "SceneIssues")
OPEN_SCENE_ISSUES_PATH = os.path.join(SCENE_ISSUES_PATH, "open")
PENDING_SCENE_ISSUES_PATH = os.path.join(SCENE_ISSUES_PATH, "pending")
ASSIGNMENT_BRANCH = os.environ.get("MOUNTING_FORCE_ASSIGNMENT_BRANCH", "automation/assignments")
ASSIGNMENT_REF = "refs/remotes/%s/%s" % (REMOTE, ASSIGNMENT_BRANCH)
ASSIGNMENT_REMOTE_REF = "refs/heads/%s" % ASSIGNMENT_BRANCH
REGISTRY_PATH = "SceneIssue issue.json on origin/%s" % ASSIGNMENT_BRANCH


def ensure_target_repository():
    """Refuse to coordinate against any checkout other than mounting-force-2."""
    if not os.path.isdir(REPO_PATH):
        raise RuntimeError("Mounting Force checkout does not exist: %s" % REPO_PATH)
    code, stdout, stderr = run_git(["remote", "get-url", REMOTE], check=False)
    if code != 0:
        raise RuntimeError("cannot read %s remote in %s: %s" % (
            REMOTE, REPO_PATH, stderr.strip() or "git remote failed"))
    normalized = stdout.strip().lower().replace("\\", "/").replace(":", "/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    if TARGET_REPOSITORY.lower() not in normalized:
        raise RuntimeError(
            "refusing to run: %s remote is %s, expected %s" %
            (REPO_PATH, stdout.strip() or "<missing>", TARGET_REPOSITORY))


_core_should_nudge = should_nudge


def should_nudge(info, now=None):
    if info.get("prompt_confirmed") is False:
        return True
    return _core_should_nudge(info, now=now)


def _master_workflow_text():
    return (
        "Use the Chat on Steroids plugin for all repository interaction: reading and editing code/files, "
        "running shell commands, and running tests. Chat on Steroids can fail intermittently or temporarily "
        "report that the plugin is unavailable, disabled, or conflicted; treat these as transient failures and "
        "keep retrying the same operation rather than abandoning the tool or switching workflows. Work directly "
        "on `master`; do not create, checkout, or use a separate agent, feature, fixes, CI, or transport branch. "
        "Before editing, make sure the working tree is on `master` and pull/reconcile current `origin/master` "
        "without discarding another agent's valid work. Periodically pull from `origin/master` while working so "
        "you stay current with other agents, and resolve any conflicts carefully, preserving valid changes from "
        "both sides. Keep changes scoped to the assigned SceneIssue. Run the relevant tests through Chat on "
        "Steroids and resolve failures caused by your work. When the assignment is genuinely complete, commit "
        "the completed work on `master` and push it to `origin/master` non-force; immediately before pushing, "
        "pull/reconcile `origin/master` again, resolve any conflicts, rerun affected tests when reconciliation "
        "changes code, then retry the push if master advances again."
    )


def task_prompt(number, task_id, work_kind=None):
    """Supply assignment identity plus the master-only Chat on Steroids workflow."""
    work_kind = work_kind or scene_work_kind(task_id)
    guide = workflow_path(work_kind)
    open_path = "SceneIssues/open/%s" % task_id
    closed_path = "SceneIssues/closed/%s" % task_id

    if work_kind == FEATURE_WORK_KIND:
        detail = (
            "This is a feature assignment: keep separate `plan.md` and `tasks.md`; work the next "
            "unchecked non-blocked task; add discovered required work only for acceptance, "
            "correctness/regression, reuse boundaries, or demonstrated quality defects; no "
            "opportunistic enhancements. Keep reusable APIs semantic/config-driven and do not "
            "refactor adjacent systems unless acceptance or a demonstrated defect requires it."
        )
    else:
        detail = (
            "For issue work, discriminate competing hypotheses with evidence, add a behavioral "
            "regression, validate the runtime/scene when player-visible, and isolate a minimal "
            "repro/root cause before a third materially different fix for the same failing symptom."
        )

    return (
        "You are %s. Work only on `%s` in `jlashmet/mounting-force-2`. Follow `AGENTS.md`, "
        "`SceneIssues/README.md`, and `%s`; those repo docs are authoritative unless they conflict with "
        "this explicit execution policy: %s %s Keep blocked or incomplete work in open; do not use "
        "`SceneIssues/pending`. Only after all required acceptance work is genuinely complete, close to `%s`, "
        "set the required fixed metadata, commit on `master`, and push to `origin/master` non-force. Do not "
        "self-select more work."
        % (agent_id(number), open_path, guide, _master_workflow_text(), detail, closed_path))


def continuation_prompt(number, task_id, info=None):
    work_kind = (info or {}).get("work_kind") or scene_work_kind(task_id)
    guide = workflow_path(work_kind)
    open_path = "SceneIssues/open/%s" % task_id
    closed_path = "SceneIssues/closed/%s" % task_id

    feature_check = (
        "Keep `plan.md`/`tasks.md` current, work the next unchecked non-blocked item, and do not close "
        "with any required task unchecked. "
        if work_kind == FEATURE_WORK_KIND else
        "Work the next non-blocked acceptance item and keep the issue open until verified. "
    )
    return (
        "Continue only `%s` in `jlashmet/mounting-force-2`. Follow `AGENTS.md`, `SceneIssues/README.md`, "
        "and `%s`. %s%s Record blockers and continue independent work where possible; do not change "
        "acceptance or self-select another SceneIssue. When all acceptance work is complete, close to `%s`, "
        "set the required fixed metadata, commit directly on `master`, and push to `origin/master` non-force."
        % (open_path, guide, _master_workflow_text(), feature_check, closed_path))


def branch_cleanup_prompt(number, head=None):
    return (
        "Do not continue work on an old agent/feature branch%s. Use the Chat on Steroids plugin, switch to "
        "current `master`, reconcile any valid unfinished assignment work without discarding unrelated work, "
        "periodically pull `origin/master` and resolve conflicts while working, finish and test only the "
        "assigned SceneIssue, then pull/reconcile once more, commit on `master`, and push to `origin/master` "
        "non-force. Do not start another SceneIssue."
        % ((" at `%s`" % head) if head else ""))


if globals().get("__name__") == "__main__":
    try:
        ensure_target_repository()
        if "--check" in sys.argv:
            check_only()
        else:
            coordinator_loop()
    except Exception as _run_error:
        _fatal_startup(_run_error)
        raise
