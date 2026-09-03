# -*- coding: utf-8 -*-
"""Coordinator entrypoint. Workflow policy lives in the voxel repository."""
from __future__ import print_function

import os
import sys
import traceback


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


def task_prompt(number, task_id, work_kind=None):
    """Supply assignment identity plus a short pointer to authoritative repo policy."""
    work_kind = work_kind or scene_work_kind(task_id)
    guide = workflow_path(work_kind)
    branch_name = feature_branch(number)
    ci_branch_name = ci_branch(number)
    open_path = "SceneIssues/open/%s" % task_id
    closed_path = "SceneIssues/closed/%s" % task_id
    legacy_pending = "SceneIssues/pending/%s" % task_id

    if work_kind == FEATURE_WORK_KIND:
        detail = (
            "This is a feature assignment: keep separate `plan.md` and `tasks.md`; add discovered "
            "required work only as the repo guide permits, and complete every checkbox and acceptance "
            "criterion before closure."
        )
    else:
        detail = (
            "For issue work, the repo guide owns competing hypotheses, behavioral regression, and "
            "built-scene evidence."
        )

    return (
        "You are %s. Work only on `%s` on `%s`; `%s` is your targeted-CI transport. Fetch origin, "
        "then follow `AGENTS.md`, `SceneIssues/README.md`, and `%s`; those repo docs are authoritative. "
        "%s Use exact-SHA CI as required. Close to `%s`; `%s` is legacy and must not be used. Do not "
        "push that exact branch head to `origin/master`; final promotion is PR + auto-merge."
        % (agent_id(number), open_path, branch_name, ci_branch_name, guide, detail,
           closed_path, legacy_pending))


def continuation_prompt(number, task_id, info=None):
    work_kind = (info or {}).get("work_kind") or scene_work_kind(task_id)
    guide = workflow_path(work_kind)
    gate = (info or {}).get("completion_gate") or {}
    state = gate.get("state")
    ci_branch_name = gate.get("ci_branch") or ci_branch(number)
    ci_head = gate.get("ci_head") or "<missing>"
    open_path = "SceneIssues/open/%s" % task_id
    closed_path = "SceneIssues/closed/%s" % task_id
    legacy_pending = "SceneIssues/pending/%s" % task_id

    if state in ("close_and_merge", "merge_to_master"):
        feature_check = (
            "First confirm every `tasks.md` checkbox and acceptance criterion; the old phrase "
            "`keep the feature open or pending` is obsolete - keep it open until complete. "
            if work_kind == FEATURE_WORK_KIND else "")
        return (
            "%s is verified. %sDo not use `%s`; close to `%s` if needed. Follow "
            "`SceneIssues/README.md`: sync `origin/master`, push `%s`, open/update its PR to master, "
            "enable auto-merge, and monitor required PR checks until merged; do not wait for the "
            "coordinator. Do not push its exact head to `origin/master`."
            % (task_id, feature_check, legacy_pending, closed_path, feature_branch(number)))
    if state in ("queued", "in_progress", "waiting", "requested", "pending"):
        return "%s: `%s` at %s is %s. Monitor it without replacement." % (
            task_id, ci_branch_name, ci_head, state)
    if state in ("failure", "error", "cancelled", "timed_out", "action_required"):
        return (
            "%s: `%s` at %s reported `ci/single-test=%s`. Follow the repo CI rules: inspect evidence; "
            "for infrastructure failure, retry only as allowed and update the assigned CI ref once; "
            "for product failure, fix the cause."
            % (task_id, ci_branch_name, ci_head, state))

    extra = (
        " Keep `plan.md`/`tasks.md` current and do not close with any unchecked task."
        if work_kind == FEATURE_WORK_KIND else "")
    return (
        "Continue only `%s` on `%s`. Follow `AGENTS.md`, `SceneIssues/README.md`, and `%s`; work the "
        "next non-blocked acceptance item.%s"
        % (open_path, feature_branch(number), guide, extra))


def branch_cleanup_prompt(number, head=None):
    branch_name = feature_branch(number)
    return (
        "%s still has prior-assignment work not on current master%s. Reconcile only that work against "
        "current master and follow `AGENTS.md` plus `SceneIssues/README.md`. If valid work remains, "
        "finish/validate it and use the normal PR + auto-merge path; do not start another SceneIssue."
        % (branch_name, (" at `%s`" % head) if head else ""))


if globals().get("__name__") == "__main__":
    try:
        if "--check" in sys.argv:
            check_only()
        else:
            coordinator_loop()
    except Exception as _run_error:
        _fatal_startup(_run_error)
        raise
