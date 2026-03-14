# SB Tracker - Simple Beads

A lightweight, standalone task tracker that stores state in a local SQLite database. Perfect for individuals and agents to maintain context and track long-running or multi-step tasks without external dependencies.

## Features

- **Zero Dependencies**: Pure Python, uses only stdlib (json, os, sys, datetime)
- **Standalone**: One local SQLite file stores all state (global by default)
- **Global Tracker**: Defaults to `~/.sb.sqlite` with optional `SB_DB_PATH`
- **Repo Awareness**: Tasks can be scoped to a repo and filtered by repo
- **Commit Snapshot**: Tasks capture the current repo commit on add/update
- **Branch/Worktree Context**: Tasks can capture repo branch and worktree path
- **Hierarchical Tasks**: Support for sub-tasks with parent-child relationships
- **Priority Levels**: Tasks support P0-P3 priority levels
- **Kanban Workflow**: Configurable states and a board view
- **Task Status Tracking**: Workflow status with timestamps
- **Lifecycle Commands**: `begin/pause/finish` for explicit feature flow
- **Verification**: `verify` command to run tests and auto-advance status
- **Context Hydration**: `context` command to aggregate task specs and files for agents
- **Dependencies**: Link tasks with blocking dependencies
- **Audit Log**: Track all changes to each task with timestamps
- **JSON Export**: Machine-readable output for integration
- **Compaction**: Archive done tasks to keep context efficient

## Breaking Change (v0.4.0)

- Storage is now SQLite-only.
- `.sb.json` is no longer supported and is not auto-migrated.
- `SB_DB_PATH` must point to a SQLite path (for example, `~/.sb.sqlite`).

## Installation

### Recommended (pipx)

```bash
pipx install sb-tracker
```

`pipx` keeps the `sb` CLI isolated while exposing it on your shell `PATH`.

### Alternative (pip)

To install or upgrade to the latest version, use:
```bash
pip install -U sb-tracker
```

### From Source (development)

```bash
git clone https://github.com/sirius-cc-wu/sb-tracker.git
cd sb-tracker
pip install -e .
```

Verify installation:

```bash
sb --help
```

## Gemini CLI Skill Installation

For AI agents that support Gemini CLI skills, you can install the `sb-tracker` skill to give them the context and instructions needed to manage tasks on your behalf. This is the recommended, non-intrusive way for agents to learn how to use this tool.

From the root of this repository, run the following command:

```bash
npx skills add https://github.com/sirius-cc-wu/sb-tracker/tree/main/skills/sb-tracker
```

This command installs the skill from the `skills/sb-tracker` directory into your Gemini CLI configuration.

## Quick Start

Initialize a new task tracker (global by default):

```bash
sb init
```

Add a task:

```bash
sb add "My first task"
sb add "High priority task" --priority 0 --desc "This is urgent"
```

List tasks:

```bash
sb list              # Show non-done tasks
sb list --all        # Show all tasks
sb list --json       # Machine-readable output
sb list --repo       # Show tasks for current repo
sb list --global     # Show tasks not tied to any repo
```

Work a task through the normal lifecycle:

```bash
sb begin sb-1
sb verify sb-1 --cmd "pytest -q"
```

If verification succeeds, the task usually auto-advances to `Done` (or `Review` when `--needs-review` is set), so a separate `sb finish` is typically only needed for manual closure or the final `Review -> Done` step.

## Commands

### Global Tracker Flags
- **`--repo [path]`**: Filter to a repo (defaults to current repo if no path)
- **`--branch [name]`**: Filter to a branch (defaults to current branch if no value)
- **`--worktree [path]`**: Filter to a worktree (defaults to current worktree if no value)
- **`--global`**: Show only tasks not tied to any repo

### Environment

- **`SB_DB_PATH`**: Override the default DB path (otherwise `~/.sb.sqlite`)
- Paths ending in `.json` are rejected (SQLite-only storage backend).

### Create and Modify

- **`init`**: Initialize the database (defaults to `~/.sb.sqlite`)
- **`add`**: `sb add <title> [--priority/-p N] [--desc/-d TEXT] [--parent ID] [--needs-review] [--id EXTERNAL_ID]`
  - Example: `sb add "Setup database" --priority 1 --desc "Configure PostgreSQL" --parent sb-1`
  - `--needs-review`: marks the task as requiring human sign-off before it can be closed (see `finish`)
  - `--id EXTERNAL_ID`: assign a literal external ID (e.g. `--id B1XF-3213` to mirror a Jira ticket)
- **`import`**: `sb import <file.md> [--parent ID] [--dry-run]`
  - Bulk imports tasks from a Markdown checklist.
  - Respects indentation for hierarchy.
  - Skips duplicates (idempotent).
- **`update`**: `sb update <id> [field=value ...]`
  - Fields: `title`, `desc`, `p` (priority), `status`, `parent`, `needs_review` (true|false)
  - Example: `sb update sb-1 p=0 needs_review=true`
  - Intended for metadata edits and state repair. Prefer `begin` / `verify` / `finish` for normal lifecycle transitions.
- **`begin <id> [--force-reopen]`**: Move task to Doing and capture current context
- **`pause <id>`**: Move task from Doing to Ready
- **`verify <id> --cmd "<CMD>" [--timeout SECONDS]`**: Run tests and log results; auto-advances to `Review` or `Done` on success
  - Default timeout is 300 seconds
  - Use `--timeout 0` to disable the timeout for long-running verification
  - The `sb` process now exits nonzero when verification fails or times out, so shell chains like `sb verify ... && sb finish ...` stop safely
- **`finish <id>`**: Complete the normal lifecycle transition for an active task. Expected source state is `Doing` (or `Review` for the final close). If `needs_review=true`, `finish` from `Doing` stops at `Review` first; run again from `Review` to close.
- **`context <id> [--files]`**: Show hydration context (spec, linked files, last failure) for agents
- **`link <id> [branch=...] [worktree=...] [file=...]`**: Bind task to context or files
- **`event <switch|create|merge|remove> [--task <id>]`**: Ingest external lifecycle event
- **`dep <child_id> <parent_id>`**: Add a blocking dependency
  - Example: `sb dep sb-2 sb-1` (sb-2 blocked by sb-1)

### List and Search

- **`list [--all] [--json]`**: List all open issues (use `--all` to include closed)
- **`ready [--json]`**: List only issues with no unresolved dependencies
- **`search <keyword> [--json]`**: Search titles and descriptions
  - Use `--repo`, `--branch`, `--worktree`, or `--global` to filter scope

### Reporting and Maintenance

- **`show <id> [--json]`**: Display task details with audit log
- **`board [--json]`**: Show issues grouped into Kanban columns
- **`promote <id>`**: Export Markdown summary of task and its history
- **`stats`**: Overview of progress and priority breakdown
- **`compact`**: Archive done tasks to save space
- **`close <id>`**: Close task from any state (skips Kanban lifecycle validation)
- **`rm <id>`**: Permanently delete task
- **`config prefix <PREFIX>`**: Set ID prefix for current repo (e.g. `sb config prefix BNC`)
- **`config prefix <PREFIX> --global`**: Set global default prefix
- **`config get prefix`**: Show effective prefix for the current context
- **`config verify-timeout <SECONDS>`**: Set the default verify timeout for the current repo
- **`config verify-timeout <SECONDS> --global`**: Set the global default verify timeout
- **`config get verify-timeout`**: Show the effective verify timeout for the current context

## Workflow

### For Individual Sessions

1. **Breakdown**: Create tasks with hierarchies for complex work
   ```bash
   sb add "Implement feature X"                              # Creates sb-<hash>
   sb add "Write unit tests" --priority 1 --parent sb-<hash>  # Creates sub-task
   sb add "Write integration tests" --priority 1 --parent sb-<hash>
   ```

2. **Execute**: Focus on high-priority ready tasks
   ```bash
   sb ready  # Show tasks with no blockers
   ```

3. **Verify and Finish**: Run tests to auto-advance or finish manually
```bash
sb begin sb-x9z8y
sb verify sb-x9z8y --cmd "pytest tests/test_feature.py"
```

If the verify command succeeds, the task is already advanced for you. Use `sb finish` when you need to close a task manually or move a `Review` task to `Done`.

4. **End session cleanly**: Verify final state and hand off
   ```bash
   sb compact         # optional
   # If your agent environment has a commit skill, use it here.
   git add -A
   git commit -m "type(scope): description of change"
   sb list --all
   ```
   Then provide a short summary of completed work and what remains using `sb promote <id>`.

### Lifecycle Workflow

Recommended explicit lifecycle:

```bash
sb ready                         # pick work with no unresolved blockers
sb begin <id>                    # start active work (Doing)
sb verify <id> --cmd "pytest"    # record verification and auto-advance on success
sb finish <id>                   # optional manual close, or Review -> Done
sb pause <id>                    # park work back to Ready
```

Use `sb verify <id> --cmd "..."` to automate the transition from Doing on success.
Notes:
- `sb finish` is for tasks already in active lifecycle states. If a task is still `Backlog` or `Ready`, run `sb begin <id>` first.
- `sb verify` defaults to a 300-second timeout. Use `--timeout <seconds>` to override it, or `--timeout 0` to disable the timeout entirely.
- If `sb finish` does not advance a task, inspect `sb show <id>` before using `sb update`.
`sb close <id>` closes a task directly from any state, bypassing the Doing/Review requirement of `finish` and ignoring `needs_review`.

### Optional Hook Adapters

`sb-tracker` stays standalone. If you use git hooks, call `sb event` from them.

Git hook examples:

```bash
# .git/hooks/post-checkout
sb event switch --repo --branch --worktree

# .git/hooks/post-merge
sb event merge --repo --branch
```

### Task ID Format

- **Task IDs**: `sb-<hash>` (for example: `sb-a3f8e9`)
- **Child IDs**: Same standard format (for example: `sb-x9z8y`)
- **Parent relationship**: Use parent ID in `add` or `update`
- **No ID reuse**: IDs are not re-used after task deletion

## Priority Levels

- **P0**: Critical, blocking everything
- **P1**: High priority, do soon
- **P2**: Normal priority (default)
- **P3**: Low priority, nice to have

## Database Format

Tasks are stored in a SQLite database (global by default at `~/.sb.sqlite`).
The on-disk format uses normalized tables (`issues`, `issue_dependencies`, `issue_events`, `meta`, `schema_info`).
Older SQLite blob-format DBs are auto-migrated on first load with a timestamped backup.

For migration/import-export workflows, the logical payload schema is:

```json
{
  "issues": [
    {
      "id": "sb-1",
      "title": "Task title",
      "description": "Optional description",
      "priority": 1,
      "status": "Backlog",
      "depends_on": ["sb-2"],
      "parent": "sb-1",
      "repo": "/absolute/path/to/repo",
      "repo_commit": "abc123...",
      "created_at": "2026-02-04T18:40:10.692Z",
      "closed_at": "2026-02-04T19:40:10.692Z",
      "events": [
        {
          "type": "created",
          "timestamp": "2026-02-04T18:40:10.692Z",
          "title": "Task title"
        }
      ]
    }
  ],
  "compaction_log": []
}
```

### Repo Awareness and Worktrees

When inside a git repo, tasks store a canonical repo root so multiple worktrees/branches share the same task set. Each add/update captures the current commit hash in `repo_commit` to provide context for the repo state.

The file may also include metadata used for ID generation and child counters:

```json
{
  "meta": {
    "id_mode": "hash",
    "kanban": {
      "columns": ["Backlog", "Ready", "Doing", "Review", "Done"],
      "backlog": "Backlog",
      "done": "Done"
    },
    "kanban_by_repo": {}
  }
}
```

## Examples

### Hierarchical Task Breakdown

```bash
$ sb add "Build authentication system"
Created sb-a3f8e9: Build authentication system (P2)

$ sb add "Design schema" --priority 1 --parent sb-a3f8e9
Created sb-x9z8y: Design schema (P1)

$ sb add "Implement login endpoint" --priority 1 --parent sb-a3f8e9
Created sb-m4n5o: Implement login endpoint (P1)

$ sb add "Write tests" --priority 2 --parent sb-a3f8e9
Created sb-p2q3r: Write tests (P2)

$ sb list
ID              P  Status       Deps       Title
--------------------------------------------------------------------------------
sb-a3f8e9       2  Backlog                 Build authentication system
sb-x9z8y        1  Backlog                 ├─ Design schema
sb-m4n5o        1  Backlog                 ├─ Implement login endpoint
sb-p2q3r        2  Backlog                 └─ Write tests
```

### Blocking Dependencies

```bash
$ sb add "Deploy to production" --priority 1
Created sb-b9d2c1: Deploy to production (P1)

$ sb dep sb-b9d2c1 sb-a3f8e9
Linked sb-b9d2c1 -> depends on -> sb-a3f8e9

$ sb ready
No issues found matching criteria.

$ sb close sb-x9z8y
Updated sb-x9z8y status to Done

$ sb close sb-m4n5o
Updated sb-m4n5o status to Done

$ sb close sb-p2q3r
Updated sb-p2q3r status to Done

$ sb close sb-a3f8e9
Updated sb-a3f8e9 status to Done

$ sb ready
ID              P  Status       Deps       Title
sb-b9d2c1       1  Backlog                 Deploy to production
```

### Task Reporting

Optional when you want a Markdown report for sharing:

```bash
$ sb promote sb-a3f8e9
### [sb-a3f8e9] Build authentication system
**Status:** Done | **Priority:** P2

#### Sub-tasks
- [x] sb-x9z8y: Design schema
- [x] sb-m4n5o: Implement login endpoint
- [x] sb-p2q3r: Write tests

#### Activity Log
- 2026-02-04: Created
- 2026-02-04: Status: Backlog -> Done
```

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

Run tests with coverage before submitting changes:

```bash
PYTHONPATH=src pytest -q
```

The test configuration enforces a minimum coverage threshold of 90%.

## Troubleshooting

### `sb: command not found`

Install with `pipx` and verify your shell can find `sb`:

```bash
pipx install sb-tracker
sb --help
```

If you installed with `pip`, ensure the install location is on your `PATH`.

### `.sb.sqlite` not found

By default, the tracker uses `~/.sb.sqlite`. You can override the location with `SB_DB_PATH`.

To initialize:
```bash
cd /your/project
sb init
```

### Task not found error

Make sure you're using the correct task ID:
```bash
$ sb list --json   # See all task IDs
```

### `sb finish` does not advance a task

`sb finish` is meant for tasks that are already in `Doing` or `Review`.
If the task is still in `Backlog` or `Ready`, start it first:

```bash
sb show <id>
sb begin <id>
sb verify <id> --cmd "pytest -q"
sb finish <id>
```

### Compaction

Archive old tasks to reduce token context:
```bash
sb compact
```

This moves all done tasks to a `compaction_log` and keeps them accessible via `list --all` or `list --json`.
