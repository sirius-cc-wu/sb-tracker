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
- **Lifecycle Commands**: `begin/pause/review/finish` for explicit feature flow
- **Dependencies**: Link tasks with blocking dependencies
- **Audit Log**: Track all changes to each task with timestamps
- **JSON Export**: Machine-readable output for integration
- **Compaction**: Archive done tasks to keep context efficient

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

Complete a task:

```bash
sb done sb-1
```

## Commands

### Global Tracker Flags
- **`--repo [path]`**: Filter to a repo (defaults to current repo if no path)
- **`--branch [name]`**: Filter to a branch (defaults to current branch if no value)
- **`--worktree [path]`**: Filter to a worktree (defaults to current worktree if no value)
- **`--global`**: Show only tasks not tied to any repo

### Environment

- **`SB_DB_PATH`**: Override the default DB path (otherwise `~/.sb.sqlite`)
- On first run, `sb` will automatically migrate legacy `~/.sb.json` data into `~/.sb.sqlite` and create a timestamped backup of the original JSON file.

### Create and Modify

- **`init`**: Initialize the database (defaults to `~/.sb.sqlite`)
- **`add <title> [--priority/-p N] [--desc/-d TEXT] [--parent ID] [--needs-review] [--id EXTERNAL_ID]`**
  - Example: `sb add "Setup database" --priority 1 --desc "Configure PostgreSQL" --parent sb-1`
  - `--needs-review`: marks the task as requiring human sign-off before it can be closed (see `finish`)
  - `--id EXTERNAL_ID`: assign a literal external ID (e.g. `--id B1XF-3213` to mirror a Jira ticket)
- **`update <id> [field=value ...]`**
  - Fields: `title`, `desc`, `p` (priority), `status`, `parent`, `needs_review` (true|false)
  - Example: `sb update sb-1 p=0 needs_review=true`
- **`begin <id> [--force-reopen]`**: Move task to Doing and capture current context
- **`pause <id>`**: Move task from Doing to Ready
- **`review <id>`**: Move task from Doing to Review
- **`finish <id>`**: Move task to Done; if task has `needs_review=true`, stops at Review first (run again from Review to close)
- **`link <id> [branch=...] [worktree=...]`**: Bind task to branch/worktree context
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
- **`promote <id>`**: Optional Markdown summary of task and sub-tasks
- **`stats`**: Overview of progress and priority breakdown
- **`compact`**: Archive done tasks to save space
- **`done <id>`**: Close task from any state (skips Kanban lifecycle validation)
- **`rm <id>`**: Permanently delete task
- **`config prefix <PREFIX>`**: Set ID prefix for current repo (e.g. `sb config prefix BNC`)
- **`config prefix <PREFIX> --global`**: Set global default prefix
- **`config get prefix`**: Show effective prefix for the current context

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

3. **Track Progress**: Update as you complete steps
   ```bash
   sb begin sb-1.1
   sb review sb-1.1
   sb finish sb-1.1
   ```

4. **End session cleanly**: Verify final state and hand off
   ```bash
   sb compact         # optional
   # If your agent environment has a commit skill, use it here.
   git add -A
   git commit -m "type(scope): description of change"
   sb list --all
   ```
   Then provide a short summary of completed work and what remains.

### Lifecycle Workflow

Recommended explicit lifecycle:

```bash
sb begin <id>     # start active work (Doing)
sb pause <id>     # park work back to Ready
sb review <id>    # hand off for review
sb finish <id>    # complete work (Done)
```

`sb done <id>` closes a task directly from any state, bypassing the Doing/Review requirement of `finish` and ignoring `needs_review`.

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

- **Root tasks**: `sb-<hash>` (for example: `sb-a3f8e9`)
- **Sub-tasks**: `<parent>.<n>` (for example: `sb-a3f8e9.1`, `sb-a3f8e9.2`)
- **Parent relationship**: Use parent ID in `add` or `update`
- **No ID reuse**: IDs are not re-used after task deletion

## Priority Levels

- **P0**: Critical, blocking everything
- **P1**: High priority, do soon
- **P2**: Normal priority (default)
- **P3**: Low priority, nice to have

## Database Format

Tasks are stored in a SQLite database (global by default at `~/.sb.sqlite`).
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
    "kanban_by_repo": {},
    "child_counters": {
      "sb-a3f8e9": 3
    }
  }
}
```

## Examples

### Hierarchical Task Breakdown

```bash
$ sb add "Build authentication system"
Created sb-a3f8e9: Build authentication system (P2)

$ sb add "Design schema" --priority 1 --parent sb-a3f8e9
Created sb-a3f8e9.1: Design schema (P1)

$ sb add "Implement login endpoint" --priority 1 --parent sb-a3f8e9
Created sb-a3f8e9.2: Implement login endpoint (P1)

$ sb add "Write tests" --priority 2 --parent sb-a3f8e9
Created sb-a3f8e9.3: Write tests (P2)

$ sb list
ID              P  Status       Deps       Title
sb-a3f8e9       2  Backlog                 Build authentication system
sb-a3f8e9.1     1  Backlog                   Design schema
sb-a3f8e9.2     1  Backlog                   Implement login endpoint
sb-a3f8e9.3     2  Backlog                   Write tests
```

### Blocking Dependencies

```bash
$ sb add "Deploy to production" --priority 1
Created sb-b9d2c1: Deploy to production (P1)

$ sb dep sb-b9d2c1 sb-a3f8e9
Linked sb-b9d2c1 -> depends on -> sb-a3f8e9

$ sb ready
No issues found matching criteria.

$ sb done sb-a3f8e9.1
Updated sb-a3f8e9.1 status to Done

$ sb done sb-a3f8e9.2
Updated sb-a3f8e9.2 status to Done

$ sb done sb-a3f8e9.3
Updated sb-a3f8e9.3 status to Done

$ sb done sb-a3f8e9
Updated sb-a3f8e9 status to Done

$ sb ready
ID              P  Status       Deps       Title
sb-b9d2c1       1  Backlog                 Deploy to production
```

### Task Reporting

Optional when you want a Markdown report for sharing:

```bash
$ sb promote sb-1
### [sb-1] Build authentication system
**Status:** Done | **Priority:** P2

#### Sub-tasks
- [x] sb-1.1: Design schema
- [x] sb-1.2: Implement login endpoint
- [x] sb-1.3: Write tests

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

### Compaction

Archive old tasks to reduce token context:
```bash
sb compact
```

This moves all done tasks to a `compaction_log` and keeps them accessible via `list --all` or `list --json`.
