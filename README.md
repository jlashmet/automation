# Scene-issue agent coordinator

`auto.py` coordinates up to nine browser-tab workers for `jlashmet/mounting-force-2`.

The automation repo owns coordination mechanics and the worker execution policy. Workers must also read the Mounting Force repository's `AGENTS.md`, `SceneIssues/README.md`, and the assignment-specific issue/feature guide.

The old `jlashmet/voxel` repository is no longer an automation target.

## Target and safety guard

The default checkout is:

```text
/Users/jlashmet/code/mounting-force-2
```

Set `MOUNTING_FORCE_REPO_PATH` only when that checkout lives elsewhere. On startup the coordinator reads the checkout's `origin` URL and refuses to run unless it resolves to `jlashmet/mounting-force-2`; this prevents an old path from sending work into another repository.

`MOUNTING_FORCE_ASSIGNMENT_BRANCH` may override the durable coordination branch `automation/assignments`. That branch is coordinator state only; agents do not develop on it.

## State

Queue state comes from `origin/master` in Mounting Force:

- `SceneIssues/open/` — available or active work.
- `SceneIssues/closed/` — completed work on master.

Durable worker ownership is stored in each open SceneIssue's `issue.json` on the repository's `automation/assignments` coordination branch. UI heartbeat/backoff state is process-local. This lets the coordinator move between computers without copying a local registry file.

## Agent execution policy

All agents now work directly on the shared `master` branch.

Agents must:

- use the **Chat on Steroids** plugin for repository interaction, including reading and editing code/files, running shell commands, and running tests;
- expect occasional transient Chat on Steroids failures (including temporarily unavailable/disabled/conflicted errors) and keep retrying the same operation rather than abandoning the plugin or switching workflows;
- work directly on `master` and **not** create or use `fixes/agent-N`, feature branches, CI branches, transport branches, or other per-agent development branches;
- pull/reconcile the latest `origin/master` before beginning work, without discarding another agent's valid changes;
- **periodically pull from `origin/master` while working** so they remain current with changes from other agents;
- resolve merge conflicts carefully and preserve valid changes from both their assignment and other agents;
- keep edits scoped to the assigned SceneIssue;
- run the relevant tests through Chat on Steroids and fix failures caused by their work;
- keep incomplete or blocked SceneIssues under `SceneIssues/open/`;
- close a SceneIssue only after all required acceptance work is genuinely complete;
- immediately before committing/pushing completed work, pull/reconcile `origin/master` again, resolve any conflicts, and rerun affected tests if reconciliation changed code;
- commit completed work directly on `master` and push it to `origin/master` non-force;
- if `origin/master` advances before push, reconcile the new master and retry rather than force-pushing.

The coordinator's `automation/assignments` branch remains only a durable claim/state mechanism. It must not be treated as an agent development branch.

## Run

```sh
cd /Users/jlashmet/automation
./run.sh
```

Or invoke Oculix directly:

```sh
cd /Users/jlashmet/automation
java -jar oculixide-4.0.0-macos.jar -c -r auto.py
```

Do not intentionally run two coordinators at once.

## Validate without driving the browser

```sh
cd /Users/jlashmet/automation
java -jar oculixide-4.0.0-macos.jar -c -r auto.py -- --check
python3 -m unittest -v test_auto.py test_assignment_persistence.py test_prompt_policy.py
```

`--check` also exercises the target-repository guard, so a stale or incorrect checkout fails before any browser tab is touched.

## Prompt policy

`auto.py` sends assignment identity plus the execution policy above. The prompts explicitly require Chat on Steroids, direct work on `master`, periodic reconciliation with `origin/master`, conflict resolution, local test execution through the plugin, and a non-force push to `origin/master` only after the assigned SceneIssue is complete.

`auto_runtime.py` and `auto_core.py` retain the reusable coordinator/state implementation; `auto.py` is the target binding and prompt-policy layer.
