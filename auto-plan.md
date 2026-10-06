# Scene-Issue Agent Coordinator Plan

## Goal

Coordinate multiple remote agents against the Mounting Force repository, assign one SceneIssue at a time, and keep ownership/state durable while agents implement in isolated SceneIssue worktrees and publish only complete, tested features to the shared branch.

## Current execution policy

The previous shared-master implementation model has been retired. Agents work in isolated SceneIssue worktrees based on the current shared branch.

Agents must now:

- use the **Chat on Steroids** plugin for all code and repository interaction, including reading/editing files, running commands, and running tests;
- work only in the assigned SceneIssue worktree rather than directly in the primary checkout or on persistent agent development branches;
- fetch/reconcile the latest upstream shared branch before beginning work;
- **periodically reconcile from upstream while working** so concurrent agent changes are incorporated promptly, without publishing the incomplete feature upstream;
- resolve conflicts carefully, preserving valid work from both sides rather than overwriting another agent's changes;
- keep changes scoped to the assigned SceneIssue;
- run the relevant tests through Chat on Steroids and resolve failures attributable to their work;
- keep blocked or incomplete work under `SceneIssues/open/`;
- move work to `SceneIssues/closed/` only when the acceptance criteria and required tasks are genuinely complete;
- never publish partial feature work to the shared branch after an individual task, milestone, checkpoint, or partial green test run;
- only when the whole SceneIssue is complete, every required acceptance criterion is satisfied, all required tests/gates are green, and final self-review is complete, reconcile upstream one final time;
- rerun affected tests if that final reconciliation changes code, then perform the single final non-force promotion to the shared branch;
- reconcile, revalidate affected work, and retry if the shared branch advances before that final promotion.

The coordinator may continue to use `automation/assignments` as a durable ownership/state branch. That branch is coordinator metadata only and is not a development branch for agents.

## Scope and constraints

- The coordinator runs locally from `/Users/jlashmet/automation/` and drives nine browser tabs.
- The target repository is `/Users/jlashmet/code/mounting-force-2`; tasks are capture directories under `SceneIssues/`.
- Folder membership is operational queue state: the coordinator enumerates `origin/master:SceneIssues/open/`.
- `blocked` is not closed. Blocked captures remain in `open/` until their required acceptance work is complete.
- Agents do not self-select additional SceneIssues; the coordinator assigns the next task.
- Browser-image failures and transient Git/network failures must not crash the coordinator or incorrectly release work.
- Concurrent work requires agents to preserve unrelated valid changes and reconcile from upstream periodically while working, while keeping incomplete feature work isolated until final validated promotion.

## Acceptance criteria

- [x] Discover only open, valid scene-issue directories in deterministic order.
- [x] Persist durable assignment ownership and useful diagnostic state.
- [x] Assign at most one task per agent and one agent per task.
- [x] Give every tab an explicit SceneIssue and repository workflow.
- [x] Re-brief idle/reset conversations from persisted assignment state.
- [x] Use `SceneIssues/open/` for incomplete work and `SceneIssues/closed/` for completed work.
- [x] Require agents to use Chat on Steroids for code/files/commands/tests.
- [x] Require isolated SceneIssue worktrees with no persistent per-agent implementation branches.
- [x] Require agents to periodically fetch/reconcile from upstream and resolve conflicts while working without publishing partial work.
- [x] Require promotion to the shared branch only after the entire SceneIssue is complete, tested, gated and self-reviewed.
- [x] Validate coordinator logic locally without sending messages to live browser tabs.

## Tasks

- [x] Read repository guidance, issue workflow, current script, UI assets, and issue schema.
- [x] Implement the coordinator and durable assignment state.
- [x] Implement the `open/` / `closed/` queue layout.
- [x] Add automated tests for claiming and stale recovery.
- [x] Replace the old per-agent/shared-master directions with the Chat on Steroids + isolated-worktree workflow.
- [x] Add periodic upstream reconciliation/conflict-resolution instructions that explicitly prohibit intermediate publication.
- [x] Update prompt-policy tests to lock in the new workflow.

## Historical note

Earlier versions of this coordinator used persistent `fixes/agent-N` branches and `ci-test/fixes/agent-N` transport branches. Those directions are obsolete and must not be used for new assignments. The only non-master branch retained by the coordinator is `automation/assignments`, which stores assignment ownership/state and is not an agent development branch.
