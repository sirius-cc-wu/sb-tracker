# PRD: sb-tracker Task Model and Workflow

## Document Metadata
- Status: Draft (implementation-aligned)
- Owner: sb-tracker
- Last Updated: 2026-03-06
- Target: task model, status model, and mutation commands

## 1. Problem Statement

`sb-tracker` needs a compact but expressive task model for agent/human workflows:
- hierarchical decomposition,
- dependency blocking,
- explicit status transitions,
- auditable mutation history.

## 2. Goals

1. Represent tasks with stable IDs and optional hierarchy.
2. Support dependency-based readiness checks.
3. Support Kanban-style status workflows, including lifecycle commands.
4. Track mutations through per-task event logs.

## 3. Non-Goals

1. Full project management (sprints, assignees, estimates).
2. Cross-repo dependency graph analytics.
3. Remote collaboration features.

## 4. Task Schema Requirements

Each issue supports:
1. Required:
   - `id`, `title`, `status`, `created_at`
2. Optional:
   - `description`, `priority`, `depends_on`, `parent`, `closed_at`
   - `repo`, `repo_commit`, `repo_branch`, `worktree_path`
   - `needs_review` (boolean, optional) — when `true`, `sb finish` stops at Review for human sign-off
   - `lifecycle` object (event metadata)
   - `events` audit log

## 5. ID and Hierarchy Requirements

1. Top-level IDs:
   - Hash-based by default: `<prefix>-xxxxxx` (e.g. `sb-a3f8e9`, `BNC-a3f8e9`)
   - Optional sequential mode via `meta.id_mode = "sequential"` (e.g. `BNC-1`, `BNC-2`)
   - External IDs can be set explicitly via `sb add --id <EXTERNAL_ID>` (e.g. Jira: `B1XF-3213`)
2. ID prefix:
   - Global default: `meta.id_prefix` (defaults to `sb`)
   - Per-repo override: `meta.prefix_by_repo[repo_root]`
   - Configure via: `sb config prefix <PREFIX>` (repo) or `sb config prefix <PREFIX> --global`
3. Child IDs:
   - `<parent>.<n>` with monotonic per-parent counters (inherits parent prefix)
4. IDs must not be reused after deletion.

## 6. Status Model Requirements

Default columns:
- `Backlog`, `Ready`, `Doing`, `Review`, `Done`

Rules:
1. `open` and `closed` aliases normalize to backlog/done respectively.
2. Done-state transitions set `closed_at`.
3. Leaving done state clears `closed_at`.
4. Repo-specific Kanban overrides are supported via `meta.kanban_by_repo`.

## 7. Mutation Command Requirements

### 7.1 Core
1. `add` creates tasks with optional parent/repo context, `--needs-review` flag, and `--id EXTERNAL_ID`.
2. `update` updates title/description/priority/status/parent, context fields, and `needs_review=true|false`.
3. `rm` deletes task by ID.

### 7.2 Configuration
1. `config prefix <PREFIX>` sets the ID prefix for the current repo.
2. `config prefix <PREFIX> --global` sets the global default prefix.
3. `config get prefix` prints the effective prefix for the current context.

### 7.2 Dependency
1. `dep <child> <parent>` adds a blocking dependency.
2. Duplicate dependency links are idempotent.

### 7.3 Status
1. `status <id> <state>` sets explicit status.
2. `close <id>` moves task to repo-configured done state.

### 7.4 Lifecycle
1. `begin`, `pause`, `review`, `finish` provide explicit feature progression.
2. `begin` captures live repo context from current workspace.
3. `begin` on `Done` is no-op unless `--force-reopen`.

### 7.5 External Lifecycle Integration
1. `event` ingests external events (`switch|create|merge|remove`).
2. `link` manually binds branch/worktree context for matching.

### 7.6 Maintenance
1. `compact` removes only tasks that are both:
   - in done state, and
   - at least 90 days old based on `closed_at`.
2. Done tasks without a valid `closed_at` timestamp must not be removed by `compact`.
3. If no tasks meet the retention threshold, `compact` performs no deletions.

## 8. Readiness Model

`ready` must include only tasks where:
1. task is not done,
2. all listed dependencies are done.

## 9. Audit Requirements

Every mutation path must log events in `events[]` with timestamped records.

Event types include:
- `created`, `updated`, `dep_added`, `status_changed`
- `lifecycle_begin`, `lifecycle_pause`, `lifecycle_review`, `lifecycle_finish`
- `external_event`, `context_linked`

## 10. Testing Requirements

1. Hierarchical ID generation and parent validation.
2. Dependency linking and readiness behavior.
3. Status normalization and done/closed timestamp behavior.
4. Lifecycle transition correctness and force-reopen path.
5. Event/link mutation and idempotent no-op behavior.
6. `compact` retention behavior (remove only done tasks older than 90 days).

Primary tests:
- `sb-tracker/tests/test_cli_coverage.py`

## 11. Acceptance Criteria

1. Tasks can be created, linked, progressed, and completed fully via CLI.
2. Status/readiness behavior is deterministic and auditable.
3. Lifecycle and classic status commands coexist without breaking older workflows.
4. Compaction preserves recent done tasks and only purges done tasks older than 90 days.
