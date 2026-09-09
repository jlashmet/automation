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
    # Prefer the launched script path over Oculix's bundle path. The bundle path may
    # point at a shared volume even when run.sh and the image assets are local.
    if sys.argv and sys.argv[0]:
        candidate = os.path.abspath(str(sys.argv[0]))
        if os.path.isfile(candidate):
            return os.path.dirname(candidate)
    get_bundle_path = globals().get("getBundlePath")
    if get_bundle_path:
        bundle_path = get_bundle_path()
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


# Pin Sikuli/Oculix image lookup to the local automation checkout before loading the
# runtime. This keeps textbox.png, submit.png, in_progress_glyph.png, etc. local even
# when Oculix has a shared-volume bundle path configured.
_LOCAL_SCRIPT_DIR = _script_dir()
_set_bundle_path = globals().get("setBundlePath")
if _set_bundle_path:
    try:
        _set_bundle_path(_LOCAL_SCRIPT_DIR)
    except Exception:
        pass

# Keep coordinator/state implementation separate from prompt policy. The implementation
# still loads auto_core.py and provides durable repository-backed assignment state.
try:
    _IMPL_PATH = os.path.join(_LOCAL_SCRIPT_DIR, "auto_runtime.py")
    _ENTRY_NAME = globals().get("__name__", "__main__")
    globals()["__name__"] = "scene_issue_auto_runtime"
    with open(_IMPL_PATH, "rb") as _impl_handle:
        _impl_code = compile(_impl_handle.read(), _IMPL_PATH, "exec")
    eval(_impl_code, globals(), globals())
    globals()["__name__"] = _ENTRY_NAME
    # auto_core's image helpers join against SCRIPT_DIR. Override any bundle-derived
    # value after bootstrap so all image reads stay in the local checkout.
    SCRIPT_DIR = _LOCAL_SCRIPT_DIR
except Exception as _startup_error:
    globals()["__name__"] = globals().get("_ENTRY_NAME", "__main__")
    _fatal_startup(_startup_error)
    raise


# Hard cutover: this coordinator has one target. Rebind all repository-sensitive globals
# after the reusable runtime is loaded. The legacy defaults inside auto_core/auto_runtime
# are never used by a live auto.py run.
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


# A queued/running CI request must suppress routine nudges, but it must never suppress
# delivery of the assignment itself. In particular, a transient image-match or submit
# failure can leave prompt_confirmed=False while CI becomes active; the core policy would
# otherwise visit the tab indefinitely without retrying the missing prompt.
_core_should_nudge = should_nudge


def should_nudge(info, now=None):
    if info.get("prompt_confirmed") is False:
        return True
    return _core_should_nudge(info, now=now)


def task_prompt(number, task_id, work_kind=None):
    """Supply assignment identity plus a short pointer to authoritative repo policy."""
    work_kind = work_kind or scene_work_kind(task_id)
    guide = workflow_path(work_kind)
    branch_name = feature_branch(number)
    ci_branch_name = ci_branch(number)
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
        "You are %s. Work only on `%s` in `jlashmet/mounting-force-2` on `%s`; `%s` is your only "
        "targeted-CI transport. Fetch origin, then follow `AGENTS.md`, `SceneIssues/README.md`, and "
        "`%s`; those repo docs are authoritative. %s Never replace queued/running CI. Use exact-SHA "
        "CI as documented. Keep blocked or incomplete work in open; do not use `SceneIssues/pending`. "
        "After green exact-SHA validation and completed acceptance, close to `%s`, set the required "
        "fixed metadata, merge current `origin/master`, and push the exact feature head to "
        "`origin/master` non-force. Do not self-select more work."
        % (agent_id(number), open_path, branch_name, ci_branch_name, guide, detail, closed_path))


def continuation_prompt(number, task_id, info=None):
    work_kind = (info or {}).get("work_kind") or scene_work_kind(task_id)
    guide = workflow_path(work_kind)
    gate = (info or {}).get("completion_gate") or {}
    state = gate.get("state")
    ci_branch_name = gate.get("ci_branch") or ci_branch(number)
    ci_head = gate.get("ci_head") or "<missing>"
    fix_commit = gate.get("fix_commit") or "<missing>"
    open_path = "SceneIssues/open/%s" % task_id
    closed_path = "SceneIssues/closed/%s" % task_id

    if state in ("close_and_merge", "merge_to_master"):
        feature_check = (
            "First confirm every `tasks.md` checkbox and acceptance criterion. "
            if work_kind == FEATURE_WORK_KIND else "")
        return (
            "%s is verified. %sClose `%s` to `%s` if needed, set status=`fixed`, `resolvedUtc`, "
            "`resolutionSummary`, `regressionTest`, and `fixCommit`, then fetch/merge current "
            "`origin/master` and push the exact `%s` head to `origin/master` non-force. If master "
            "advanced, merge/retry."
            % (task_id, feature_check, open_path, closed_path, feature_branch(number)))
    if state == "missing_branch":
        return (
            "%s: `%s` is missing. Create the next exact-SHA request from the source containing "
            "fixCommit %s and monitor `ci/single-test`." % (task_id, ci_branch_name, fix_commit))
    if state == "missing_fix":
        return (
            "%s: `%s` at %s lacks fixCommit %s. Create a fresh request on that same transport from "
            "the correct source and monitor it." % (task_id, ci_branch_name, ci_head, fix_commit))
    if state == "not_created":
        return (
            "%s: no exact-SHA `Tests (single)` run exists for `%s` at %s. Leave active CI alone; "
            "after the documented admission window, update only the assigned CI ref."
            % (task_id, ci_branch_name, ci_head))
    if state in ("queued", "in_progress", "waiting", "requested", "pending"):
        return "%s: `%s` at %s is %s. Monitor it without replacement." % (
            task_id, ci_branch_name, ci_head, state)
    if state in ("failure", "error", "cancelled", "timed_out", "action_required"):
        return (
            "%s: `%s` at %s reported validation=%s. Inspect evidence; fix product failures or retry "
            "only proven infrastructure failure, then reuse this same CI transport. Never replace "
            "active CI."
            % (task_id, ci_branch_name, ci_head, state))

    extra = (
        " Keep `plan.md`/`tasks.md` current, work the next unchecked non-blocked item, and do not "
        "close with any required task unchecked."
        if work_kind == FEATURE_WORK_KIND else
        " Work the next non-blocked acceptance item and keep the issue open until verified.")
    return (
        "Continue only `%s` in `jlashmet/mounting-force-2` on `%s`. Follow `AGENTS.md`, "
        "`SceneIssues/README.md`, and `%s`.%s Record blockers and continue independent work where "
        "possible; do not change acceptance or self-select another SceneIssue."
        % (open_path, feature_branch(number), guide, extra))


def branch_cleanup_prompt(number, head=None):
    branch_name = feature_branch(number)
    return (
        "%s still has prior-assignment work not on current Mounting Force master%s. Reconcile only "
        "that work against current master and follow `AGENTS.md` plus `SceneIssues/README.md`. If "
        "valid work remains, finish/validate it and use the normal non-force master promotion path; "
        "do not start another SceneIssue."
        % (branch_name, (" at `%s`" % head) if head else ""))


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
