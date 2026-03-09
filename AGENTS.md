# SB Tracker (Simple Beads): Agentic Development Harness

A lightweight, standalone task tracker designed for **Harness Engineering**. It stores state in a local SQLite file, allowing individual agent sessions to maintain context and track long-running, multi-step tasks across repositories.

## The Harness Philosophy

Successful long-horizon agents rely on a strict **Autonomous Loop**:
1.  **Plan**: Draft a `plan.md` (Durable Project Memory).
2.  **Import**: Use `sb import` to convert the plan into executable tasks.
3.  **Act**: Implement the next "Ready" task.
4.  **Verify**: Use `sb verify` to run tests and log results to the task audit trail.
5.  **Observe & Repair**: Use `sb show` to analyze failures and iterate.
6.  **Update**: Advance the task status and sync documentation.

## Installation

```bash
pipx install sb-tracker
sb --help
```

## Core Workflow for Agents

### 1. Onboarding & Planning
At the start of a task, analyze the requirements and draft a Markdown plan (e.g., `plan.md`).
```bash
# Ingest the plan into the tracker
sb import plan.md
```

### 2. Execution Loop
Focus on the highest priority `ready` tasks.
```bash
sb ready                # Show tasks with no open blockers
sb begin <id>           # Move to Doing and capture repo context
```

### 3. Verification & Feedback (The Loop)
Never mark a task complete without verification.
```bash
# Run a test command and log the result to the task
sb verify <id> --cmd "pytest tests/test_feature.py"
```
*   **Success**: Automatically advances status to `Review` or `Done`.
*   **Failure**: Logs exit code/output to the task and keeps it in `Doing` for repair.

### 4. Context Recovery & Hydration
If a session restarts, use the tracker to instantly reconstruct the "Durable Project Memory."
```bash
# Get a single-shot context block including task spec, linked files, and last failure
sb context <id> --files
```
You can also use `sb list --json` for raw state inspection.

### 5. Handoff & Session Completion
Before ending a work session:
1.  **File remaining work**: Create issues for any follow-up tasks.
2.  **Verify**: Ensure all "Done" tasks have a passing `verification_result`.
3.  **Clean up**: Run `sb compact` to remove old closed tasks.
4.  **Commit**: Commit code changes.
5.  **Summary**: Provide a brief report of completed work and the next task.

## Commands

### Task Management
- **`add`**: `sb add <title> [--priority/-p N] [--desc/-d TEXT] [--parent ID] [--needs-review]`
- **`import`**: `sb import <file.md> [--parent ID] [--dry-run]` (Ingest Markdown plans)
- **`update`**: `sb update <id> [title=...] [desc=...] [p=...] [parent=...]`
- **`dep`**: `sb dep <child> <parent>` (Create blocking dependencies)

### Lifecycle & Verification
- **`begin <id>`**: Start active work (Doing).
- **`verify <id> --cmd "<CMD>"`**: Run tests and log results to the task audit trail.
- **`review <id>`**: Hand off for review.
- **`finish <id>`**: Complete work (Done).

### Inspection & Reporting
- **`list [--all] [--json] [--repo]`**: Shows tasks with hierarchy and status.
- **`ready`**: Shows tasks with no unresolved dependencies.
- **`show <id>`**: Displays details, context, and **Verification Audit Log**.
- **`promote <id>`**: Generates a Markdown summary of the task and its history.

## Priority Levels

- **0** = P0 (Critical) - Blocking other work.
- **1** = P1 (High) - Important, do soon.
- **2** = P2 (Medium) - Normal priority (default).
- **3** = P3 (Low) - Nice to have.
