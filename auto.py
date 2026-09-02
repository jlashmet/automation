"""Coordinator entrypoint plus concise prompt-policy and durable assignment overrides."""
from __future__ import print_function

import os
import sys
import tempfile
from collections import OrderedDict


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


# Assignment ownership is repository state, not coordinator-machine state. Keep the
# existing core's in-memory registry shape so the UI/lease code stays unchanged, but
# reconstruct and persist durable ownership through each open SceneIssue's issue.json
# on an unprotected coordination branch. Queue/open/closed truth remains on master.
REPO_PATH = os.path.abspath(os.environ.get("VOXEL_REPO_PATH", REPO_PATH))
SCENE_ISSUES_PATH = os.path.join(REPO_PATH, "SceneIssues")
OPEN_SCENE_ISSUES_PATH = os.path.join(SCENE_ISSUES_PATH, "open")
PENDING_SCENE_ISSUES_PATH = os.path.join(SCENE_ISSUES_PATH, "pending")
ASSIGNMENT_BRANCH = os.environ.get("VOXEL_ASSIGNMENT_BRANCH", "automation/assignments")
ASSIGNMENT_REF = "refs/remotes/%s/%s" % (REMOTE, ASSIGNMENT_BRANCH)
ASSIGNMENT_REMOTE_REF = "refs/heads/%s" % ASSIGNMENT_BRANCH
REGISTRY_PATH = "SceneIssue issue.json on origin/%s" % ASSIGNMENT_BRANCH
ASSIGNMENT_FIELD = "assignment"
ASSIGNMENT_COMMIT_MESSAGE = "chore(scene-issues): persist coordinator assignment"
MASTER_UPDATE_RETRIES = 4


def run_git(arguments, check=True, input_text=None, extra_env=None):
    command = ["git", "-C", REPO_PATH] + list(arguments)
    environment = None
    if extra_env:
        environment = os.environ.copy()
        environment.update(extra_env)
    stdin = subprocess.PIPE if input_text is not None else None
    process = subprocess.Popen(
        command, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
    payload = None
    if input_text is not None:
        payload = input_text if isinstance(input_text, bytes) else input_text.encode("utf-8")
    stdout, stderr = process.communicate(payload)
    stdout = _decode(stdout)
    stderr = _decode(stderr)
    if check and process.returncode != 0:
        raise RuntimeError("git command failed (%s): %s" % (
            " ".join(arguments), stderr.strip() or "exit %d" % process.returncode))
    return process.returncode, stdout, stderr


def read_json_at_ref(ref_name, repo_relative_path):
    code, stdout, unused_stderr = run_git(
        ["show", "%s:%s" % (ref_name, repo_relative_path)], check=False)
    if code != 0:
        return None
    try:
        value = json.loads(stdout, object_pairs_hook=OrderedDict)
    except ValueError:
        return None
    return value if hasattr(value, "get") else None


def ensure_assignment_ref():
    """Create the durable coordination branch from current master if it does not exist."""
    if ref_exists(ASSIGNMENT_REF):
        return
    fetch_remote()
    if ref_exists(ASSIGNMENT_REF):
        return
    unused_code, master_sha, unused_stderr = run_git(["rev-parse", QUEUE_REF])
    master_sha = master_sha.strip()
    code, unused_stdout, stderr = run_git([
        "push", REMOTE, "%s:%s" % (master_sha, ASSIGNMENT_REMOTE_REF),
    ], check=False)
    if code == 0:
        run_git(["update-ref", ASSIGNMENT_REF, master_sha])
        return
    fetch_remote()
    if ref_exists(ASSIGNMENT_REF):
        return
    raise RuntimeError("could not create assignment branch %s: %s" % (
        ASSIGNMENT_BRANCH, stderr.strip() or "git push failed"))


def assignment_issue_path(task_id, ref_name=None):
    """Return the issue.json path currently authoritative as open on master."""
    if task_id not in list_open_tasks(QUEUE_REF):
        return None
    return "SceneIssues/open/%s/issue.json" % task_id


def _issue_assignment(issue):
    value = (issue or {}).get(ASSIGNMENT_FIELD)
    if not hasattr(value, "get") or not value.get("owner"):
        return None
    return OrderedDict(value)


def _persistent_assignment(info):
    """Return only durable ownership data; UI heartbeat/nudge state stays in memory."""
    if not info or info.get("status") != "in_progress":
        return None
    result = OrderedDict()
    for key in ("owner", "branch", "ci_branch", "claimed_at", "lease_history"):
        if key in info:
            result[key] = info[key]
    return result


def _runtime_assignment(persisted, now=None):
    """Restore durable assignment state and start a fresh local UI lease."""
    if not persisted:
        return None
    now = time.time() if now is None else now
    result = dict(persisted)
    result["status"] = "in_progress"
    result["last_heartbeat"] = now
    result["last_prompted"] = 0
    result["prompt_count"] = 0
    result["prompt_confirmed"] = False
    return result


def load_registry(ref_name=None, now=None):
    """Load assignment ownership exclusively from SceneIssue issue.json files."""
    ref_name = ref_name or ASSIGNMENT_REF
    now = time.time() if now is None else now
    tasks = {}
    persisted = {}
    if not ref_exists(ref_name):
        return {"version": 2, "tasks": tasks, "_persisted_assignments": persisted}
    for task_id in list_open_tasks(QUEUE_REF):
        path = "SceneIssues/open/%s/issue.json" % task_id
        issue = read_json_at_ref(ref_name, path)
        assignment = _issue_assignment(issue)
        if not assignment:
            continue
        persisted[task_id] = assignment
        runtime = _runtime_assignment(assignment, now=now)
        runtime["work_kind"] = scene_work_kind(task_id, QUEUE_REF)
        tasks[task_id] = runtime
    return {
        "version": 2,
        "tasks": tasks,
        "_persisted_assignments": persisted,
    }


def _replace_registry_from_remote(registry, now=None):
    """Refresh ownership from the coordination branch while preserving ephemeral UI state."""
    now = time.time() if now is None else now
    remote = load_registry(now=now)
    ephemeral_top = dict(
        (key, value) for key, value in registry.items()
        if key not in ("version", "tasks", "_persisted_assignments"))
    durable_keys = set(("owner", "branch", "ci_branch", "claimed_at", "lease_history", "status"))
    for task_id, remote_info in remote["tasks"].items():
        local_info = registry.get("tasks", {}).get(task_id)
        if local_info and local_info.get("owner") == remote_info.get("owner"):
            for key, value in local_info.items():
                if key not in durable_keys:
                    remote_info[key] = value
            remote_info["last_heartbeat"] = max(
                float(local_info.get("last_heartbeat") or 0),
                float(remote_info.get("last_heartbeat") or 0))
    registry.clear()
    registry.update(remote)
    registry.update(ephemeral_top)
    return registry


def _adopt_remote_assignment(registry, task_id, remote_assignment):
    persisted = registry.setdefault("_persisted_assignments", {})
    if remote_assignment:
        persisted[task_id] = OrderedDict(remote_assignment)
        runtime = _runtime_assignment(remote_assignment)
        runtime["work_kind"] = scene_work_kind(task_id, QUEUE_REF)
        registry.setdefault("tasks", {})[task_id] = runtime
    else:
        persisted.pop(task_id, None)
        registry.setdefault("tasks", {}).pop(task_id, None)


def _create_assignment_commit(master_sha, parent_sha, updates):
    """Create a coordination-branch commit from the latest master tree without checkout."""
    descriptor, index_path = tempfile.mkstemp(prefix="auto-assignment-index-")
    os.close(descriptor)
    try:
        os.remove(index_path)
    except OSError:
        pass
    index_env = {"GIT_INDEX_FILE": index_path}
    identity = {
        "GIT_AUTHOR_NAME": "SceneIssue Coordinator",
        "GIT_AUTHOR_EMAIL": "scene-issue-coordinator@local",
        "GIT_COMMITTER_NAME": "SceneIssue Coordinator",
        "GIT_COMMITTER_EMAIL": "scene-issue-coordinator@local",
    }
    try:
        run_git(["read-tree", master_sha], extra_env=index_env)
        for path in sorted(updates):
            unused_code, blob_sha, unused_stderr = run_git(
                ["hash-object", "-w", "--stdin"], input_text=updates[path])
            run_git([
                "update-index", "--add", "--cacheinfo", "100644",
                blob_sha.strip(), path,
            ], extra_env=index_env)
        unused_code, tree_sha, unused_stderr = run_git(["write-tree"], extra_env=index_env)
        unused_code, commit_sha, unused_stderr = run_git([
            "commit-tree", tree_sha.strip(), "-p", parent_sha, "-m", ASSIGNMENT_COMMIT_MESSAGE,
        ], extra_env=identity)
        return commit_sha.strip()
    finally:
        try:
            os.remove(index_path)
        except OSError:
            pass


def save_registry(registry):
    """Persist changed durable ownership into issue manifests on the coordination branch."""
    persisted = registry.setdefault("_persisted_assignments", {})
    dirty = []
    for task_id, info in registry.get("tasks", {}).items():
        if _persistent_assignment(info) != persisted.get(task_id):
            dirty.append(task_id)
    if not dirty:
        return False

    for unused_attempt in range(MASTER_UPDATE_RETRIES):
        fetch_remote()
        ensure_assignment_ref()
        unused_code, parent_sha, unused_stderr = run_git(["rev-parse", ASSIGNMENT_REF])
        unused_code, master_sha, unused_stderr = run_git(["rev-parse", QUEUE_REF])
        parent_sha = parent_sha.strip()
        master_sha = master_sha.strip()
        remote_registry = load_registry(ref_name=ASSIGNMENT_REF)
        remote_persisted = OrderedDict(remote_registry.get("_persisted_assignments") or {})
        accepted = []

        for task_id in list(dirty):
            baseline = persisted.get(task_id)
            remote_assignment = remote_persisted.get(task_id)
            if remote_assignment != baseline:
                log("assignment for %s changed on %s; adopting remote owner %s" % (
                    task_id, ASSIGNMENT_BRANCH,
                    (remote_assignment or {}).get("owner") or "<unassigned>"))
                _adopt_remote_assignment(registry, task_id, remote_assignment)
                continue
            local_assignment = _persistent_assignment(registry.get("tasks", {}).get(task_id))
            if local_assignment:
                remote_persisted[task_id] = local_assignment
            else:
                remote_persisted.pop(task_id, None)
            accepted.append(task_id)

        if not accepted:
            return False

        updates = OrderedDict()
        for task_id, assignment in remote_persisted.items():
            path = assignment_issue_path(task_id)
            if not path:
                continue
            issue = read_json_at_ref(QUEUE_REF, path)
            if issue is None:
                raise RuntimeError("cannot read assignment issue from master: %s" % path)
            issue[ASSIGNMENT_FIELD] = assignment
            updates[path] = json.dumps(issue, indent=2) + "\n"

        commit_sha = _create_assignment_commit(master_sha, parent_sha, updates)
        code, unused_stdout, stderr = run_git([
            "push", REMOTE, "%s:%s" % (commit_sha, ASSIGNMENT_REMOTE_REF),
        ], check=False)
        if code == 0:
            run_git(["update-ref", ASSIGNMENT_REF, commit_sha])
            registry["_persisted_assignments"] = OrderedDict(remote_persisted)
            return True

        message = stderr.strip().lower()
        if "non-fast-forward" in message or "fetch first" in message or "failed to push" in message:
            log("assignment branch advanced while persisting ownership; retrying")
            continue
        raise RuntimeError("failed to persist assignment state: %s" % (
            stderr.strip() or "git push failed"))

    raise RuntimeError("assignment branch kept advancing while persisting assignment state")


def sync_remote_and_registry(registry):
    fetch_remote()
    ensure_assignment_ref()
    _replace_registry_from_remote(registry)
    refresh_ci_activity(registry)
    reconcile_assignments(registry)
    return list_open_tasks()


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
