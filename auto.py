"""Coordinator entrypoint plus concise prompt-policy overrides."""
from __future__ import print_function

import os
import sys


def _bootstrap_script_dir():
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
            "Maintain separate `plan.md` and `tasks.md`. Work the next unchecked non-blocked task; "
            "record blockers and continue independent work. Add work only for acceptance, "
            "correctness/regression, reuse boundaries, or demonstrated quality defects; no "
            "opportunistic enhancements. Keep shared APIs semantic/config-driven and scene-specific "
            "policy in composition. Prove reuse with an independent consumer/fixture when practical. "
            "Do not refactor adjacent systems unless acceptance or a demonstrated defect requires it."
        )
    else:
        directions = (
            "Inspect captures/marked regions, discriminate competing hypotheses with evidence, add a "
            "behavioral regression, validate the built scene, and check blast radius/cost."
        )

    return """You are {name}. Work only on `{task}` on `{branch}`; `{ci_branch}` is your only targeted-CI transport. Fetch origin and resume the branch, or create it from `origin/master`.

Follow `AGENTS.md`, `{guide}`, and common `SceneIssues/README.md`. {directions} If an external prerequisite is unavailable, record the blocker and continue independent work; do not change acceptance. If the same acceptance symptom/assertion fails after two materially different fixes, isolate a minimal repro/root cause before another fix.

Never replace queued/running CI. After a completed failure, fix the cause or retry proven infrastructure failure using the same CI transport.

Do not close until every required checkbox and acceptance criterion is validated. After green exact-SHA gates, move `SceneIssues/open/{task}` directly to `SceneIssues/closed/{task}`, set `status=fixed` and `resolvedUtc`, merge current `origin/master`, and push that exact feature head to `origin/master` non-force. If master advances, fetch/merge/retry. Do not modify another assignment, put `.github/test-request.json` on the feature branch, create alternate CI transports, or self-select more work.""".format(
        name=name,
        task=task_id,
        branch=branch_name,
        ci_branch=ci_branch_name,
        guide=guide,
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
        return ("%s is verified. Confirm all required checkboxes/acceptance are complete, move "
                "`SceneIssues/open/%s` to `SceneIssues/closed/%s` if not already closed, set "
                "status=`fixed` and `resolvedUtc`, then fetch/merge current `origin/master` and push "
                "the exact `%s` head to `origin/master` non-force. If master advances, merge/retry." % (
                    task_id, task_id, task_id, feature_branch(number)))

    if state == "missing_branch":
        return ("%s: `%s` is missing. Create the next exact-SHA request from the source containing "
                "fixCommit %s and monitor `ci/single-test`." % (task_id, ci_branch_name, fix_commit))
    if state == "missing_fix":
        return ("%s: `%s` at %s lacks fixCommit %s. Create a fresh request on that same transport "
                "from the correct source and monitor it." % (task_id, ci_branch_name, ci_head, fix_commit))
    if state == "not_created":
        return ("%s: no `ci/single-test` exists for `%s` at %s. Leave active CI alone; after the "
                "documented admission window, update only the assigned CI ref." % (
                    task_id, ci_branch_name, ci_head))
    if state in ("queued", "in_progress", "waiting", "requested", "pending"):
        return ("%s: `%s` at %s is %s. Monitor it without replacement." % (
                    task_id, ci_branch_name, ci_head, state))
    if state in ("failure", "error", "cancelled", "timed_out", "action_required"):
        return ("%s: `%s` at %s reported `ci/single-test=%s`. Inspect evidence, fix the cause or "
                "retry proven infrastructure failure, then reuse this same CI transport. Never "
                "replace active CI." % (task_id, ci_branch_name, ci_head, state))

    checklist = (" Maintain `plan.md`/`tasks.md`; work the next unchecked non-blocked item; record "
                 "blockers and continue independent work." if work_kind == FEATURE_WORK_KIND else
                 " Work the next non-blocked acceptance item; record blockers and continue independent work.")
    return ("Continue only the %s assignment %s on `%s`; keep it under `SceneIssues/open/%s` until "
            "closure. Follow `%s` plus common `SceneIssues/README.md` rules.%s If an external "
            "prerequisite is unavailable, record it and continue independent work without changing "
            "acceptance. If the same acceptance symptom/assertion fails after two materially "
            "different fixes, isolate a minimal repro/root cause before another fix." % (
                work_kind, task_id, feature_branch(number), task_id, guide, checklist))


if globals().get("__name__") == "__main__":
    if "--check" in sys.argv:
        check_only()
    else:
        coordinator_loop()
