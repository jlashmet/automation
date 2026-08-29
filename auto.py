"""Coordinate remote scene-issue agents through browser tabs and GitHub.

This script is intended to run in Oculix/SikuliX. Its registry and Git logic can
also be imported and tested with regular CPython; UI globals are only resolved
inside the UI functions.
"""

from __future__ import print_function

import atexit
import json
import os
import subprocess
import sys
import time
import traceback


# ---------------- CONFIG ----------------

def discover_script_dir():
    """Find adjacent assets under both CPython and Oculix's Jython runner."""
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


SCRIPT_DIR = discover_script_dir()
REPO_PATH = "/Users/jlashmet/code/voxel"
SCENE_ISSUES_PATH = os.path.join(REPO_PATH, "SceneIssues")
OPEN_SCENE_ISSUES_PATH = os.path.join(SCENE_ISSUES_PATH, "open")
PENDING_SCENE_ISSUES_PATH = os.path.join(SCENE_ISSUES_PATH, "pending")
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "_registry.json")
LOCK_PATH = os.path.join(SCRIPT_DIR, "_coordinator.lock")
DIAGNOSTICS_PATH = os.path.join(SCRIPT_DIR, "_diagnostics")

NUM_AGENTS = 9                         # browser tabs selected with Cmd+1 .. Cmd+9
REMOTE = "origin"
QUEUE_REF = "origin/master"
GITHUB_REPOSITORY = "jlashmet/voxel"
FEATURE_BRANCH_TEMPLATE = "fixes/agent-{number}"
CI_BRANCH_TEMPLATE = "ci-test/fixes/agent-{number}"

POLL_WAIT_SECONDS = 5
FETCH_INTERVAL_SECONDS = 30
TAB_SETTLE_SECONDS = 5
UI_STATE_TIMEOUT_SECONDS = 5
STALE_SECONDS = 60 * 60                # reclaim after one hour without a visible live tab
NUDGE_INTERVAL_SECONDS = 10 * 60
MAX_NUDGE_INTERVAL_SECONDS = 30 * 60
IMAGE_TIMEOUT_SECONDS = 5
MIN_IMAGE_SIMILARITY = 0.95
RUNNING_IMAGE = "in_progress_glyph.png"
REGISTRY_READ_ATTEMPTS = 5
REGISTRY_READ_RETRY_SECONDS = 0.25

OPEN_STATUSES = ("", "open", "todo")
PENDING_STATUS = "pending"
ISSUE_WORK_KIND = "issue"
FEATURE_WORK_KIND = "feature"
ISSUE_WORKFLOW_PATH = "SceneIssues/issue-readme.md"
FEATURE_WORKFLOW_PATH = "SceneIssues/feature-readme.md"

_lock_owned = False

try:
    TEXT_TYPE = unicode
except NameError:
    TEXT_TYPE = str


# ---------------- GENERAL HELPERS ----------------

def log(message):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = "[%s] %s\n" % (stamp, _text(message))
    if sys.version_info[0] < 3:
        line = line.encode("utf-8")
    sys.stdout.write(line)
    sys.stdout.flush()


def agent_id(number):
    return "agent-%d" % number


def feature_branch(number):
    return FEATURE_BRANCH_TEMPLATE.format(number=number)


def ci_branch(number):
    return CI_BRANCH_TEMPLATE.format(number=number)


def atomic_write_json(path, value):
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    temporary = path + ".tmp-%d" % os.getpid()
    with open(temporary, "w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except (AttributeError, OSError):
            pass
    os.rename(temporary, path)


def load_registry(path=None):
    path = path or REGISTRY_PATH
    if not os.path.exists(path):
        return {"version": 1, "tasks": {}}
    value = None
    last_error = None
    for attempt in range(REGISTRY_READ_ATTEMPTS):
        try:
            with open(path, "r") as handle:
                value = json.load(handle)
            last_error = None
            break
        except (IOError, ValueError) as error:
            last_error = error
            if attempt + 1 < REGISTRY_READ_ATTEMPTS:
                time.sleep(REGISTRY_READ_RETRY_SECONDS)
    if last_error is not None:
        raise ValueError(
            "could not read registry JSON at %s after %d attempts: %s" % (
                os.path.abspath(path), REGISTRY_READ_ATTEMPTS, last_error))
    if not isinstance(value, dict) or not isinstance(value.get("tasks"), dict):
        raise ValueError(
            "registry at %s must be an object containing a tasks object" %
            os.path.abspath(path))
    return value


def save_registry(registry, path=None):
    registry["version"] = 1
    atomic_write_json(path or REGISTRY_PATH, registry)


def acquire_process_lock(path=None):
    global _lock_owned
    path = path or LOCK_PATH
    try:
        os.mkdir(path)
    except OSError:
        pid_path = os.path.join(path, "pid")
        try:
            with open(pid_path, "r") as handle:
                pid = int(handle.read().strip())
            os.kill(pid, 0)
        except (IOError, OSError, ValueError):
            raise RuntimeError(
                "stale coordinator lock at %s; remove that directory after confirming no "
                "other coordinator is running" % path
            )
        raise RuntimeError("another coordinator is already running with pid %d" % pid)
    with open(os.path.join(path, "pid"), "w") as handle:
        handle.write(str(os.getpid()))
    _lock_owned = True


def release_process_lock(path=None):
    global _lock_owned
    path = path or LOCK_PATH
    if not _lock_owned:
        return
    try:
        os.remove(os.path.join(path, "pid"))
        os.rmdir(path)
    except OSError:
        pass
    _lock_owned = False


def _decode(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _text(value):
    """Return Unicode text without Python 2/Jython's implicit ASCII coercion."""
    if value is None:
        return TEXT_TYPE("")
    if isinstance(value, TEXT_TYPE):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return TEXT_TYPE(value)


def run_git(arguments, check=True):
    command = ["git", "-C", REPO_PATH] + list(arguments)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    stdout = _decode(stdout)
    stderr = _decode(stderr)
    if check and process.returncode != 0:
        raise RuntimeError("git command failed (%s): %s" % (
            " ".join(arguments), stderr.strip() or "exit %d" % process.returncode))
    return process.returncode, stdout, stderr


def fetch_remote():
    run_git(["fetch", "--prune", REMOTE])


def read_json_at_ref(ref_name, repo_relative_path):
    code, stdout, unused_stderr = run_git(
        ["show", "%s:%s" % (ref_name, repo_relative_path)], check=False)
    if code != 0:
        return None
    try:
        value = json.loads(stdout)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def list_open_tasks(ref_name=None):
    """Return capture-directory names that are open on the queue ref."""
    ref_name = ref_name or QUEUE_REF
    unused_code, stdout, unused_stderr = run_git(
        ["ls-tree", "-r", "--name-only", ref_name, "--", "SceneIssues/open"])
    tasks = []
    for path in stdout.splitlines():
        if not path.startswith("SceneIssues/open/") or not path.endswith("/issue.json"):
            continue
        parts = path.split("/")
        if len(parts) != 4:
            continue
        issue = read_json_at_ref(ref_name, path)
        if issue is None:
            log("ignoring invalid issue JSON at %s:%s" % (ref_name, path))
            continue
        status = _text(issue.get("status") or "").lower()
        if status in OPEN_STATUSES:
            tasks.append(parts[2])
    return sorted(set(tasks))


def scene_work_kind(task_id, ref_name=None):
    """Classify an assignment using explicit metadata or its published note prefix."""
    ref_name = ref_name or QUEUE_REF
    path = "SceneIssues/open/%s/issue.json" % task_id
    issue = read_json_at_ref(ref_name, path) or {}
    explicit = _text(issue.get("workType") or "").strip().lower()
    if explicit in (ISSUE_WORK_KIND, FEATURE_WORK_KIND):
        return explicit
    note = _text(issue.get("note") or "").lstrip().upper()
    if note.startswith("FEATURE"):
        return FEATURE_WORK_KIND
    return ISSUE_WORK_KIND


def workflow_path(work_kind):
    if work_kind == FEATURE_WORK_KIND:
        return FEATURE_WORKFLOW_PATH
    return ISSUE_WORKFLOW_PATH


def remote_ref(branch_name):
    return "refs/remotes/%s/%s" % (REMOTE, branch_name)


def ref_exists(ref_name):
    code, unused_stdout, unused_stderr = run_git(
        ["show-ref", "--verify", "--quiet", ref_name], check=False)
    return code == 0


def branch_head(branch_name):
    ref_name = remote_ref(branch_name)
    if not ref_exists(ref_name):
        return None
    unused_code, stdout, unused_stderr = run_git(["rev-parse", ref_name])
    return stdout.strip()


def commit_is_on_branch(commit_sha, branch_name):
    if not commit_sha or not ref_exists(remote_ref(branch_name)):
        return False
    code, unused_stdout, unused_stderr = run_git(
        ["merge-base", "--is-ancestor", commit_sha, remote_ref(branch_name)], check=False)
    return code == 0


def commit_is_on_ref(commit_sha, ref_name):
    if not commit_sha:
        return False
    code, unused_stdout, unused_stderr = run_git(
        ["rev-parse", "--verify", "--quiet", ref_name], check=False)
    if code != 0:
        return False
    code, unused_stdout, unused_stderr = run_git(
        ["merge-base", "--is-ancestor", commit_sha, ref_name], check=False)
    return code == 0


def branch_has_unmerged_work(branch_name):
    head = branch_head(branch_name)
    return bool(head and not commit_is_on_ref(head, QUEUE_REF))


def branch_introduced_issue_paths(branch_name):
    """Return branch issue manifests whose capture ID is absent from queue master."""
    ref_name = remote_ref(branch_name)
    if not ref_exists(ref_name):
        return []

    def manifests(ref):
        unused_code, stdout, unused_stderr = run_git([
            "ls-tree", "-r", "--name-only", ref, "--",
            "SceneIssues/open", "SceneIssues/pending", "SceneIssues/closed",
        ])
        result = {}
        for path in stdout.splitlines():
            parts = path.split("/")
            if len(parts) == 4 and parts[0] == "SceneIssues" \
                    and parts[1] in ("open", "pending", "closed") \
                    and parts[3] == "issue.json":
                result[parts[2]] = path
        return result

    master_manifests = manifests(QUEUE_REF)
    branch_manifests = manifests(ref_name)
    return sorted(path for task_id, path in branch_manifests.items()
                  if task_id not in master_manifests)


def branch_policy_violations(task_id, branch_name):
    """Return feature-only paths forbidden for this assigned SceneIssue."""
    ref_name = remote_ref(branch_name)
    if not ref_exists(ref_name):
        return []
    unused_code, stdout, unused_stderr = run_git([
        "diff", "--name-only", "%s...%s" % (QUEUE_REF, ref_name),
    ])
    violations = []
    for path in stdout.splitlines():
        if path == ".github/test-request.json" or path.startswith(".github/workflows/"):
            violations.append(path)
            continue
        parts = path.split("/")
        if len(parts) >= 3 and parts[0] == "SceneIssues" \
                and parts[1] in ("open", "pending", "closed") and parts[2] != task_id:
            violations.append(path)
    return sorted(set(violations))


def github_status_context(commit_sha, context):
    """Return the newest GitHub commit-status state for a context, if present."""
    command = [
        "gh", "api",
        "repos/%s/commits/%s/status" % (GITHUB_REPOSITORY, commit_sha),
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        log("GitHub status lookup failed for %s: %s" % (
            commit_sha, _decode(stderr).strip() or "exit %d" % process.returncode))
        return None
    try:
        response = json.loads(_decode(stdout))
    except ValueError:
        log("GitHub returned invalid status JSON for %s" % commit_sha)
        return None
    for status in response.get("statuses") or []:
        if status.get("context") == context:
            return _text(status.get("state") or "").lower()
    return None


def github_actions_run(commit_sha):
    """Return the newest single-test Actions run for an exact request SHA."""
    command = [
        "gh", "api",
        "repos/%s/actions/runs?head_sha=%s&per_page=100" % (
            GITHUB_REPOSITORY, commit_sha),
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        log("GitHub Actions lookup failed for %s: %s" % (
            commit_sha, _decode(stderr).strip() or "exit %d" % process.returncode))
        return None
    try:
        response = json.loads(_decode(stdout))
    except ValueError:
        log("GitHub returned invalid Actions JSON for %s" % commit_sha)
        return None

    matches = []
    for run in response.get("workflow_runs") or []:
        if _text(run.get("head_sha") or "") != commit_sha:
            continue
        path = _text(run.get("path") or "")
        name = _text(run.get("name") or "")
        if not (path.endswith(".github/workflows/tests-single.yml") or
                name == "Tests (single)"):
            continue
        matches.append(run)
    if not matches:
        return None
    matches.sort(key=lambda value: _text(value.get("created_at") or ""), reverse=True)
    run = matches[0]
    status = _text(run.get("status") or "").lower()
    conclusion = _text(run.get("conclusion") or "").lower()
    state = conclusion if status == "completed" else status
    return {
        "state": state or "unknown",
        "run_id": run.get("id"),
        "run_url": _text(run.get("html_url") or ""),
        "run_created_at": _text(run.get("created_at") or ""),
    }


def github_active_single_test_runs():
    """Return queued/running single-test workflows keyed by exact head SHA."""
    command = [
        "gh", "api",
        "repos/%s/actions/runs?per_page=100" % GITHUB_REPOSITORY,
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        log("GitHub active-run lookup failed: %s" % (
            _decode(stderr).strip() or "exit %d" % process.returncode))
        return None
    try:
        response = json.loads(_decode(stdout))
    except ValueError:
        log("GitHub returned invalid active-run JSON")
        return None
    result = {}
    for run in response.get("workflow_runs") or []:
        path = _text(run.get("path") or "")
        state = _text(run.get("status") or "").lower()
        head = _text(run.get("head_sha") or "")
        if not path.endswith(".github/workflows/tests-single.yml") or \
                state not in ("queued", "in_progress", "waiting", "requested", "pending") or \
                not head:
            continue
        candidate = {
            "state": state,
            "ci_head": head,
            "run_id": run.get("id"),
            "run_url": _text(run.get("html_url") or ""),
            "run_created_at": _text(run.get("created_at") or ""),
        }
        existing = result.get(head)
        if existing is None or candidate["run_created_at"] > existing["run_created_at"]:
            result[head] = candidate
    return result


def refresh_ci_activity(registry):
    active_runs = github_active_single_test_runs()
    if active_runs is None:
        return False
    changed = False
    for info in registry["tasks"].values():
        if info.get("status") != "in_progress":
            continue
        branch_name = info.get("ci_branch")
        head = branch_head(branch_name) if branch_name else None
        activity = active_runs.get(head)
        if activity:
            if info.get("ci_activity") != activity:
                info["ci_activity"] = activity
                changed = True
        elif "ci_activity" in info:
            info.pop("ci_activity", None)
            changed = True
    return changed


def targeted_ci_passed(ci_branch_name, fix_commit):
    """Require green targeted CI whose request branch contains the recorded fix."""
    return targeted_ci_gate(ci_branch_name, fix_commit)["state"] == "success"


def targeted_ci_gate(ci_branch_name, fix_commit):
    """Describe the exact targeted-CI gate currently blocking completion."""
    head = branch_head(ci_branch_name)
    if not head:
        return {
            "state": "missing_branch",
            "ci_branch": ci_branch_name,
            "fix_commit": fix_commit,
        }
    if not commit_is_on_branch(fix_commit, ci_branch_name):
        return {
            "state": "missing_fix",
            "ci_branch": ci_branch_name,
            "ci_head": head,
            "fix_commit": fix_commit,
        }
    run = github_actions_run(head)
    status = github_status_context(head, "ci/single-test")
    if run and run["state"] in ("queued", "in_progress", "waiting", "requested", "pending"):
        state = run["state"]
    elif status:
        state = status
    elif run:
        state = run["state"]
    else:
        state = "not_created"
    result = {
        "state": state,
        "ci_branch": ci_branch_name,
        "ci_head": head,
        "fix_commit": fix_commit,
    }
    if run:
        result.update(run)
    return result


def completion_issue_state(task_id, branch_name):
    """Return verified pending or closed metadata from a remote feature branch."""
    ref_name = remote_ref(branch_name)
    if not ref_exists(ref_name):
        return None
    introduced = branch_introduced_issue_paths(branch_name)
    if introduced:
        log("%s cannot complete because %s introduced issue(s) that did not enter through %s: %s" % (
            task_id, branch_name, QUEUE_REF, ", ".join(introduced)))
        return None
    violations = branch_policy_violations(task_id, branch_name)
    if violations:
        log("%s cannot complete because %s contains forbidden feature-only paths: %s" % (
            task_id, branch_name, ", ".join(violations)))
        return None
    pending_path = "SceneIssues/pending/%s/issue.json" % task_id
    closed_path = "SceneIssues/closed/%s/issue.json" % task_id
    pending_issue = read_json_at_ref(ref_name, pending_path)
    closed_issue = read_json_at_ref(ref_name, closed_path)
    issue = pending_issue or closed_issue
    if issue is None:
        return None
    open_issue_path = "SceneIssues/open/%s/issue.json" % task_id
    if read_json_at_ref(ref_name, open_issue_path) is not None or \
            (pending_issue is not None and closed_issue is not None):
        log("%s must exist in exactly one completion folder on %s" % (
            task_id, branch_name))
        return None
    status = _text(issue.get("status") or "").lower()
    expected_status = PENDING_STATUS if pending_issue is not None else "fixed"
    if status != expected_status:
        return None

    resolved = _text(issue.get("resolvedUtc") or "").strip()
    if status == PENDING_STATUS and resolved:
        log("%s on %s is pending but already has resolvedUtc" % (task_id, branch_name))
        return None
    if status == "fixed" and not resolved:
        log("%s on %s is fixed but missing resolvedUtc" % (task_id, branch_name))
        return None

    summary = _text(issue.get("resolutionSummary") or "").strip()
    if not summary:
        log("%s on %s says %s but has no resolutionSummary" % (
            task_id, branch_name, status))
        return None

    required = ("regressionTest", "fixCommit")
    missing = [key for key in required if not _text(issue.get(key) or "").strip()]
    if missing:
        log("%s on %s says pending but is missing %s" % (
            task_id, branch_name, ", ".join(missing)))
        return None
    if not commit_is_on_branch(_text(issue["fixCommit"]).strip(), branch_name):
        log("%s has fixCommit %s that is not on %s" % (
            task_id, issue["fixCommit"], branch_name))
        return None
    return {
        "status": status,
        "branch_head": branch_head(branch_name),
        "fix_commit": _text(issue.get("fixCommit") or "").strip(),
    }


# Compatibility alias for existing callers.
pending_issue_state = completion_issue_state


def closed_on_master(task_id, candidate):
    """Return true when the worker's completed branch is present on master."""
    terminal = closed_issue_state_on_master(task_id)
    if not terminal or terminal.get("fix_commit") != candidate.get("fix_commit"):
        return False
    return commit_is_on_ref(candidate.get("branch_head"), QUEUE_REF)


def closed_issue_state_on_master(task_id):
    """Return terminal metadata when master authoritatively contains a valid closed issue."""
    closed_path = "SceneIssues/closed/%s/issue.json" % task_id
    issue = read_json_at_ref(QUEUE_REF, closed_path)
    if issue is None or _text(issue.get("status") or "").lower() != "fixed":
        return None
    if read_json_at_ref(QUEUE_REF, "SceneIssues/open/%s/issue.json" % task_id) is not None or \
            read_json_at_ref(QUEUE_REF, "SceneIssues/pending/%s/issue.json" % task_id) is not None:
        return None
    required = ("resolvedUtc", "resolutionSummary", "regressionTest", "fixCommit")
    if any(not _text(issue.get(key) or "").strip() for key in required):
        return None
    fix_commit = _text(issue.get("fixCommit") or "").strip()
    if not commit_is_on_ref(fix_commit, QUEUE_REF):
        return None
    unused_code, stdout, unused_stderr = run_git(["rev-parse", QUEUE_REF])
    return {
        "status": "fixed",
        "branch_head": stdout.strip(),
        "fix_commit": fix_commit,
    }


def closed_queue_state_on_master(task_id):
    """Return authoritative queue completion even when its audit metadata is invalid.

    A capture that exists only under closed/ must not retain a live worker lease. The
    stricter closed_issue_state_on_master check remains the audit path; this fallback
    records why the closed capture could not pass that audit while still releasing the
    agent to work on an actually open capture.
    """
    closed_path = "SceneIssues/closed/%s/issue.json" % task_id
    issue = read_json_at_ref(QUEUE_REF, closed_path)
    if issue is None or _text(issue.get("status") or "").lower() != "fixed":
        return None
    if read_json_at_ref(QUEUE_REF, "SceneIssues/open/%s/issue.json" % task_id) is not None or \
            read_json_at_ref(QUEUE_REF, "SceneIssues/pending/%s/issue.json" % task_id) is not None:
        return None

    warnings = []
    required = ("resolvedUtc", "resolutionSummary", "regressionTest", "fixCommit")
    missing = [key for key in required if not _text(issue.get(key) or "").strip()]
    if missing:
        warnings.append("missing metadata: %s" % ", ".join(missing))
    fix_commit = _text(issue.get("fixCommit") or "").strip()
    if fix_commit and not commit_is_on_ref(fix_commit, QUEUE_REF):
        warnings.append("fixCommit is not on %s" % QUEUE_REF)
    unused_code, stdout, unused_stderr = run_git(["rev-parse", QUEUE_REF])
    return {
        "status": "fixed",
        "branch_head": stdout.strip(),
        "fix_commit": fix_commit,
        "audit_warnings": warnings or ["strict closed-capture validation failed"],
    }


# ---------------- REGISTRY / LEASES ----------------

def get_agent_task(agent_name, registry):
    matches = []
    for task_id, info in registry["tasks"].items():
        if info.get("owner") == agent_name and info.get("status") == "in_progress":
            matches.append((float(info.get("claimed_at") or 0), task_id))
    if not matches:
        return None
    matches.sort()
    return matches[0][1]


def _assign(task_id, agent_name, branch_name, ci_branch_name, registry, now):
    previous = registry["tasks"].get(task_id) or {}
    history = list(previous.get("lease_history") or [])
    if previous.get("owner") and previous.get("owner") != agent_name:
        history.append({
            "owner": previous.get("owner"),
            "claimed_at": previous.get("claimed_at"),
            "last_heartbeat": previous.get("last_heartbeat"),
            "ended_as": "stale" if previous.get("status") == "in_progress"
                        else previous.get("status"),
        })
    registry["tasks"][task_id] = {
        "status": "in_progress",
        "owner": agent_name,
        "branch": branch_name,
        "ci_branch": ci_branch_name,
        "work_kind": scene_work_kind(task_id),
        "claimed_at": now,
        "last_heartbeat": now,
        "last_prompted": 0,
        "lease_history": history,
    }


def claim_new_task(agent_name, branch_name, ci_branch_name, registry, open_tasks, now=None):
    """Claim the oldest available task, including an expired lease."""
    if get_agent_task(agent_name, registry):
        return get_agent_task(agent_name, registry)
    now = time.time() if now is None else now
    for task_id in sorted(open_tasks):
        info = registry["tasks"].get(task_id)
        if info is None or info.get("status") != "in_progress":
            if info is not None:
                log("reopening %s because it is present in the authoritative open queue" %
                    task_id)
            _assign(task_id, agent_name, branch_name, ci_branch_name, registry, now)
            return task_id
        if info.get("status") == "in_progress":
            heartbeat_at = float(info.get("last_heartbeat") or 0)
            if now - heartbeat_at > STALE_SECONDS:
                previous_branch = info.get("branch")
                if previous_branch and branch_has_unmerged_work(previous_branch):
                    info["handoff_required"] = True
                    info["handoff_reason"] = "stale owner has branch-only work"
                    log("not reclaiming stale task %s from %s; %s has unmerged work" % (
                        task_id, info.get("owner"), previous_branch))
                    continue
                log("reclaiming stale task %s from %s" % (task_id, info.get("owner")))
                _assign(task_id, agent_name, branch_name, ci_branch_name, registry, now)
                return task_id
    return None


def heartbeat(task_id, registry, now=None):
    info = registry["tasks"].get(task_id)
    if info and info.get("status") == "in_progress":
        info["last_heartbeat"] = time.time() if now is None else now


def mark_prompted(task_id, registry, now=None):
    info = registry["tasks"].get(task_id)
    if info and info.get("status") == "in_progress":
        info["last_prompted"] = time.time() if now is None else now
        info["prompt_count"] = int(info.get("prompt_count") or 0) + 1
        info["prompt_confirmed"] = True


def mark_prompt_attempted(task_id, registry):
    """Make an unconfirmed UI submission eligible for an immediate retry."""
    info = registry["tasks"].get(task_id)
    if info and info.get("status") == "in_progress":
        info["prompt_confirmed"] = False


def mark_response_active(task_id, registry):
    """Remember a response that must be followed as soon as the tab becomes idle."""
    info = registry["tasks"].get(task_id)
    if info and info.get("status") == "in_progress":
        info["response_active"] = True
        info.pop("idle_observed", None)


def response_became_idle(info, textbox_visible):
    """Consume the running-response marker when the input box returns."""
    if not textbox_visible:
        return False
    if info.get("response_active"):
        info.pop("response_active", None)
        info["idle_observed"] = True
        return True
    if not info.get("idle_observed"):
        info["idle_observed"] = True
        return True
    return False


def nudge_interval(info):
    count = int(info.get("prompt_count") or 0)
    return min(NUDGE_INTERVAL_SECONDS * (2 ** max(0, count - 1)),
               MAX_NUDGE_INTERVAL_SECONDS)


def should_nudge(info, now=None):
    gate_state = _text((info.get("completion_gate") or {}).get("state") or "")
    activity_state = _text((info.get("ci_activity") or {}).get("state") or "")
    active_states = ("queued", "in_progress", "waiting", "requested", "pending")
    if gate_state in active_states or activity_state in active_states:
        return False
    if info.get("last_prompted") and not info.get("prompt_confirmed"):
        return True
    now = time.time() if now is None else now
    last_prompted = float(info.get("last_prompted") or 0)
    return now - last_prompted >= nudge_interval(info)


def mark_terminal(task_id, registry, terminal, now=None):
    info = registry["tasks"].get(task_id)
    if not info:
        return
    info["status"] = terminal["status"]
    info["completed_at"] = time.time() if now is None else now
    info["completion_commit"] = terminal.get("branch_head")
    info["fix_commit"] = terminal.get("fix_commit")
    info.pop("completion_gate", None)


def reconcile_assignments(registry, now=None):
    changed = False
    for obsolete_key in ("promotion_batch", "master_ci"):
        if obsolete_key in registry:
            registry.pop(obsolete_key, None)
            changed = True
    for task_id, info in list(registry["tasks"].items()):
        if info.get("status") != "in_progress":
            continue
        terminal = closed_issue_state_on_master(task_id)
        if terminal is None:
            terminal = closed_queue_state_on_master(task_id)
        if terminal:
            mark_terminal(task_id, registry, terminal, now=now)
            if terminal.get("audit_warnings"):
                info["completion_audit_warnings"] = terminal["audit_warnings"]
                log("%s is closed on master with audit warning(s): %s" % (
                    task_id, "; ".join(terminal["audit_warnings"])))
            log("%s is closed on master; releasing %s" % (
                task_id, info.get("owner")))
            changed = True
            continue
        branch_name = info.get("branch")
        if not branch_name:
            continue
        candidate = completion_issue_state(task_id, branch_name)
        if not candidate:
            if "completion_gate" in info:
                info.pop("completion_gate", None)
                changed = True
            continue
        ci_branch_name = info.get("ci_branch")
        gate = targeted_ci_gate(ci_branch_name, candidate.get("fix_commit")) \
            if ci_branch_name else {
                "state": "missing_branch",
                "ci_branch": ci_branch_name,
                "fix_commit": candidate.get("fix_commit"),
            }
        if gate["state"] != "success":
            if info.get("completion_gate") != gate:
                info["completion_gate"] = gate
                changed = True
            log("%s is pending on %s but targeted CI gate on %s is %s" % (
                task_id, branch_name, ci_branch_name or "<missing>", gate["state"]))
            continue

        if candidate["status"] == "fixed" and closed_on_master(task_id, candidate):
            completed = dict(candidate)
            completed["status"] = "fixed"
            mark_terminal(task_id, registry, completed, now=now)
            log("%s is closed on master" % task_id)
            changed = True
            continue
        gate = {
            "state": "close_and_merge" if candidate["status"] == PENDING_STATUS
                     else "merge_to_master",
            "fix_commit": candidate.get("fix_commit"),
            "completion_commit": candidate.get("branch_head"),
        }
        if info.get("completion_gate") != gate:
            info["completion_gate"] = gate
            info["last_prompted"] = 0
            changed = True
        log("%s is verified on %s and must be closed and merged by %s" % (
            task_id, branch_name, info.get("owner")))
    return changed


# ---------------- UI HELPERS ----------------

def configure_ui():
    settings = globals().get("Settings")
    if settings is None:
        raise RuntimeError("Oculix/SikuliX Settings global is unavailable")
    settings.MinSimilarity = MIN_IMAGE_SIMILARITY
    set_bundle_path = globals().get("setBundlePath")
    if set_bundle_path:
        set_bundle_path(SCRIPT_DIR)


def switch_to_tab(number):
    """Select the exact browser tab without leaving Cmd held down.

    Passing the modifier with the number makes press/type/release one Sikuli action.
    Explicit keyUp calls clean up any modifier left behind by an interrupted action.
    """
    type_value = globals()["type"]
    key = globals()["Key"]

    for candidate in (key.CMD, key.CTRL):
        try:
            globals()["keyUp"](candidate)
        except Exception:
            pass
    try:
        type_value(str(number), key.CMD)
    finally:
        try:
            globals()["keyUp"](key.CMD)
        except Exception:
            pass

    globals()["wait"](TAB_SETTLE_SECONDS)
    type_value(key.END)
    globals()["wait"](1)


def release_all_keys():
    """Release every modifier before a shortcut or submission retry."""
    key_up = globals().get("keyUp")
    if not key_up:
        return
    try:
        key_up()
        return
    except Exception:
        pass
    key = globals().get("Key")
    if not key:
        return
    for name in ("CMD", "CTRL", "SHIFT", "ALT"):
        modifier = getattr(key, name, None)
        if modifier is not None:
            try:
                key_up(modifier)
            except Exception:
                pass


def park_mouse():
    """Move the pointer off action buttons so hover styling cannot foil matching."""
    try:
        center_mouse()
    except Exception:
        pass


def capture_ui_diagnostic(label):
    """Save the lower browser area for post-mortem UI-state inspection."""
    screen = globals().get("SCREEN")
    if screen is None:
        return None
    try:
        if not os.path.isdir(DIAGNOSTICS_PATH):
            os.makedirs(DIAGNOSTICS_PATH)
        height = min(420, int(screen.h))
        image = screen.capture(0, int(screen.h) - height, int(screen.w), height)
        filename = "%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), label)
        path = image.save(DIAGNOSTICS_PATH, filename)
        log("saved UI diagnostic: %s" % path)
        return path
    except Exception as error:
        log("could not save UI diagnostic %s: %s" % (label, error))
        return None


def image_exists(filename, timeout=None):
    timeout = IMAGE_TIMEOUT_SECONDS if timeout is None else timeout
    return globals()["exists"](os.path.join(SCRIPT_DIR, filename), timeout)


def click_image(filename, timeout=None):
    match = image_exists(filename, timeout)
    if not match:
        return False
    globals()["click"](match)
    return True


def recover_long_conversation(agent_name, registry):
    """Start a fresh chat when the conversation-length action is visible."""
    if not image_exists("new_chat.png", UI_STATE_TIMEOUT_SECONDS) or \
            not click_image("new_chat.png", UI_STATE_TIMEOUT_SECONDS):
        return False
    globals()["wait"](2)
    task_id = get_agent_task(agent_name, registry)
    if task_id:
        info = registry["tasks"][task_id]
        info["last_prompted"] = 0
        info["prompt_count"] = 0
        info["prompt_confirmed"] = False
        log("%s reached the conversation limit; started a new chat for %s" % (
            agent_name, task_id))
    else:
        log("%s reached the conversation limit; started a new idle chat" % agent_name)
    return True


def task_prompt(number, task_id, work_kind=None):
    name = agent_id(number)
    branch_name = feature_branch(number)
    ci_branch_name = ci_branch(number)
    work_kind = work_kind or scene_work_kind(task_id)
    if work_kind == FEATURE_WORK_KIND:
        directions = ("Follow `SceneIssues/feature-readme.md`. Before implementation, create and "
                      "maintain separate `plan.md` and `tasks.md` files in the assigned folder. "
                      "Add discovered required work to `tasks.md`; do not close the feature until "
                      "every checkbox and acceptance criterion is complete and validated.")
    else:
        directions = ("Follow `SceneIssues/issue-readme.md`. Inspect every capture and marked "
                      "region, discriminate competing hypotheses with runtime evidence, add a "
                      "behavioral regression, and validate the exact scene in the built application.")
    return """You are {name}. Work only on the {work_kind} assignment `SceneIssues/open/{task_id}` on `{branch}`; use `{ci_branch}` only for its final targeted-CI request. Fetch origin and resume the feature branch, or create it from current `origin/master`.

Follow `AGENTS.md`. {directions} Check blast radius and cost.

After every workflow gate and green exact-SHA CI, complete pending metadata on `{branch}`. Then move `SceneIssues/pending/{task_id}` to `SceneIssues/closed/{task_id}`, set status=`fixed` and `resolvedUtc`, merge current `origin/master` into `{branch}`, and push that exact branch head to `origin/master` non-force. If master advanced, fetch, merge, and retry. Do not modify another assignment, edit `.github/test-request.json` on the feature branch, create extra CI transports, replace queued CI, or self-select more work.""".format(
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
        return ("%s is fixed but `%s` is missing. Create its final request commit directly on the "
                "source containing fixCommit %s, update that CI ref once, and monitor "
                "`ci/single-test`." % (task_id, ci_branch_name, fix_commit))
    if state == "missing_fix":
        return ("%s is fixed, but `%s` at %s does not contain fixCommit %s. Create one fresh "
                "request on the correct source, update the CI ref once, and monitor it." % (
                    task_id, ci_branch_name, ci_head, fix_commit))
    if state == "not_created":
        return ("%s has no `ci/single-test` status for `%s` at %s. Check for an exact-SHA Actions "
                "run. Leave queued/running work alone; only after the documented admission window "
                "may you update the assigned CI ref once. Do not use another transport." % (
                    task_id, ci_branch_name, ci_head))
    if state in ("queued", "in_progress", "waiting", "requested", "pending"):
        return ("%s: `%s` at %s is %s. Monitor that exact request without replacing it." % (
                    task_id, ci_branch_name, ci_head, state))
    if state in ("failure", "error", "cancelled", "timed_out", "action_required"):
        return ("%s: `%s` at %s reported `ci/single-test=%s`. Inspect the run and artifact. For "
                "infrastructure failure, wait and retry once; for product failure, fix it. Then "
                "create one fresh final request and update the assigned CI ref once." % (
                    task_id, ci_branch_name, ci_head, state))
    checklist = (" Keep `plan.md` and `tasks.md` separate and current; do not close with any "
                 "unchecked task." if work_kind == FEATURE_WORK_KIND else "")
    return ("Continue only the %s assignment `SceneIssues/open/%s` on `%s`; follow `%s`.%s Once "
            "verified, close the assignment and merge your branch to master." % (
                work_kind, task_id, feature_branch(number), guide, checklist))


def message_for_nudge(number, task_id, info, started_new_chat=False):
    """Choose enough context for a normal nudge or a freshly restarted chat."""
    if info.get("completion_gate"):
        return continuation_prompt(number, task_id, info)
    activity = info.get("ci_activity") or {}
    if activity.get("state") in ("queued", "in_progress", "waiting", "requested", "pending"):
        return ("Continue only scene assignment %s. Its exact targeted-CI request `%s` is `%s`; "
                "monitor it without replacing it, then close and merge the assignment yourself." % (
                    task_id, activity.get("ci_head") or "<unknown>", activity.get("state")))
    if started_new_chat or not float(info.get("last_prompted") or 0):
        return task_prompt(number, task_id, info.get("work_kind"))
    return continuation_prompt(number, task_id, info)


def focus_textbox():
    """Focus either an empty composer or one whose placeholder is hidden by text."""
    match = image_exists("textbox.png", UI_STATE_TIMEOUT_SECONDS)
    if match:
        globals()["click"](match)
        return True

    submit = image_exists("submit.png", UI_STATE_TIMEOUT_SECONDS)
    if not submit:
        return False
    try:
        center = submit.getCenter()
        target = globals()["Location"](center.x - 180, center.y)
    except Exception:
        return False
    globals()["click"](target)
    return True


def composer_visible():
    """Recognize both the empty placeholder and a non-empty, submittable draft."""
    if image_exists("textbox.png", UI_STATE_TIMEOUT_SECONDS):
        return True
    return bool(image_exists("submit.png", UI_STATE_TIMEOUT_SECONDS))


def replace_composer_text(text):
    """Replace stale drafts or leaked tab digits instead of appending to them."""
    if not focus_textbox():
        return False
    key = globals()["Key"]
    try:
        globals()["type"]("a", key.CMD)
    finally:
        try:
            globals()["keyUp"](key.CMD)
        except Exception:
            pass
    paste_value = globals().get("paste")
    if paste_value:
        paste_value(text)
    else:
        globals()["type"](text)
    # A long clipboard paste can reach the browser before React enables Submit.
    globals()["wait"](2)
    return True


def submit_current_message():
    """Click Submit, then use Enter if the click did not start a response."""
    clicked = click_image("submit.png", UI_STATE_TIMEOUT_SECONDS)
    park_mouse()
    if clicked and image_exists(RUNNING_IMAGE, 4):
        return True

    log("Submit click was not confirmed; retrying from the textbox with Enter")
    if focus_textbox():
        release_all_keys()
        globals()["type"](globals()["Key"].ENTER)
        park_mouse()
    if image_exists(RUNNING_IMAGE, 8):
        return True

    # One final click covers a composer that enabled Submit only after the Enter retry.
    clicked = click_image("submit.png", 2)
    park_mouse()
    if clicked and image_exists(RUNNING_IMAGE, 5):
        return True

    return False


def send_message(text):
    if not replace_composer_text(text):
        return False
    if submit_current_message():
        return True
    log("message submission was not confirmed by a running-response control")
    return False


def center_mouse():
    screen = globals()["SCREEN"]
    location = globals()["Location"]
    globals()["mouseMove"](location(screen.w / 2, screen.h / 2))


# ---------------- COORDINATOR ----------------

def validate_configuration():
    problems = []
    if not os.path.isdir(REPO_PATH):
        problems.append("repository does not exist: %s" % REPO_PATH)
    if not os.path.isdir(SCENE_ISSUES_PATH):
        problems.append("SceneIssues directory does not exist: %s" % SCENE_ISSUES_PATH)
    if not os.path.isdir(OPEN_SCENE_ISSUES_PATH):
        problems.append("open SceneIssues queue does not exist: %s" % OPEN_SCENE_ISSUES_PATH)
    if not os.path.isdir(PENDING_SCENE_ISSUES_PATH):
        problems.append("pending SceneIssues queue does not exist: %s" %
                        PENDING_SCENE_ISSUES_PATH)
    for image in ("textbox.png", "submit.png", RUNNING_IMAGE, "new_chat.png",
                  "got_it.png", "connection_lost.png", "refresh.png"):
        path = os.path.join(SCRIPT_DIR, image)
        if not os.path.isfile(path):
            problems.append("missing UI image: %s" % path)
    if NUM_AGENTS < 1 or NUM_AGENTS > 9:
        problems.append("NUM_AGENTS must be between 1 and 9 for Cmd+number tab selection")
    if problems:
        raise RuntimeError("\n".join(problems))


def sync_remote_and_registry(registry):
    fetch_remote()
    changed = refresh_ci_activity(registry)
    if reconcile_assignments(registry):
        changed = True
    if changed:
        save_registry(registry)
    return list_open_tasks()


def handle_tab(number, registry, open_tasks):
    name = agent_id(number)
    switch_to_tab(number)
    started_new_chat = recover_long_conversation(name, registry)
    task_id = get_agent_task(name, registry)

    if image_exists("connection_lost.png", UI_STATE_TIMEOUT_SECONDS):
        log("%s has a connection interruption; refreshing" % name)
        click_image("refresh.png", 2)
        globals()["wait"](2)
        return
    if image_exists("got_it.png", UI_STATE_TIMEOUT_SECONDS) and \
            click_image("got_it.png", UI_STATE_TIMEOUT_SECONDS):
        park_mouse()
        globals()["wait"](TAB_SETTLE_SECONDS)
        capture_ui_diagnostic("got-it-dismissed-agent-%d" % number)
        if not task_id:
            log("%s dismissed Got it but has no current assignment; restored draft was not sent" %
                name)
            # Fall through so the normal idle-agent path can claim a new task now.
        else:
            # ChatGPT may restore a draft from an earlier assignment. Never submit it
            # blindly: replace it with the registry's current task and branch context.
            info = registry["tasks"][task_id]
            text = message_for_nudge(number, task_id, info, started_new_chat=True)
            mark_prompt_attempted(task_id, registry)
            submitted = send_message(text)
            if not submitted:
                capture_ui_diagnostic("got-it-submit-unconfirmed-agent-%d" % number)
                submit_visible = bool(image_exists("submit.png", 0))
                textbox_visible = bool(image_exists("textbox.png", 0))
                running_visible = bool(image_exists(RUNNING_IMAGE, 0))
                log("%s post-Got-it submission unconfirmed: textbox=%s submit=%s running=%s" % (
                    name, textbox_visible, submit_visible, running_visible))
                if textbox_visible and submit_visible and not running_visible:
                    # This is the observed failure state: the correct text is present and
                    # Submit is enabled, but the first action was lost. Let the settled UI
                    # breathe once more and submit the existing text without repasting it.
                    globals()["wait"](2)
                    submitted = submit_current_message()

            if submitted:
                heartbeat(task_id, registry)
                mark_prompted(task_id, registry)
                mark_response_active(task_id, registry)
                log("%s replaced the restored draft and resumed %s" % (name, task_id))
            else:
                capture_ui_diagnostic("got-it-submit-failed-agent-%d" % number)
                log("%s post-Got-it submission failed after the settled-state retry" % name)
            return

    busy = bool(image_exists(RUNNING_IMAGE, UI_STATE_TIMEOUT_SECONDS))

    if busy:
        if task_id:
            heartbeat(task_id, registry)
            mark_response_active(task_id, registry)
        return

    if not task_id:
        if branch_has_unmerged_work(feature_branch(number)):
            log("%s is idle but %s has unmerged work; assigning nothing" % (
                name, feature_branch(number)))
            return
        task_id = claim_new_task(
            name, feature_branch(number), ci_branch(number), registry, open_tasks)
        if not task_id:
            return
        mark_prompt_attempted(task_id, registry)
        save_registry(registry)
        if send_message(task_prompt(number, task_id)):
            heartbeat(task_id, registry)
            mark_prompted(task_id, registry)
            mark_response_active(task_id, registry)
            save_registry(registry)
            log("%s claimed %s on %s" % (name, task_id, feature_branch(number)))
        else:
            log("%s claimed %s but its textbox was not visible; will retry" % (name, task_id))
        return


    textbox_visible = composer_visible()
    if textbox_visible:
        heartbeat(task_id, registry)
    info = registry["tasks"][task_id]
    became_idle = response_became_idle(info, textbox_visible)
    if started_new_chat or became_idle or should_nudge(info):
        text = message_for_nudge(number, task_id, info, started_new_chat)
        mark_prompt_attempted(task_id, registry)
        if textbox_visible and send_message(text):
            mark_prompted(task_id, registry)
            mark_response_active(task_id, registry)
            log("nudged %s on %s" % (name, task_id))


def coordinator_loop():
    validate_configuration()
    #acquire_process_lock()
    atexit.register(release_process_lock)
    configure_ui()

    registry = load_registry()
    last_fetch = 0
    open_tasks = []
    log("coordinator started for %d agents; registry=%s" % (NUM_AGENTS, REGISTRY_PATH))

    while True:
        try:
            now = time.time()
            if now - last_fetch >= FETCH_INTERVAL_SECONDS:
                try:
                    open_tasks = sync_remote_and_registry(registry)
                    last_fetch = now
                    log("remote queue has %d open task(s)" % len(open_tasks))
                except Exception as error:
                    log("remote sync failed; coordinator is exiting: %s" % error)
                    traceback.print_exc()
                    return

            for number in range(1, NUM_AGENTS + 1):
                try:
                    handle_tab(number, registry, open_tasks)
                    save_registry(registry)
                except Exception as error:
                    log("tab %d failed: %s" % (number, error))
                    traceback.print_exc()
                finally:
                    try:
                        center_mouse()
                    except Exception:
                        pass
            globals()["wait"](POLL_WAIT_SECONDS)
        except KeyboardInterrupt:
            log("coordinator stopped")
            return


def check_only():
    validate_configuration()
    fetch_remote()
    tasks = list_open_tasks()
    registry = load_registry()
    reconcile_assignments(registry)
    log("configuration is valid; %d open remote task(s): %s" % (
        len(tasks), ", ".join(tasks) if tasks else "none"))


if __name__ == "__main__":
    if "--check" in sys.argv:
        check_only()
    else:
        coordinator_loop()
