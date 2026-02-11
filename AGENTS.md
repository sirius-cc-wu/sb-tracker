# SB Tracker (Simple Beads)

A lightweight, standalone task tracker that stores state in a local `.sb.json` file. It's ideal for individual agent sessions to maintain context and track long-running or multi-step tasks.

## Installation

The `sb` command is installed via the `sb-tracker` Python package:

```bash
pipx install sb-tracker
```

Or install in development mode from the standalone package:

```bash
pip install -e /path/to/sb-tracker
```

Verify installation:

```bash
sb --help
```

## Quick Start

- **Initialize**: Run `sb init` if `.sb.json` doesn't exist.
- **Add Task**: `sb add "Task Title" [priority] [desc] [parent_id]`
- **Hierarchy**: Use `parent_id` to create sub-tasks (e.g., `sb-1.1`).
- **List Tasks**: `sb list` (open) or `sb list --all`
- **JSON Output**: Append `--json` to `list` or `show` for machine-readable data.
- **Complete Task**: `sb done sb-1`

## Workflow

1. **Breakdown**: When given a complex task, create `sb-tracker` issues. Use hierarchical IDs for sub-steps (e.g., `add "Sub-step" 2 "..." sb-1`).
2. **Execute**: Work on the highest priority (P0-P1) "ready" task.
3. **Audit**: Use `show <id>` to see the status history and event log.
4. **Context Recovery**: If a session restarts, run `sb list --json` to see the full state.

## Commands

The skill uses the `sb` command (installed via `pip install sb-tracker`).

### Priority Levels

When using `sb add` or `sb update`, specify priority as a **numeric value** (0-3):
- **0** = P0 (Critical) - Blocking other work
- **1** = P1 (High) - Important, do soon
- **2** = P2 (Medium) - Normal priority (default)
- **3** = P3 (Low) - Nice to have

Example: `sb add "Fix critical bug" 0 "This blocks release"`

### Create and Modify
- **`add`**: `sb add <title> [priority] [desc] [parent_id]`
- **`update`**: `sb update <id> [title=...] [desc=...] [p=...] [parent=...]`
  - Example: `sb update sb-1 p=0 desc="New description"`
- **`dep`**: `sb dep <child> <parent>`

### List and Search
- **`list`**: Shows open tasks with hierarchy.
- **`ready`**: Shows tasks with no open blockers.
- **`search`**: `sb search <keyword>`

### Reporting and Promotion
- **`promote`**: `sb promote <id>`
  - Generates a Markdown summary of the task, its sub-tasks, and its activity log. Use this when you need to report progress to the user or "promote" a private task to a team-wide issue tracker.

### Statistics and Maintenance
- **`stats`**: Overview of progress and priority breakdown.
- **`compact`**: Remove closed tasks to save tokens and context space.

## Agent Operational Loop

To maintain perfect context across sessions, agents should follow this loop:

1. **Onboarding**: At the start of a task, run `sb list --json` or `sb ready` to understand the current state.
2. **Execution**: Focus on the highest priority `ready` tasks.
3. **Verification**: Run project tests or take a screenshot to confirm the work is complete.
4. **Updating**: As you complete sub-steps, run `sb done <id>`.
5. **Clean up**: Run `sb compact` to remove closed tasks before committing.
6. **Commit**: Commit code and `.sb.json` together so the tracker state matches the code state.
7. **Handoff**: Before ending a session, run `sb list --all` and provide a short summary of what was completed and what remains.

## Landing the Plane (Session Completion)

**When ending a work session**, complete these steps:

1. **File remaining work** - Create issues for any follow-up tasks
2. **Verify** - Run project tests or take a screenshot to confirm the work is complete
3. **Update task status** - Mark completed work as done with `sb done <id>`
4. **Clean up** - Run `sb compact` if you want to remove closed tasks
5. **Commit local changes** - Commit code and `.sb.json` together. If a `commit` skill is available in the agent environment, use it. Otherwise run:
   ```bash
   git add -A
   git commit -m "[scope]: complete <task-id>"
   ```
6. **Final state check** - Run `sb list --all` and confirm there are no ambiguous task states
7. **Handoff** - Share a brief summary of completed work and the next task to pick up

**CRITICAL RULES:**
- Always update task status before ending a session
- Never leave tasks in an ambiguous state; close them or create explicit follow-up sub-tasks
- Do not leave finished work uncommitted; commit issue-by-issue so progress is resumable
- Prefer the `commit` skill for commits when available; use raw git commit only as fallback
- `sb promote` is optional and only for generating a Markdown report when needed

### Close Issue
`sb done <id>`
- Moves status to "closed" and sets `closed_at` timestamp.

### Delete Issue
`sb rm <id>`
- Permanently removes the issue from the database.
