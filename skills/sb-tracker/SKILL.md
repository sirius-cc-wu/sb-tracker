---
name: sb-tracker
description: Track work with the `sb` CLI by creating, updating, listing, and completing tasks with priorities, dependencies, and repo/global filters. Use for any coding agent that needs a lightweight task tracker for long-running or multi-step work, context recovery across sessions, or end-of-session handoff.
---

# SB Tracker

Use `sb` to maintain a lightweight task list in a global SQLite DB (default `~/.sb.sqlite`) so agent work is resumable across sessions.

## When to Use

Use this skill when work is multi-step, spans sessions, or needs explicit handoff state.

## Preconditions

Verify the CLI is available:

```bash
sb --help
```

DB behavior:
- Default DB: `~/.sb.sqlite`
- Override path: `SB_DB_PATH=/path/to/db.sqlite`
- Legacy `~/.sb.json` is auto-migrated on first run

## Operational Loop (Required)

1. **Onboard**
   ```bash
   sb list --json
   # or
   sb ready
   ```
2. **Break down work**
   ```bash
   sb add "Parent task" --priority 1
   sb add "Subtask" --priority 1 --parent <parent_id>
   ```
3. **Work lifecycle explicitly**
   ```bash
   sb begin <id>
   sb review <id>
   sb finish <id>
   ```
   Use `sb pause <id>` if work is parked.
4. **Use dependencies and ready queue**
   ```bash
   sb dep <child_id> <parent_id>
   sb ready
   ```
5. **Close session cleanly**
   - Verify work (tests/screenshots as applicable)
   - Complete tasks with `sb finish <id>` or `sb done <id>`
   - Run `sb list --all`
   - Share completed work and the next task

## Command Playbook

Create and update:

```bash
sb init
sb add "Task Title" [--priority/-p N] [--desc/-d TEXT] [--parent ID]
sb update <id> [title=...] [desc=...] [p=...] [status=...] [parent=...]
sb begin <id> [--force-reopen]
sb pause <id>
sb review <id>
sb finish <id>
sb done <id>
```

List and inspect:

```bash
sb list
sb list --all
sb list --json
sb list --repo
sb list --global
sb ready
sb show <id> [--json]
sb search <keyword> [--repo|--global]
sb board [--json]
sb stats
```

Dependencies, context, and maintenance:

```bash
sb dep <child_id> <parent_id> [--repo|--global]
sb link <id> [branch=...] [worktree=...]
sb event <switch|create|merge|remove> [--task <id>]
sb promote <id>
sb compact
sb rm <id>
```

## Task Semantics

Priority values:

```bash
0 = P0 Critical (blocking)
1 = P1 High
2 = P2 Medium (default)
3 = P3 Low
```

IDs:
- Root task IDs are hash-based by default (for example `sb-a3f8e9`); sequential IDs (`sb-1`) are used in legacy or single-repo mode
- Subtasks append a numeric suffix (for example `sb-a3f8e9.1`)

Completion:
- Preferred lifecycle: `begin → review → finish` (requires task to be in Doing/Review)
- `sb done <id>` closes a task directly from any state, bypassing lifecycle validation

## End-of-Session Checklist (Must Do)

1. File follow-up work as explicit tasks/subtasks.
2. Verify implementation (tests/screenshots as applicable).
3. Move task status out of ambiguous states; complete done work (`finish` or `done`).
4. Optionally run `sb compact` to prune done items.
5. Commit code changes (use the `commit` skill if available, otherwise `git add -A && git commit -m "..."`).
6. Run `sb list --all` and confirm task state clarity.
7. Provide a brief handoff summary plus next task to pick up.

## Guardrails

- Do not leave completed work untracked; always close or split into follow-up tasks.
- Do not leave tasks stuck in `Doing`/`Review` at session end without explicit intent.
- Prefer repo-aware filters (`--repo`) when inside a repository; use `--global` for non-repo work.
