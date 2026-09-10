# Scene-Issue Agent Coordinator Plan

## Goal

Coordinate multiple remote agents against `jlashmet/mounting-force-2`, assign one SceneIssue at a time, and keep ownership/state durable while agents perform implementation directly on the repository's shared `master` branch.

## Current execution policy

The previous per-agent branch model has been retired.

Agents must now:

- use the **Chat on Steroids** plugin for all code and repository interaction, including reading/editing files, running commands, and running tests;
- work directly on `master` rather than on `fixes/agent-N`, feature branches, CI branches, transport branches, or other agent-specific development branches;
- pull/reconcile the latest `origin/master` before beginning work;
- **periodically pull from `origin/master` while working** so concurrent agent changes are incorporated promptly;
- resolve conflicts carefully, preserving valid work from both sides rather than overwriting another agent's changes;
- keep changes scoped to the assigned SceneIssue;
- run the relevant tests through Chat on Steroids and resolve failures attributable to their work;
- keep blocked or incomplete work under `SceneIssues/open/`;
- move work to `SceneIssues/closed/` only when the acceptance criteria and required tasks are genuinely complete;
- pull/reconcile `origin/master` again immediately before final commit/push, resolve conflicts, and rerun affected tests if reconciliation changes code;
- commit completed work directly on `master` and push it to `origin/master` non-force;
- reconcile and retry if `origin/master` advances before the push.

The coordinator may continue to use `automation/assignments` as a durable ownership/state branch. That branch is coordinator metadata only and is not a development branch for agents.

## Scope and constraints

- The coordinator runs locally from `/Users/jlashmet/automation/` and drives nine browser tabs.
- The target repository is `/Users/jlashmet/code/mounting-force-2`; tasks are capture directories under `SceneIssues/`.
- Folder membership is operational queue state: the coordinator enumerates `origin/master:SceneIssues/open/`.
- `blocked` is not closed. Blocked captures remain in `open/` until their required acceptance work is complete.
- Agents do not self-select additional SceneIssues; the coordinator assigns the next task.
- Browser-image failures and transient Git/network failures must not crash the coordinator or incorrectly release work.
- Shared-master concurrency requires agents to preserve unrelated valid changes and reconcile current `origin/master` periodically while working and before pushing.

## Acceptance criteria

- [x] Discover only open, valid scene-issue directories in deterministic order.
- [x] Persist durable assignment ownership and useful diagnostic state.
- [x] Assign at most one task per agent and one agent per task.
- [x] Give every tab an explicit SceneIssue and repository workflow.
- [x] Re-brief idle/reset conversations from persisted assignment state.
- [x] Use `SceneIssues/open/` for incomplete work and `SceneIssues/closed/` for completed work.
- [x] Require agents to use Chat on Steroids for code/files/commands/tests.
- [x] Require direct development on `master` with no per-agent development branches.
- [x] Require agents to periodically pull/reconcile `origin/master` and resolve conflicts while working.
- [x] Require completed work to be committed on `master` and pushed non-force to `origin/master`.
- [x] Validate coordinator logic locally without sending messages to live browser tabs.

## Tasks

- [x] Read repository guidance, issue workflow, current script, UI assets, and issue schema.
- [x] Implement the coordinator and durable assignment state.
- [x] Implement the `open/` / `closed/` queue layout.
- [x] Add automated tests for claiming and stale recovery.
- [x] Replace the old per-agent branch directions with the Chat on Steroids + shared-master workflow.
- [x] Add periodic `origin/master` reconciliation/conflict-resolution instructions.
- [x] Update prompt-policy tests to lock in the new workflow.

## Historical note

Earlier versions of this coordinator used persistent `fixes/agent-N` branches and `ci-test/fixes/agent-N` transport branches. Those directions are obsolete and must not be used for new assignments. The only non-master branch retained by the coordinator is `automation/assignments`, which stores assignment ownership/state and is not an agent development branch.
