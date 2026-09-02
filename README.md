# Scene-issue agent coordinator

`auto.py` drives up to nine Oculix/Sikuli browser tabs while using GitHub as the source of truth
for the `SceneIssues/open/` queue, verified captures under `SceneIssues/pending/`, completed
captures under `SceneIssues/closed/`, and active agent assignment ownership stored in each open
issue's `issue.json` on the voxel repository's `automation/assignments` coordination branch.

## Before starting

1. Put the remote-agent conversations in browser tabs 1 through 9. Keep that browser as the
   foreground application. The script selects each exact tab with an atomic `Cmd+number`
   shortcut so the permanent agent-to-tab mapping survives restarts and missed UI actions. It
   allows five seconds for the selected tab to settle before inspecting it.
2. Ensure Java/Oculix has macOS Accessibility and Screen Recording permission.
3. Ensure the voxel repository exists, `origin` is configured, and `gh auth status` succeeds.
   The historical default is `/Users/jlashmet/code/voxel`; set `VOXEL_REPO_PATH` when the clone is
   elsewhere on another computer. `VOXEL_ASSIGNMENT_BRANCH` may override the default
   `automation/assignments` coordination branch when needed.
4. Run the repository-root `./push_scene_issues.sh` from an up-to-date local `master` to publish
   newly captured issues. Queue state is read from `origin/master`, not from uncommitted local files.

## Validate without driving the browser

```sh
cd /Users/jlashmet/automation
java -jar oculixide-4.0.0-macos.jar -c -r auto.py -- --check
python3 -m unittest -v test_auto.py
```

## Run

```sh
cd /Users/jlashmet/automation
java -jar oculixide-4.0.0-macos.jar -c -r auto.py
```

Stop it with `Ctrl+C`. Durable assignment state is not stored beside the automation script. The
coordinator writes an `assignment` object into the authoritative open SceneIssue `issue.json` on
`origin/automation/assignments` before prompting a newly claimed worker. On startup it fetches the
voxel repo and reconstructs ownership from those manifests, so the coordinator can be stopped on
one computer and started from another clone without copying a registry file. UI heartbeat,
prompt-backoff, and tab activity remain process-local runtime state. Do not intentionally run two
coordinators at once.

The coordination branch exists because voxel `master` is protected and requires pull-request CI.
Assignment claims must not wait for or generate a protected-master PR. Queue status still comes only
from `origin/master`; the coordination branch is a durable overlay containing the same SceneIssue
manifests plus assignment metadata. Every assignment commit rebuilds its tree from current master,
then reapplies active assignments, so normal feature/queue content does not become independently
owned by the coordination branch.

Each browser slot reuses its own feature and CI branches:

```text
fixes/agent-1              ci-test/fixes/agent-1
fixes/agent-2              ci-test/fixes/agent-2
...
```

The oldest unclaimed capture under `origin/master:SceneIssues/open/` is assigned first. A visible
running-response control or input box renews the task's in-memory UI lease. A task whose tab has not
been observable for one hour in the running coordinator may be reassigned only when the former
owner's feature branch has no work outside `origin/master`. Otherwise the coordinator leaves
ownership in place so unfinished work is not silently stacked beneath another assignment.
Assignment claims themselves are durable in the issue manifest and survive coordinator restarts.

Assignment writes do not check out or modify the local voxel worktree. The coordinator constructs a
new `automation/assignments` commit with a temporary Git index and pushes it non-force. If another
coordinator changed the same issue assignment after the local snapshot, the newer remote assignment
wins rather than double-claiming the issue. Heartbeat and UI-only changes do not create Git commits.

After selecting a tab, the coordinator scrolls to the bottom. If the conversation-length screen is
visible, it clicks **Start new chat**, resets that task's prompt backoff, and sends either the full
assignment or the task's current coordinator gate into the fresh conversation.
If ChatGPT then shows **Got it** with a prefilled message, the coordinator dismisses the notice but
does not trust the restored draft. It replaces the composer with the assignment currently owned by
that exact agent, or submits nothing when the tab has no current assignment. It waits five seconds
for the post-dialog composer to settle and moves the pointer away from the action button before
checking whether generation started. A failed transition saves lower-screen diagnostics under
`_diagnostics/` and logs whether the textbox, Submit button, and running control were visible.
Prompt backoff advances only after the running-response control confirms that submission started;
an unconfirmed click is retried with Enter and remains immediately retryable instead of being
recorded as a successful instruction. Before pasting, the coordinator selects the entire composer
contents so a stale draft or leaked tab-switch digit cannot contaminate the next instruction.
Key browser states use five-second image searches, retaining the original script's tolerance for
slow tab rendering.
The composer is considered available when either the empty **Ask ChatGPT** placeholder or the blue
Submit button is visible. This allows restored, non-empty drafts to be focused and replaced even
though entering text hides the placeholder image.
Running-state detection uses a separate crop containing only the white Stop square at 0.95 image
similarity. The shared blue-circle background can therefore no longer make the Submit arrow look
like a running response.

Idle agents are nudged with a ten-to-thirty-minute exponential backoff. A known queued or running
targeted-CI request suppresses nudges entirely. The coordinator looks up the exact request SHA in
GitHub Actions so a job waiting for the shared self-hosted runner is not mistaken for a missing
workflow and needlessly reissued.

When a running response finishes and the **Ask ChatGPT** input returns, the coordinator sends the
next continuation immediately. The backoff applies only when a tab was already idle; it does not
leave a newly finished agent waiting.

For a completed issue, the coordinator waits until all of these are visible after a fetch:

- the assigned remote feature branch moves the capture from `open/` to `pending/` and marks it `pending`;
- `resolutionSummary`, `regressionTest`, and `fixCommit` are populated;
- `fixCommit` is an ancestor of that feature branch;
- the feature-only diff contains no other capture, CI request file, or workflow;
- the paired CI request branch contains `fixCommit`; and
- the CI branch head has a successful `ci/single-test` commit status;
- after targeted CI succeeds, the same worker moves the capture from `pending/` to `closed/`, sets
  `status: fixed` and `resolvedUtc`, and commits that bookkeeping on its feature branch;
- the worker merges current `origin/master` into its feature branch and pushes the exact feature
  head to `origin/master` through the repository's accepted promotion path; and
- master contains the fix and capture only under `SceneIssues/closed/`.

CI request branches are updated atomically: construct the final request commit directly on the
feature SHA being tested, then force-update the assigned CI ref once. Do not publish an
intermediate reset/template head because that is another push event and can later cancel the real
request when GitHub admits events out of order.

The coordinator releases the tab and assigns another capture after it observes the fixed capture
under `SceneIssues/closed/` on master. A blocked capture remains in `open/`; it is not complete.
Closed/pending master state always overrides stale assignment metadata on the coordination branch.
