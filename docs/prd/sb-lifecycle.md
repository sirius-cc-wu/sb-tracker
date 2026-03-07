# PRD: sb-tracker Feature Lifecycle

## Document Metadata
- Status: Draft (implementation-ready)
- Owner: sb-tracker
- Last Updated: 2026-02-28
- Target: sb-tracker CLI

## 1. Problem Statement

`sb-tracker` is good at tracking tasks, but lifecycle progress (`Backlog -> Doing -> Review -> Done`) is still mostly manual. In multi-worktree or multi-agent workflows, task status can drift from actual execution context.

We need a lightweight lifecycle model that:
- keeps `sb-tracker` as the source of truth for task state,
- supports explicit agent-driven actions,
- supports optional external triggers (worktrunk/git/shell),
- does not make `sb-tracker` depend on worktrunk.

## 2. Goals

1. Add first-class lifecycle commands to `sb` for explicit, low-friction status transitions.
2. Add an optional event ingestion interface for external hook adapters.
3. Improve task-context linkage using repo/branch/worktree metadata.
4. Keep backward compatibility with existing `sb` flows (`status`, `close`, `update`, `list`).

## 3. Non-Goals

1. Do not build a separate lifecycle orchestration daemon/tool.
2. Do not add mandatory dependency on worktrunk.
3. Do not add background auto-watchers in v1.
4. Do not infer lifecycle from opaque heuristics without explicit command/event input.

## 4. Users and Primary Use Cases

### 4.1 Users
- Individual developers using `sb` manually.
- Coding agents operating through CLI workflows.
- Teams using worktrees and optional lifecycle hooks.

### 4.2 Core Use Cases
1. Agent starts implementation for a task and marks it `Doing` with one command.
2. Agent hands off task for review with explicit transition.
3. External hook (worktrunk/git/shell) sends lifecycle event to `sb`.
4. User filters tasks by current branch/worktree during active development.

## 5. Product Requirements

### 5.1 Lifecycle Commands (Explicit Control)
Add commands:
- `sb begin <id>`: move to `Doing` and capture current repo context.
- `sb pause <id>`: move to `Ready`.
- `sb review <id>`: move to `Review`.
- `sb finish <id>`: move to `Done`.

Rules:
- No-op transitions must be safe and idempotent.
- Lifecycle commands must append audit events.
- `sb close <id>` is the direct close command from any state.

### 5.2 External Event Ingestion
Add command:
- `sb event <event_type> [--task <id>] [--repo <path>] [--branch <name>] [--worktree <path>]`

Supported event types in v1:
- `switch`
- `create`
- `merge`
- `remove`

Resolution behavior:
1. If `--task` is provided, apply transition to that task.
2. Otherwise attempt unique match from open tasks by:
   - `repo + branch`, then
   - `repo + worktree_path`.
3. If no unique match, perform no mutation and print deterministic diagnostic output.

### 5.3 Context Linking
Support command:
- `sb link <id> [branch=<name>] [worktree=<path>]`

Purpose:
- Explicitly bind a task to branch/worktree metadata for robust event resolution.

### 5.4 Query/Filter Enhancements
Extend filtering with branch-awareness:
- `--branch [name]` for `list`, `ready`, `search`, `board`.
- If value omitted, infer current branch from git.

## 6. Lifecycle State Machine (v1)

Canonical statuses:
- `Backlog`, `Ready`, `Doing`, `Review`, `Done`

Transitions:
1. `begin`: `Backlog|Ready|Review -> Doing`
2. `pause`: `Doing -> Ready`
3. `review`: `Doing -> Review`
4. `finish`: `Doing -> Review` (when `needs_review=true`) or `Doing|Review -> Done`
   - When a task has `needs_review=true`, `finish` from `Doing` stops at `Review` and prints a reminder.
   - A second `finish` from `Review` always closes to `Done` (human has confirmed).
   - `close <id>` bypasses `needs_review` and force-closes from any state.

Event-to-status default mappings:
1. `event switch`: target task `-> Doing` (if not `Done`)
2. `event create`: target task `-> Doing` (if not `Done`)
3. `event merge`: target task `Doing|Review -> Review` (default is not auto-done)
4. `event remove`: no status change by default; audit event only

## 7. Data Model and Interface Changes

### 7.1 Issue Fields
Add/standardize fields on task records:
- `repo_branch` (string, optional)
- `worktree_path` (string, optional)

Add optional lifecycle object:
- `lifecycle.started_at`
- `lifecycle.last_event_at`
- `lifecycle.last_event_type`

### 7.2 Audit Events
Add new event types:
- `lifecycle_begin`
- `lifecycle_pause`
- `lifecycle_review`
- `lifecycle_finish`
- `external_event`
- `context_linked`

No-op lifecycle actions should log with `result: "noop"`.

### 7.3 Compatibility
- Schema is additive; no mandatory migration.
- Existing DB entries remain valid.
- Existing commands retain behavior.

## 8. Integration Model (Hook-Agnostic)

### 8.1 Worktrunk Hook Adapter (Optional)
Example mapping (in `.config/wt.toml`):
- `post-switch` -> `sb event switch ...`
- `post-create` -> `sb event create ...`
- `post-merge` -> `sb event merge ...`

### 8.2 Git Hook Adapter (Optional)
- `post-checkout` -> `sb event switch`
- `post-merge` -> `sb event merge`

### 8.3 Shell Wrapper Adapter (Optional)
- Wrapper around `wt switch` or `git switch` calling `sb event`.

Design rule:
- External systems emit events.
- `sb-tracker` owns state transitions and audit trail.

## 9. UX and Output Requirements

1. All lifecycle/event commands must return deterministic single-line outcome summaries.
2. Ambiguous task resolution must include clear reason (`no match` or `multiple matches`).
3. JSON output paths should include lifecycle metadata when present.
4. Human-readable outputs should remain concise.

## 10. Testing Requirements

### 10.1 Unit Tests
1. Transition logic for `begin/pause/review/finish` including no-op paths.
2. Event resolution by `--task`, by branch, by worktree, and ambiguity handling.
3. Branch/worktree metadata capture correctness.

### 10.2 CLI Integration Tests
1. `sb begin <id>` updates status and captures context.
2. `sb event switch` updates matched task to `Doing`.
3. `sb event merge` updates matched task to `Review`.
4. `sb link` updates metadata and emits audit event.

### 10.3 Regression Tests
1. Existing command behaviors unchanged (`close`, `status`, `update`, `list --repo`, `--worktree`).
2. Existing JSON and human output formats remain backward compatible.

## 11. Acceptance Criteria

1. User can manage full feature lifecycle with explicit `sb` commands only.
2. Optional hooks can drive status updates through `sb event` without direct DB edits.
3. No lifecycle command causes unintended mutation on ambiguous match.
4. Existing users can upgrade without changing current workflows.
5. Documentation provides copy-paste integration examples for worktrunk, git hooks, and shell wrappers.

## 12. Rollout Plan

1. Ship as additive minor release.
2. Use `sb close` as the direct close command.
3. Update `README.md`, `AGENTS.md`, and skill docs with recommended lifecycle flow.
4. Add a short migration note: no migration required; new fields are optional.

## 13. Risks and Mitigations

1. Risk: Wrong task matched by external events.
- Mitigation: strict unique-match requirement and no-mutation on ambiguity.

2. Risk: Over-automation closes tasks prematurely.
- Mitigation: default merge mapping is `Review`, not `Done`.

3. Risk: Scope creep into workflow orchestration.
- Mitigation: keep hooks/adapters external; keep `sb` focused on state transitions.

## 14. Open Questions (for v2)

1. ~~Should `finish` optionally gate on human review?~~ **Resolved:** `needs_review` flag on tasks; `finish` stops at Review when set, closes on second call.
2. Should `finish` optionally require clean git state?
3. Should event rules be user-configurable via `meta.lifecycle_rules`?
4. Should we add per-repo lifecycle policy files for team conventions?
