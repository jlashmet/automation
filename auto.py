"""Coordinator entrypoint. Workflow policy lives in the voxel repository."""
from __future__ import print_function

import os
import sys


def _script_dir():
    file_name = globals().get("__file__")
    if file_name:
        return os.path.dirname(os.path.abspath(file_name))
    get_bundle_path = globals().get("getBundlePath")
    if get_bundle_path:
        bundle_path = get_bundle_path()
        if bundle_path:
            return os.path.abspath(str(bundle_path))
    return os.getcwd()


# Keep coordinator/state implementation separate from prompt policy. The implementation
# still loads auto_core.py and provides durable repository-backed assignment state.
_IMPL_PATH = os.path.join(_script_dir(), "auto_runtime.py")
_ENTRY_NAME = globals().get("__name__", "__main__")
globals()["__name__"] = "scene_issue_auto_runtime"
with open(_IMPL_PATH, "rb") as _impl_handle:
    _impl_code = compile(_impl_handle.read(), _IMPL_PATH, "exec")
eval(_impl_code, globals(), globals())
globals()["__name__"] = _ENTRY_NAME


def task_prompt(number, task_id, work_kind=None):
    """Supply identity/state only; the voxel repo owns workflow instructions."""
    work_kind = work_kind or scene_work_kind(task_id)
    return (
        "You are %s. Work only on `%s` on `%s`; `%s` is your targeted-CI transport. "
        "Fetch origin, then read and follow `AGENTS.md`, `SceneIssues/README.md`, and `%s`; "
        "those repo documents are authoritative. Do not self-select or modify another assignment."
        % (agent_id(number), task_id, feature_branch(number), ci_branch(number),
           workflow_path(work_kind)))


def continuation_prompt(number, task_id, info=None):
    gate = (info or {}).get("completion_gate") or {}
    state = gate.get("state")
    ci_branch_name = gate.get("ci_branch") or ci_branch(number)
    ci_head = gate.get("ci_head") or "<missing>"

    if state in ("close_and_merge", "merge_to_master"):
        return (
            "%s is verified. Follow `SceneIssues/README.md` completion: close it on `%s` if needed, "
            "sync current master, push the branch, open/update its PR to `master`, enable auto-merge, "
            "and monitor the required PR gate until it merges."
            % (task_id, feature_branch(number)))
    if state in ("queued", "in_progress", "waiting", "requested", "pending"):
        return "%s: `%s` at %s is %s. Monitor it without replacement." % (
            task_id, ci_branch_name, ci_head, state)
    if state in ("failure", "error", "cancelled", "timed_out", "action_required"):
        return (
            "%s: `%s` at %s is %s. Follow the repo CI rules: inspect evidence, fix the cause or "
            "retry only proven infrastructure failure on the same transport."
            % (task_id, ci_branch_name, ci_head, state))
    return (
        "Continue only `%s` on `%s`. Read `AGENTS.md`, `SceneIssues/README.md`, and `%s`, then work "
        "the next non-blocked acceptance item."
        % (task_id, feature_branch(number),
           workflow_path((info or {}).get("work_kind") or scene_work_kind(task_id))))


def branch_cleanup_prompt(number, head=None):
    branch_name = feature_branch(number)
    return (
        "%s still has prior-assignment work not on current master%s. Reconcile only that work against "
        "current master and follow `AGENTS.md` plus `SceneIssues/README.md`. If valid work remains, "
        "finish/validate it and use the normal PR + auto-merge path; do not start another SceneIssue."
        % (branch_name, (" at `%s`" % head) if head else ""))


if globals().get("__name__") == "__main__":
    if "--check" in sys.argv:
        check_only()
    else:
        coordinator_loop()
