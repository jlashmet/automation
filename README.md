# Scene-issue agent coordinator

`auto.py` coordinates up to nine browser-tab workers for `jlashmet/mounting-force-2`.

The automation repo owns only coordination mechanics: tab assignment, durable assignment ownership, CI activity detection, and concise nudges. It does not define the SceneIssue development/validation/merge workflow. Workers must read the Mounting Force repository's `AGENTS.md`, `SceneIssues/README.md`, and the assignment-specific issue/feature guide; those files are authoritative.

The old `jlashmet/voxel` repository is no longer an automation target.

## Target and safety guard

The default checkout is:

```text
/Users/jlashmet/code/mounting-force-2
```

Set `MOUNTING_FORCE_REPO_PATH` only when that checkout lives elsewhere. On startup the coordinator reads the checkout's `origin` URL and refuses to run unless it resolves to `jlashmet/mounting-force-2`; this prevents an old path from sending work into another repository.

`MOUNTING_FORCE_ASSIGNMENT_BRANCH` may override the default durable coordination branch `automation/assignments`.

## State

Queue state comes from `origin/master` in Mounting Force:

- `SceneIssues/open/` — available or active work.
- `SceneIssues/closed/` — completed work on master.

Durable worker ownership is stored in each open SceneIssue's `issue.json` on the repository's `automation/assignments` coordination branch. UI heartbeat/backoff state is process-local. This lets the coordinator move between computers without copying a local registry file.

Each browser slot reuses:

```text
fixes/agent-N
ci-test/fixes/agent-N
```

The coordinator does not invent extra feature or CI branches.

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

## CI prerequisite

Mounting Force contains `.github/workflows/tests-single.yml`. Its exact-SHA validation job uses a self-hosted macOS runner with the project's Unity version installed and runs:

```sh
./Scripts/validate.sh
./Scripts/validate-engine.sh
```

Because self-hosted runner registration is repository-scoped unless configured at a broader GitHub account/organization level, make sure the Mac runner used for this automation is registered/available to `jlashmet/mounting-force-2`. A runner still registered only to the retired voxel repository will not pick up these jobs.

## Prompt policy

`auto.py` intentionally sends short prompts containing only assignment identity/state and links back to the Mounting Force workflow docs. Final implementation, testing, exact-SHA CI behavior, acceptance rules, and closure rules belong in `mounting-force-2`, not duplicated here.

`auto_runtime.py` and `auto_core.py` retain the reusable coordinator/state implementation; `auto.py` is the target binding and prompt-policy layer.
