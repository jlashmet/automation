# Scene-issue agent coordinator

`auto.py` coordinates up to nine browser-tab workers for `jlashmet/voxel`.

The automation repo owns only coordination mechanics: tab assignment, durable assignment ownership, CI activity detection, and concise nudges. **It does not define the SceneIssue development/validation/merge workflow.** Workers must read the voxel repository's `AGENTS.md`, `SceneIssues/README.md`, and the assignment-specific issue/feature guide. Those files are authoritative.

## State

Queue state comes from `origin/master` in the voxel repo:

- `SceneIssues/open/` — available or active work
- `SceneIssues/closed/` — completed work on master

Durable worker ownership is stored in each open SceneIssue's `issue.json` on the voxel repo's `automation/assignments` coordination branch. UI heartbeat/backoff state is process-local. This lets the coordinator move between computers without copying a local registry file.

Each browser slot reuses:

```text
fixes/agent-N
ci-test/fixes/agent-N
```

The coordinator does not invent extra feature or CI branches.

## Run

The historical voxel clone path is `/Users/jlashmet/code/voxel`; set `VOXEL_REPO_PATH` when it differs. `VOXEL_ASSIGNMENT_BRANCH` may override `automation/assignments`.

```sh
cd /Users/jlashmet/automation
java -jar oculixide-4.0.0-macos.jar -c -r auto.py
```

Do not intentionally run two coordinators at once.

## Validate without driving the browser

```sh
cd /Users/jlashmet/automation
java -jar oculixide-4.0.0-macos.jar -c -r auto.py -- --check
python3 -m unittest -v test_auto.py test_assignment_persistence.py
```

## Prompt policy

`auto.py` intentionally sends short prompts containing only assignment identity/state and links back to the voxel repo workflow docs. Final implementation, testing, PR/auto-merge behavior, retry policy, acceptance rules, and closure rules belong in the voxel repo, not duplicated here.

`auto_runtime.py` contains the existing coordinator/state implementation; `auto.py` is the small entrypoint/prompt-policy layer.
