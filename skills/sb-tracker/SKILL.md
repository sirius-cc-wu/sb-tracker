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
- Paths ending in `.json` are not supported

## Operational Loop (Required)

1. **Onboard & Plan**
   - Draft a `plan.md` using the `plan` skill.
   - Ingest into the tracker: `sb import plan.md`
   - Review the ready queue: `sb ready`

2. **Work Lifecycle Explicitly**
   ```bash
   sb begin <id>
   sb verify <id> --cmd "pytest ..."
   sb review <id>
   sb finish <id>
   ```
   Use `sb pause <id>` if work is parked.

3. **Observe & Repair**
   - If verification fails, run `sb show <id>` to see the error context.
   - Iterate on code and re-run `sb verify`.

4. **Close Session Cleanly**
   - Mark completed work as `Done`.
   - Run `sb list --all`.
   - Share a brief handoff summary.

## Command Playbook

Create and update:

```bash
sb init
sb add "Task Title" [--priority/-p N] [--desc/-d TEXT] [--parent ID] [--needs-review] [--id EXTERNAL_ID]
sb import <file.md> [--parent ID] [--dry-run]
sb update <id> [title=...] [desc=...] [p=...] [status=...] [parent=...] [needs_review=true|false]
sb config prefix <PREFIX>          # set prefix for current repo (e.g. BNC)
sb config prefix <PREFIX> --global # set global default prefix
sb config get prefix               # show effective prefix
sb begin <id> [--force-reopen]
sb verify <id> --cmd "<CMD>"       # Run verification and log result
sb pause <id>
sb review <id>
sb finish <id>
sb close <id>
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

### Git Hook Integration (optional)

`sb event` is designed to be called from git hooks to auto-advance task status:

| Hook | Event | Effect |
|---|---|---|
| `post-checkout` | `switch` | → Doing |
| `post-merge` | `merge` | → Review |

```bash
# .git/hooks/post-checkout
#!/bin/bash
[ "$3" = "1" ] && sb event switch --repo --branch --worktree

# .git/hooks/post-merge
#!/bin/bash
sb event merge --repo --branch
```

`--branch` and `--worktree` without a value auto-detect from the current working directory.
`sb event` exits 0 silently when no matching task is found — safe to call unconditionally.

## Task Semantics

Priority values:

```bash
0 = P0 Critical (blocking)
1 = P1 High
2 = P2 Medium (default)
3 = P3 Low
```

IDs:
- Task IDs are hash-based by default: `<prefix>-xxxxxx` (e.g. `sb-a3f8e9`, `BNC-a3f8e9`)
- Child tasks use the same standard ID format (no suffixes).
- External IDs (Jira, etc.) can be set literally: `sb add "..." --id B1XF-3213`
- Configure prefix per-repo: `sb config prefix BNC` or globally: `sb config prefix SB --global`

Completion:
- Preferred lifecycle: `begin → review → finish` (requires task to be in Doing/Review)
- `sb close <id>` closes a task directly from any state, bypassing lifecycle validation

`needs_review` flag:
- Add `--needs-review` to `sb add` (or `sb update <id> needs_review=true`) to mark tasks that require human sign-off before closing.
- When set, `sb finish` from `Doing` moves to `Review` and prints a reminder instead of closing.
- A second `sb finish` from `Review` always closes to `Done` (human has confirmed).
- `sb close` ignores the flag and force-closes from any state.

## End-of-Session Checklist (Must Do)

1. File follow-up work as explicit tasks/subtasks.
2. Verify implementation (tests/screenshots as applicable).
3. Move task status out of ambiguous states; complete done work (`finish` or `close`).
4. Optionally run `sb compact` to prune done items.
5. Commit code changes (use the `commit` skill if available, otherwise `git add -A && git commit -m "..."`).
6. Run `sb list --all` and confirm task state clarity.
7. Provide a brief handoff summary plus next task to pick up.

## Guardrails

- Do not leave completed work untracked; always close or split into follow-up tasks.
- Do not leave tasks stuck in `Doing`/`Review` at session end without explicit intent.
- Prefer repo-aware filters (`--repo`) when inside a repository; use `--global` for non-repo work.
