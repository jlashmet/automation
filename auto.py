# -*- coding: utf-8 -*-
"""Coordinator entrypoint for the Unreal Mounting Force SceneIssue queue."""
from __future__ import print_function

import os
import sys
import traceback


TARGET_REPOSITORY = "jlashmet/mounting-force-unreal"
DEFAULT_TARGET_REPO_PATH = "/Users/jlashmet/Documents/Unreal Projects/MountingForce"


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
QUEUE_REF = "origin/main"
SCENE_ISSUES_PATH = os.path.join(REPO_PATH, "SceneIssues")
OPEN_SCENE_ISSUES_PATH = os.path.join(SCENE_ISSUES_PATH, "open")
ISSUE_WORKFLOW_PATH = "SceneIssues/README.md"
FEATURE_WORKFLOW_PATH = "SceneIssues/README.md"
ASSIGNMENT_BRANCH = os.environ.get("MOUNTING_FORCE_ASSIGNMENT_BRANCH", "automation/assignments")
ASSIGNMENT_REF = "refs/remotes/%s/%s" % (REMOTE, ASSIGNMENT_BRANCH)
ASSIGNMENT_REMOTE_REF = "refs/heads/%s" % ASSIGNMENT_BRANCH
REGISTRY_PATH = "SceneIssue issue.json on origin/%s" % ASSIGNMENT_BRANCH


def ensure_target_repository():
    """Refuse to coordinate against any checkout other than mounting-force-unreal."""
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
_core_mark_tab_refresh = mark_tab_refresh


def should_nudge(info, now=None):
    if info.get("prompt_confirmed") is False:
        return True
    return _core_should_nudge(info, now=now)


def mark_tab_refresh(number, registry, now=None):
    """After a browser reload, require the full assignment prompt again."""
    _core_mark_tab_refresh(number, registry, now=now)
    task_id = get_agent_task(agent_id(number), registry)
    if not task_id:
        return
    info = registry.get("tasks", {}).get(task_id)
    if not info or info.get("status") != "in_progress":
        return
    # The tab may have lost conversation state during the reload. Make the next
    # idle send establish identity/assignment again instead of sending only continue.
    info["last_prompted"] = 0
    info["prompt_confirmed"] = False


def _master_workflow_text():
    return (
        "Use the Chat on Steroids plugin for all repository interaction: reading and editing code/files, "
        "running shell commands, and running tests. Chat on Steroids can fail intermittently or temporarily "
        "report that the plugin is unavailable, disabled, or conflicted; treat these as transient failures and "
        "keep retrying the same operation rather than abandoning the tool or switching workflows. Work only "
        "inside the assigned `.worktrees/<SceneIssue-directory-name>` checkout. SceneIssue worktrees are "
        "intentionally detached from current `origin/main`; do not create or use a persistent agent, feature, "
        "fixes, CI, or transport branch for implementation. Before editing, fetch and reconcile the worktree "
        "with current `origin/main` without discarding another agent's valid work. Periodically fetch/rebase "
        "or otherwise reconcile **from** current `origin/main` inside the isolated worktree so you stay current "
        "with other agents; this is not permission to publish your partial feature to main. Never merge, push, "
        "cherry-pick, or otherwise promote incomplete feature work to `origin/main` after an individual task, "
        "milestone, checkpoint, or partial test pass. "
        "Human/manual testing is never required: if the assigned issue contains manual/human-only validation, "
        "replace it with agent-executable automated/native validation through the same production controls and "
        "authorities, update the issue plan/tasks accordingly, and never wait for the user to test or approve. "
        "Keep changes scoped to the assigned SceneIssue. Run the relevant Unreal tests/checks through Chat on "
        "Steroids and resolve failures caused by your work. Do not modify or clean the primary checkout; it may "
        "contain unrelated user work. Only when the **entire SceneIssue feature** is complete, every required "
        "acceptance criterion is satisfied, all required focused/runtime tests and the repository gate are green, "
        "and final self-review is complete may you promote the feature to `origin/main`. Immediately before that "
        "single final promotion, fetch and reconcile the SceneIssue worktree with current `origin/main`; if that "
        "reconciliation changes code/content, rerun affected validation, then push the verified detached worktree "
        "HEAD to `origin/main` non-force. If `origin/main` advances, reconcile, revalidate affected work, and retry. "
        "Never force-push and never discard valid concurrent work."
    )


def task_prompt(number, task_id, work_kind=None, role=None):
    """Supply assignment identity plus the isolated Unreal worktree workflow."""
    work_kind = work_kind or scene_work_kind(task_id)
    role = role or task_role(task_id)
    if role == "reviewer":
        return review_prompt(number, task_id, work_kind)
    guide = workflow_path(work_kind)
    open_path = "SceneIssues/open/%s" % task_id
    review_path = "SceneIssues/pending/%s" % task_id

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
        "You are %s. Work only on `%s` in `jlashmet/mounting-force-unreal`. Follow `CLAUDE.md` and "
        "`SceneIssues/README.md`; those repo docs are authoritative unless they conflict with "
        "this explicit execution policy: %s %s Keep blocked or incomplete work in open. Read any prior `review.md` feedback and address every required change. Do not publish anything to `origin/main` while any feature task, acceptance criterion, required test, or gate is incomplete. Only after all required acceptance work is genuinely complete, tested, gated, and you have self-reviewed the final work, move to `%s` for independent review; never close your own implementation. "
        "Set status=`pending`, record implementer identity, candidate commit, validation and self-review evidence in `review.md`, remove any stale resolvedUtc, commit in the assigned SceneIssue worktree, and push the reconciled worktree HEAD to `origin/main` non-force. Do not "
        "self-select more work. %s"
        % (agent_id(number), open_path, _master_workflow_text(), detail, review_path,
           handoff_instructions(task_id)))


def review_prompt(number, task_id, work_kind):
    return (
        "You are %s, the reviewer for `SceneIssues/pending/%s` in `jlashmet/mounting-force-unreal`. "
        "Follow `CLAUDE.md` and `SceneIssues/README.md`. %s "
        "Independently inspect the implementation diff, surrounding code, every acceptance criterion, "
        "required tasks, validation results and current player-visible evidence. Verify the candidate "
        "on current origin/main and run focused checks needed to support your decision. "
        "Read and preserve review.md history. Record reviewer identity, reviewed commit, checks, evidence, "
        "and an explicit decision in review.md. Either accept and move the entire assigned folder to "
        "`SceneIssues/closed/%s`, setting status=fixed and resolvedUtc plus required resolution metadata, "
        "or reject with detailed actionable feedback (file/criterion, defect, evidence, required change, "
        "and validation expected), uncheck unmet tasks, and move it to `SceneIssues/open/%s` with "
        "status=open and no resolvedUtc. Do not implement the requested fixes during review. "
        "Commit and promote the decision to origin/main non-force. Do not self-select more work. %s"
        % (agent_id(number), task_id, _master_workflow_text(),
           task_id, task_id, handoff_instructions(task_id)))


def continuation_prompt(number, task_id, info=None):
    work_kind = (info or {}).get("work_kind") or scene_work_kind(task_id)
    if (info or {}).get("role", task_role(task_id)) == "reviewer":
        return review_prompt(number, task_id, work_kind)
    guide = workflow_path(work_kind)
    open_path = "SceneIssues/open/%s" % task_id
    review_path = "SceneIssues/pending/%s" % task_id

    feature_check = (
        "Keep `plan.md`/`tasks.md` current, work the next unchecked non-blocked item, and do not close "
        "with any required task unchecked. "
        if work_kind == FEATURE_WORK_KIND else
        "Work the next non-blocked acceptance item and keep the issue open until verified. "
    )
    return (
        "Continue only `%s` in `jlashmet/mounting-force-unreal`. Follow `CLAUDE.md` and `SceneIssues/README.md`. "
        "%s%s Record blockers and continue independent work where possible; do not change "
        "acceptance or self-select another SceneIssue. Do not publish partial work to `origin/main`. When the entire SceneIssue is complete, all required tests/gates are green, and your final self-review is complete, move to `%s` for independent review; never close your own implementation, "
        "Set status=`pending`, record implementer identity, candidate commit, validation and self-review evidence in `review.md`, remove any stale resolvedUtc, commit in the assigned SceneIssue worktree, and push the reconciled worktree HEAD to `origin/main` non-force. %s"
        % (open_path, _master_workflow_text(), feature_check, review_path,
           handoff_instructions(task_id)))


def message_for_nudge(number, task_id, info, started_new_chat=False):
    """Send the full assignment only on first contact/reload; otherwise just continue."""
    if not started_new_chat:
        if not float(info.get("last_prompted") or 0):
            return task_prompt(number, task_id, info.get("work_kind"), info.get("role"))
        return "continue"

    # A new/reloaded conversation always gets the complete assignment identity and
    # execution policy first. Recovery context is supplementary, never a replacement.
    parts = [task_prompt(number, task_id, info.get("work_kind"), info.get("role"))]
    handoff = _fresh_chat_handoff_context(task_id)
    if handoff:
        parts.append(handoff)

    activity = info.get("ci_activity") or {}
    active_states = ("queued", "in_progress", "waiting", "requested", "pending")
    if info.get("completion_gate"):
        parts.append("CURRENT COORDINATOR STATE:\n%s" % continuation_prompt(number, task_id, info))
    elif activity.get("state") in active_states:
        parts.append(
            "CURRENT COORDINATOR STATE:\nContinue only scene assignment %s. Its exact "
            "targeted-CI request `%s` is `%s`; monitor it without replacing it, then complete your assigned role and promote its decision." % (
                task_id, activity.get("ci_head") or "<unknown>", activity.get("state")))
    return "\n\n".join(parts)


def branch_cleanup_prompt(number, head=None):
    return (
        "Legacy branch state was detected%s. Do not resume or create a `fixes/agent-N` implementation branch. "
        "Use the assigned `.worktrees/<SceneIssue-directory-name>` checkout based on current `origin/main`; "
        "preserve any valid in-scope legacy work by reconciling it deliberately, then continue in the SceneIssue "
        "worktree and push the verified detached worktree HEAD to `origin/main` non-force without modifying the primary checkout."
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
