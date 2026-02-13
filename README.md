# SB Tracker - Simple Beads

A lightweight, standalone task tracker that stores state in a local `.sb.json` file. Perfect for individuals and agents to maintain context and track long-running or multi-step tasks without external dependencies.

## Features

- **Zero Dependencies**: Pure Python, uses only stdlib (json, os, sys, datetime)
- **Standalone**: One JSON file stores all state locally
- **Hierarchical Tasks**: Support for sub-tasks with parent-child relationships
- **Priority Levels**: Tasks support P0-P3 priority levels
- **Task Status Tracking**: Open/closed status with timestamps
- **Dependencies**: Link tasks with blocking dependencies
- **Audit Log**: Track all changes to each task with timestamps
- **JSON Export**: Machine-readable output for integration
- **Compaction**: Archive closed tasks to keep context efficient

## Installation

### Recommended (pipx)

```bash
pipx install sb-tracker
```

`pipx` keeps the `sb` CLI isolated while exposing it on your shell `PATH`.

### Alternative (pip)

```bash
pip install sb-tracker
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

## Quick Start

Initialize a new task tracker:

```bash
sb init
```

Add a task:

```bash
sb add "My first task"
sb add "High priority task" 0 "This is urgent"
```

List tasks:

```bash
sb list              # Show open tasks
sb list --all        # Show all tasks
sb list --json       # Machine-readable output
```

Complete a task:

```bash
sb done sb-1
```

## Commands

### Create and Modify

- **`init`**: Initialize `.sb.json` in the current git repository root
- **`add <title> [priority] [description] [parent_id]`**
  - Example: `sb add "Setup database" 1 "Configure PostgreSQL" sb-1`
- **`update <id> [field=value ...]`**
  - Fields: `title`, `desc`, `p` (priority), `parent`
  - Example: `sb update sb-1 p=0 desc="New description"`
- **`dep <child_id> <parent_id>`**: Add a blocking dependency
  - Example: `sb dep sb-2 sb-1` (sb-2 blocked by sb-1)

### List and Search

- **`list [--all] [--json]`**: Show open (or all) tasks with hierarchy
- **`ready [--json]`**: Show tasks with no open blockers
- **`search <keyword> [--json]`**: Search titles and descriptions

### Reporting and Maintenance

- **`show <id> [--json]`**: Display task details with audit log
- **`promote <id>`**: Optional Markdown summary of task and sub-tasks
- **`stats`**: Overview of progress and priority breakdown
- **`compact`**: Archive closed tasks to save space
- **`done <id>`**: Mark task as closed
- **`rm <id>`**: Permanently delete task

## Workflow

### For Individual Sessions

1. **Breakdown**: Create tasks with hierarchies for complex work
   ```bash
   sb add "Implement feature X"                    # Creates sb-1
   sb add "Write unit tests" 1 "" sb-1             # Creates sb-1.1
   sb add "Write integration tests" 1 "" sb-1      # Creates sb-1.2
   ```

2. **Execute**: Focus on high-priority ready tasks
   ```bash
   sb ready  # Show tasks with no blockers
   ```

3. **Track Progress**: Update as you complete steps
   ```bash
   sb done sb-1.1
   sb done sb-1.2
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

Tasks are stored in `.sb.json` (found in git repository root) with this schema:

```json
{
  "issues": [
    {
      "id": "sb-1",
      "title": "Task title",
      "description": "Optional description",
      "priority": 1,
      "status": "open",
      "depends_on": ["sb-2"],
      "parent": "sb-1",
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

The file may also include metadata used for ID generation and child counters:

```json
{
  "meta": {
    "id_mode": "hash",
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
Created sb-1: Build authentication system (P2)

$ sb add "Design schema" 1 "" sb-1
Created sb-1.1: Design schema (P1)

$ sb add "Implement login endpoint" 1 "" sb-1
Created sb-1.2: Implement login endpoint (P1)

$ sb add "Write tests" 2 "" sb-1
Created sb-1.3: Write tests (P2)

$ sb list
ID           P  Status       Deps       Title
sb-1         2  open                    Build authentication system
sb-1.1       1  open                      Design schema
sb-1.2       1  open                      Implement login endpoint
sb-1.3       2  open                      Write tests
```

### Blocking Dependencies

```bash
$ sb add "Deploy to production" 1
Created sb-2: Deploy to production (P1)

$ sb dep sb-2 sb-1
Linked sb-2 -> depends on -> sb-1

$ sb ready
No issues found matching criteria.

$ sb done sb-1.1
Updated sb-1.1 status to closed

$ sb done sb-1.2
Updated sb-1.2 status to closed

$ sb done sb-1.3
Updated sb-1.3 status to closed

$ sb done sb-1
Updated sb-1 status to closed

$ sb ready
ID           P  Status       Deps       Title
sb-2         1  open                    Deploy to production
```

### Task Reporting

Optional when you want a Markdown report for sharing:

```bash
$ sb promote sb-1
### [sb-1] Build authentication system
**Status:** closed | **Priority:** P2

#### Sub-tasks
- [x] sb-1.1: Design schema
- [x] sb-1.2: Implement login endpoint
- [x] sb-1.3: Write tests

#### Activity Log
- 2026-02-04: Created
- 2026-02-04: Status: open -> closed
```

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Troubleshooting

### `sb: command not found`

Install with `pipx` and verify your shell can find `sb`:

```bash
pipx install sb-tracker
sb --help
```

If you installed with `pip`, ensure the install location is on your `PATH`.

### `.sb.json` not found

The tracker looks for `.sb.json` starting from the current directory and walking up the directory tree until it finds a `.git` directory (to keep data project-local). If not found, it creates `.sb.json` in the current working directory.

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

This moves all closed tasks to a `compaction_log` and keeps them accessible via `list --all` or `list --json`.
