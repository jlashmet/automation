# Scene-issue agent coordinator

`auto.py` coordinates up to nine browser-tab workers for `jlashmet/mounting-force-unreal`.

The automation repo owns coordination mechanics and the worker execution policy. Workers also follow the Unreal repository's `CLAUDE.md` and `SceneIssues/README.md`.

The old `jlashmet/voxel` repository is no longer an automation target.

## Target and safety guard

The default checkout is:

```text
/Users/jlashmet/Documents/Unreal Projects/MountingForce
```

Set `MOUNTING_FORCE_REPO_PATH` only when that checkout lives elsewhere. On startup the coordinator reads the checkout's `origin` URL and refuses to run unless it resolves to `jlashmet/mounting-force-unreal`; this prevents the retired Unity checkout from receiving work.

`MOUNTING_FORCE_ASSIGNMENT_BRANCH` may override the durable coordination branch `automation/assignments`. That branch is coordinator state only; agents do not develop on it.

## State

Queue state comes from `origin/main` in Mounting Force Unreal:

- `SceneIssues/open/` — available or active work.
- `SceneIssues/pending/` — self-reviewed work awaiting an independent review assignment; selected before open work.
- `SceneIssues/closed/` — reviewer-accepted work on main.

Durable worker ownership is stored in each open or pending SceneIssue's `issue.json` on the repository's `automation/assignments` coordination branch. UI heartbeat/backoff state is process-local. This lets the coordinator move between computers without copying a local registry file.

## Agent execution policy

Agents work in disposable SceneIssue worktrees based on `origin/main`. They do not modify or clean the primary checkout, which may contain unrelated user work. Each assignment has a durable `implementer` or `reviewer` role. Folder transitions release the previous role, including across coordinator restarts.

Agents must:

- use the **Chat on Steroids** plugin for repository interaction, including reading and editing code/files, running shell commands, and running tests;
- expect occasional transient Chat on Steroids failures (including temporarily unavailable/disabled/conflicted errors) and keep retrying the same operation rather than abandoning the plugin or switching workflows;
- work in `.worktrees/<SceneIssue-directory-name>` detached from current `origin/main`; **do not** create or use `fixes/agent-N`, feature branches, CI branches, transport branches, or other per-agent development branches;
- fetch/reconcile the latest `origin/main` before beginning work, without discarding another agent's valid changes;
- **periodically reconcile from `origin/main` inside the isolated worktree while working** so they remain current with changes from other agents; this does not publish their work to main;
- resolve merge conflicts carefully and preserve valid changes from both their assignment and other agents;
- keep edits scoped to the assigned SceneIssue;
- run the relevant tests through Chat on Steroids and fix failures caused by their work;
- keep incomplete or blocked SceneIssues under `SceneIssues/open/`;
- never merge, push, cherry-pick, or otherwise publish partial feature work to `origin/main` after individual tasks, milestones, checkpoints, or partial test passes;
- implementers complete acceptance and self-review, record candidate/evidence in `review.md`, and move to `pending` with `status=pending`;
- reviewers inspect implementation and evidence, then accept into `closed` with fixed/resolved metadata or return to `open` with detailed actionable feedback in `review.md`;
- only after the entire SceneIssue feature is complete, every required acceptance criterion is satisfied, all required focused/runtime tests and repository gates are green, and final self-review is complete, fetch/reconcile `origin/main` again;
- resolve any final conflicts and rerun affected tests if reconciliation changed code, then commit in the assigned worktree and perform the single final promotion of the verified detached HEAD to `origin/main` non-force;
- if `origin/main` advances before push, reconcile and retry rather than force-pushing.

The coordinator's `automation/assignments` branch remains only a durable claim/state mechanism. It must not be treated as an agent development branch.

## Conversation handoffs

Workers maintain a compact local continuation snapshot in `_handoffs/<SceneIssue>.md`. The file is coordinator-owned transient state, is ignored by Git, and is rewritten rather than appended. Worker prompts require the snapshot to stay under 6,000 characters and to capture only current objective/progress, important findings, changed files, validation, blockers, relevant repository state, and the exact next step.

When the ChatGPT conversation-length UI offers **New Chat**, the coordinator starts the new conversation with the normal complete assignment prompt plus the saved handoff. The coordinator independently caps injected handoff text at 6,000 characters (preserving both the beginning and end if it must truncate) and tells the new chat to verify the summary against current repository state. Missing handoffs simply fall back to the normal fresh-assignment prompt. Handoffs are removed when an assignment changes phase or reaches terminal state.

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
python3 -m unittest -v test_auto.py test_assignment_persistence.py test_prompt_policy.py test_folder_state.py
```

`--check` also exercises the target-repository guard, so a stale or incorrect checkout fails before any browser tab is touched.

## Prompt policy

`auto.py` sends assignment identity plus the execution policy above. The prompts explicitly require Chat on Steroids, isolated worktrees and role-specific review decisions, periodic reconciliation **from** `origin/main`, conflict resolution, Unreal validation through the plugin, and no promotion to `origin/main` until the entire SceneIssue feature is complete, tested, gated and self-reviewed.

`auto_runtime.py` and `auto_core.py` retain the reusable coordinator/state implementation; `auto.py` is the target binding and prompt-policy layer.
