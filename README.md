# Scene-issue agent coordinator

`auto.py` drives up to nine Oculix/Sikuli browser tabs while using GitHub as the source of truth
for the `SceneIssues/open/` queue, verified captures under `SceneIssues/pending/`, and completed
captures under `SceneIssues/closed/`.

## Before starting

1. Put the remote-agent conversations in browser tabs 1 through 9. Keep that browser as the
   foreground application; the script selects tabs with `Cmd+1` through `Cmd+9`.
2. Ensure Java/Oculix has macOS Accessibility and Screen Recording permission.
3. Ensure `/Users/jlashmet/code/voxel` exists, `origin` is configured, and `gh auth status` succeeds.
4. Run the repository-root `./push_scene_issues.sh` from an up-to-date local `master` to publish
   newly captured issues. The coordinator intentionally reads `SceneIssues/open/` from the remote
   branch, not from uncommitted local files.

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

Stop it with `Ctrl+C`. It writes `_registry.json` beside the script. Run only one coordinator
instance; this setup intentionally does not enforce a process lock.

Each browser slot reuses its own feature and CI branches:

```text
fixes/agent-1              ci-test/fixes/agent-1
fixes/agent-2              ci-test/fixes/agent-2
...
```

The oldest unclaimed capture under `origin/master:SceneIssues/open/` is assigned first. A visible
running-response control or input box renews the task lease. A task whose tab has not been
observable for one hour may be reassigned only when the former owner's feature branch has no work
outside `origin/master`. Otherwise the registry records that an explicit handoff is required and
leaves the lease in place so unfinished work is not silently stacked beneath another assignment.

After selecting a tab, the coordinator scrolls to the bottom. If the conversation-length screen is
visible, it clicks **Start new chat**, resets that task's prompt backoff, and sends either the full
assignment or the task's current coordinator gate into the fresh conversation.
Prompt backoff advances only after the running-response control confirms that submission started;
an unconfirmed click is retried instead of being recorded as a successful instruction.

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
- `verification-final.png` exists in the pending capture;
- the feature-only diff contains no other capture, CI request file, or workflow;
- the paired CI request branch contains `fixCommit`; and
- the CI branch head has a successful `ci/single-test` commit status;
- after targeted CI succeeds, the same worker moves the capture from `pending/` to `closed/`, sets
  `status: fixed` and `resolvedUtc`, and commits that bookkeeping on its feature branch;
- the worker merges current `origin/master` into its feature branch and pushes the exact feature
  head to `origin/master` non-force; and
- master contains the fix and capture only under `SceneIssues/closed/`.

CI request branches are updated atomically: construct the final request commit directly on the
feature SHA being tested, then force-update the assigned CI ref once. Do not publish an
intermediate reset/template head because that is another push event and can later cancel the real
request when GitHub admits events out of order.

Workers promote their own completed issues. If another worker advances master first, the worker
fetches and merges the new master into its feature branch, then retries the non-force master push.
The coordinator releases the tab and assigns another capture after it observes the fixed capture
under `SceneIssues/closed/` on master. A blocked capture remains in `open/`; it is not complete.

Do not delete or hand-edit `_registry.json` while the coordinator or remote workers are active. If
recovery is necessary, stop the coordinator first and preserve a copy of the registry so active
assignments are not duplicated.
