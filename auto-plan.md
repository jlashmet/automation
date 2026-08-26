# Scene-Issue Agent Coordinator Plan

## Goal

Finish the local Oculix/Sikuli coordinator so multiple remote agents can safely claim open
`SceneIssues` captures, work independently through GitHub, and receive another task after their
published issue is complete.

The queue layout was subsequently refined: new and non-terminal captures live under
`SceneIssues/open/`, while only `status: fixed` captures live under `SceneIssues/closed/`. As of
2026-08-26, workers close and merge their own verified issues; there is no coordinator promotion
batch, review branch, pull request, or human-approval gate.

## Scope and constraints

- The coordinator runs locally from `/Users/jlashmet/automation/` and drives nine browser tabs.
- The repository is `/Users/jlashmet/code/voxel`; tasks are capture directories under
  `SceneIssues/`.
- Each agent owns one persistent feature branch (`fixes/agent-N`) and one matching targeted-CI
  request branch (`ci-test/fixes/agent-N`).
- Claims are coordinated in a local atomic registry; completion is verified from the agent's
  fetched remote feature branch, not inferred from pixels in the browser UI.
- Folder membership is operational queue state: the coordinator enumerates only
  `origin/master:SceneIssues/open/`. `issue.json.status` remains a validation/audit invariant.
- `blocked` is not closed. Until a separate blocked policy is defined, blocked captures remain in
  `open/` and must not be moved to `closed/`.
- The coordinator must not check out branches, mutate the working tree, merge work, or overwrite
  unrelated local files.
- Browser-image failures and transient Git/network failures must not crash the coordinator or
  incorrectly release work.

## Acceptance criteria

- [x] Discover only open, valid scene-issue directories in deterministic oldest-first order.
- [x] Atomically persist claims, heartbeats, completion, and useful diagnostic state.
- [x] Assign at most one task per agent and one agent per task, including after restart.
- [x] Give every tab an explicit issue path, feature branch, CI branch, and repository workflow.
- [x] Detect completion only when the assigned issue is closed on `origin/master`, its feature
  branch contains valid fixed metadata/evidence, and the fix has verified targeted CI.
- [x] Recover from connection interruptions, stale claims, and Git fetch failures without losing
  the registry. Re-brief an idle/reset conversation from its persisted assignment.
- [x] Update repository documentation for per-agent feature/CI branches and concurrent claims.
- [x] Validate coordinator logic locally without sending messages to live browser tabs.
- [x] Migrate existing fixed captures to `closed/` and all other captures to `open/`.
- [x] Make Unity save new captures directly to `open/` and keep recursive replay support.
- [x] Update hard-coded workflow paths and repository documentation for the nested layout.
- [x] Make terminal completion require the assigned capture to move from `open/` to `closed/`.
- [x] Preserve existing registry leases by capture ID across the path migration.
- [x] Validate migration integrity, coordinator behavior, and affected Unity capture tests.
- [x] Add and validate a guarded root `push_scene_issues.sh` intake command.

## Tasks

- [x] Read repository guidance, issue workflow, current script, UI assets, and issue schema.
- [x] Implement the coordinator and relocate it beside its UI assets.
- [x] Update `AGENTS.md` and `SceneIssues/README.md` to document the new branch/claim model.
- [x] Add automated tests for claiming, stale recovery, and remote completion detection.
- [x] Run non-UI validation and review the final diff.
- [x] Implement and validate the `open/` / `closed/` queue layout.

## Findings

- The draft's `task_complete.png` is only a placeholder; no such image asset exists.
- The checked-out repository currently has one open issue and unrelated untracked user files.
- The existing shared `fixes` policy cannot support independent concurrent writers. The user
  explicitly replaced it with one persistent branch per agent.
- Oculix supplies Sikuli-style globals (`exists`, `click`, `type`, `Key`, and others), so UI code
  must stay compatible with that runtime while non-UI logic remains importable under CPython.

## Validation evidence

- `python3 -m unittest -v test_auto.py`: 9 tests passed on 2026-08-25.
- `java -jar oculixide-4.0.0-macos.jar -c -r auto.py -- --check`: passed under the bundled
  Jython 2.7.4 runtime and found the expected single open remote capture.
- `git diff --check`: passed for the repository documentation changes.
- No browser-driving run was performed, so no live tab was messaged and no remote branch was
  created by validation.
- Repository workflow documentation was committed as `7ce937b77` and pushed to
  `origin/scene-issue-agent-coordinator`. No CI request branch was created because the tracked diff
  is documentation-only and no Unity test can validate the external local script.

## Layout migration findings

- There are currently 14 `fixed` and 7 `open` captures; there are no blocked captures in the
  checkout. Only the 14 fixed directories will move to `closed/`.
- The replay menu already searches recursively, but capture saving writes directly beneath the
  root and must be changed to `SceneIssues/open/`.
- Historical one-shot workflows contain explicit capture paths and must follow moved captures.
- The coordinator registry keys captures by ID rather than path, so the existing agent-1 lease can
  survive the migration without rewriting `_registry.json`.

## Layout migration validation

- Feature commit `94e0377f0` was pushed to `origin/scene-issue-agent-coordinator`, validated, then
  fast-forwarded to `origin/master`; local `master` matches it.
- Queue integrity: 7 `status: open` manifests under `SceneIssues/open/`, 14 `status: fixed`
  manifests under `SceneIssues/closed/`, and no flat capture manifests.
- `python3 -m unittest -q test_auto.py`: 12 tests passed, including fixed moves, blocked-not-closed,
  master-first capture IDs, stale leases, and CI-gated completion.
- Targeted Unity CI request `f862d84f802170db196ab10de4f86a66ad27b573`: `ci/single-test`
  passed `VoxelEngine.Tests.EditMode.SceneIssueCapturePathTests.OpenCaptureRootIsOpenChildOfSceneIssuesRoot`.
- `push_scene_issues.sh` committed and pushed a synthetic capture to a disposable bare remote,
  excluded an unrelated file, and returned a clean no-op on a second run. It also returned a clean
  no-op against the real up-to-date `master` after migration.
- CPython `auto.py --check` fetched the migrated master and enumerated the expected 7 open tasks.
- A post-migration Oculix `--check` attempt could not initialize Sikuli's mouse device because macOS
  reported it blocked. This occurred before script code ran; the same Oculix/Jython runtime had
  passed the earlier dry run, and the user subsequently ran the live coordinator successfully.
