"""Coordinator entrypoint plus prompt policy overrides.

The stable coordinator implementation is loaded from ``auto_core.py`` into this
module's namespace so existing imports, tests, and monkeypatches keep working.
"""
from __future__ import print_function

import os
import sys


def _bootstrap_script_dir():
    """Locate adjacent files under CPython and Oculix/SikuliX/Jython."""
    file_name = globals().get("__file__")
    if file_name:
        return os.path.dirname(os.path.abspath(file_name))
    get_bundle_path = globals().get("getBundlePath")
    if get_bundle_path:
        bundle_path = get_bundle_path()
        if bundle_path:
            return os.path.abspath(str(bundle_path))
    if sys.argv and sys.argv[0]:
        candidate = os.path.abspath(str(sys.argv[0]))
        if os.path.isfile(candidate):
            return os.path.dirname(candidate)
    return os.getcwd()


_CORE_PATH = os.path.join(_bootstrap_script_dir(), "auto_core.py")
_ENTRY_NAME = globals().get("__name__", "__main__")
globals()["__name__"] = "scene_issue_auto_core"
with open(_CORE_PATH, "rb") as _core_handle:
    _core_code = compile(_core_handle.read(), _CORE_PATH, "exec")
eval(_core_code, globals(), globals())
globals()["__name__"] = _ENTRY_NAME


def task_prompt(number, task_id, work_kind=None):
    name = agent_id(number)
    branch_name = feature_branch(number)
    ci_branch_name = ci_branch(number)
    work_kind = work_kind or scene_work_kind(task_id)
    guide = workflow_path(work_kind)
    if work_kind == FEATURE_WORK_KIND:
        directions = (
            "Follow `%s` plus common `SceneIssues/README.md` rules. Before implementation, create "
            "and maintain separate `plan.md` and `tasks.md` files in the assigned folder. Add "
            "discovered required work to `tasks.md` only when required by acceptance, "
            "correctness/regression, reuse boundaries, or a demonstrated quality defect; do not add "
            "opportunistic enhancements. Work the next unchecked non-blocked task; record blockers "
            "and continue independent work. Do not close until every checkbox and acceptance "
            "criterion is complete and validated. Keep shared APIs semantic/config-driven and "
            "scene/place/material-ID-specific policy in composition; prove reuse with an independent "
            "consumer/fixture when practical. If the same gate fails twice, isolate a minimal "
            "repro/root cause before another speculative fix." % guide)
    else:
        directions = (
            "Follow `%s` plus common `SceneIssues/README.md` rules. Inspect captures/marked regions, "
            "discriminate competing hypotheses with evidence, add a behavioral regression, validate "
            "the scene, and check blast radius/cost. Work the next non-blocked acceptance item; "
            "record blockers and continue independent work. If the same gate fails twice, isolate a "
            "minimal repro/root cause before another speculative fix." % guide)
    return """You are {name}. Work only on the {work_kind} assignment `SceneIssues/open/{task_id}` on `{branch}`; `{ci_branch}` is the only targeted-CI transport. Fetch origin and resume the branch, or create it from `origin/master`.

Follow `AGENTS.md`. {directions}

Never replace queued/running CI. After a completed failure, fix the cause and reuse only the assigned CI transport for the next exact-SHA request.

After green exact-SHA CI, complete pending metadata on `{branch}`; move `SceneIssues/pending/{task_id}` to `SceneIssues/closed/{task_id}`, set status=`fixed` and `resolvedUtc`, merge `origin/master`, and push that exact branch head to `origin/master` non-force. If master advances, fetch/merge/retry. Do not modify another assignment, edit `.github/test-request.json` on the feature branch, create extra CI transports, or self-select more work.""".format(
        name=name,
        task_id=task_id,
        branch=branch_name,
        ci_branch=ci_branch_name,
        work_kind=work_kind,
        directions=directions,
    )


def continuation_prompt(number, task_id, info=None):
    work_kind = (info or {}).get("work_kind") or scene_work_kind(task_id)
    guide = workflow_path(work_kind)
    gate = (info or {}).get("completion_gate") or {}
    state = gate.get("state")
    ci_branch_name = gate.get("ci_branch") or ci_branch(number)
    ci_head = gate.get("ci_head") or "<missing>"
    fix_commit = gate.get("fix_commit") or "<missing>"

    if state in ("close_and_merge", "merge_to_master"):
        feature_gate = ("First confirm every `tasks.md` checkbox and every acceptance criterion "
                        "is complete; if any is unfinished, keep the feature open or pending and "
                        "continue the work. " if work_kind == FEATURE_WORK_KIND else "")
        close = ("Move `SceneIssues/pending/%s` to `SceneIssues/closed/%s`, set status=`fixed` "
                 "and `resolvedUtc`, and commit that bookkeeping. " % (task_id, task_id)) \
            if state == "close_and_merge" else "The assignment is already closed on your branch. "
        return ("%s is verified. %s%sFetch current `origin/master`, merge it into `%s`, resolve "
                "only in-scope conflicts, push the feature branch, then push its exact head to "
                "`origin/master` non-force. If master advanced, fetch, merge, and retry; do not "
                "wait for the coordinator." % (
                    task_id, feature_gate, close, feature_branch(number)))

    if state == "missing_branch":
        return ("%s is fixed but `%s` is missing. Create the next exact-SHA request directly on "
                "the source containing fixCommit %s, update only that CI ref, and monitor "
                "`ci/single-test`." % (task_id, ci_branch_name, fix_commit))
    if state == "missing_fix":
        return ("%s is fixed, but `%s` at %s does not contain fixCommit %s. Create one fresh "
                "request on the correct source using that same CI transport, then monitor it." % (
                    task_id, ci_branch_name, ci_head, fix_commit))
    if state == "not_created":
        return ("%s has no `ci/single-test` status for `%s` at %s. Check for an exact-SHA Actions "
                "run. Leave queued/running work alone; only after the documented admission window "
                "may you update the assigned CI ref. Do not use another transport." % (
                    task_id, ci_branch_name, ci_head))
    if state in ("queued", "in_progress", "waiting", "requested", "pending"):
        return ("%s: `%s` at %s is %s. Monitor that exact request without replacing it." % (
                    task_id, ci_branch_name, ci_head, state))
    if state in ("failure", "error", "cancelled", "timed_out", "action_required"):
        return ("%s: `%s` at %s reported `ci/single-test=%s`. Inspect the run/artifact. After the "
                "completed failure, fix the cause (or retry a proven infrastructure failure) and "
                "reuse only this assigned CI transport for the next exact-SHA request. Never "
                "replace active CI." % (task_id, ci_branch_name, ci_head, state))

    checklist = (" Keep `plan.md` and `tasks.md` separate and current; work the next unchecked "
                 "non-blocked task; record blockers and continue independent work; do not close "
                 "with any unchecked task." if work_kind == FEATURE_WORK_KIND else
                 " Work the next non-blocked acceptance item; record blockers and continue "
                 "independent work.")
    reuse = (" Keep shared APIs semantic/config-driven and scene-specific policy in composition."
             if work_kind == FEATURE_WORK_KIND else "")
    return ("Continue only the %s assignment %s on `%s`; it may currently be under "
            "`SceneIssues/open/%s` or `SceneIssues/pending/%s`, so do not move it backward because "
            "of prompt wording. Follow `%s` plus common `SceneIssues/README.md` rules.%s%s If the "
            "same gate has failed twice, isolate a minimal repro/root cause before another "
            "speculative fix. Once verified, close the assignment and merge your branch to master." % (
                work_kind, task_id, feature_branch(number), task_id, task_id, guide, checklist,
                reuse))


if globals().get("__name__") == "__main__":
    if "--check" in sys.argv:
        check_only()
    else:
        coordinator_loop()
