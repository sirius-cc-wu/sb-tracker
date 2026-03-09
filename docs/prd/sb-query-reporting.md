# PRD: sb-tracker Query, Filtering, and Reporting

## Document Metadata
- Status: Draft (implementation-aligned)
- Owner: sb-tracker
- Last Updated: 2026-02-28
- Target: read/query/report command surface

## 1. Problem Statement

Agents and developers need fast ways to:
- find actionable tasks,
- filter by working context (repo/branch/worktree/global),
- inspect details and audit history,
- export machine-readable data for automation.

## 2. Goals

1. Provide predictable list/search/report commands for daily execution.
2. Support context filters that align with multi-repo and multi-worktree usage.
3. Support both human-readable and JSON outputs.
4. Keep output stable enough for scripting.

## 3. Non-Goals

1. Interactive TUI or dashboard in v1.
2. External analytics backend.
3. Real-time streaming query APIs.

## 4. Query Command Requirements

### 4.1 List Family
1. `list` returns non-done tasks by default.
2. `list --all` includes done tasks.
3. `ready` returns only non-done tasks with all blockers resolved.

### 4.2 Search
1. `search <keyword>` matches title and description.
2. Case-insensitive matching.

### 4.3 Board
1. `board` groups tasks by effective status columns.
2. `board --json` returns structured column payload.

### 4.4 Detail and Summary
1. `show <id>` includes metadata, dependency relationships, and event log.
2. `promote <id>` renders Markdown summary suitable for sharing.
3. `stats` reports totals/open/ready/done and priority breakdown.

## 5. Filter Requirements

Supported global filters:
1. `--repo [path]`
2. `--branch [name]`
3. `--worktree [path]`
4. `--global`

Rules:
1. Omitted value for `--repo/--branch/--worktree` means infer current context.
2. `--global` limits results to tasks with no `repo`.
3. Filters compose across list/search/ready/board.

## 6. Output Requirements

### 6.1 Human Output
1. Deterministic tabular/section formats for common commands.
2. Hierarchy visualization: `list` and `ready` commands must render parent-child relationships using a tree structure with indentation and connectors (e.g., `└─`).
   - Root tasks are sorted by Priority/ID.
   - Child tasks are nested immediately under their parent.
3. Clear “no results” messages.
4. Concise summaries for lifecycle/event operations.

### 6.2 JSON Output
1. `list --json` returns issue array payload.
2. `show --json` returns full issue document.
3. `board --json` returns column-grouped payload.
4. JSON must include additive fields when present (`repo_branch`, `worktree_path`, `lifecycle`, `events`).

## 7. Compatibility Requirements

1. Additive fields must not break older consumers reading known keys only.
2. Existing command names and baseline output semantics remain stable.

## 8. Testing Requirements

1. Filter combinations (`repo`, `branch`, `worktree`, `global`) across query commands.
2. JSON output validity and shape for list/show/board.
3. No-result handling paths.
4. Branch/worktree metadata visibility in `show`.

Primary tests:
- `sb-tracker/tests/test_cli_coverage.py`

## 9. Acceptance Criteria

1. Users can isolate work by repo/branch/worktree with one command.
2. `ready` reliably surfaces executable tasks.
3. JSON outputs are script-friendly and include contextual metadata when available.
4. Reporting commands (`show`, `promote`, `stats`) cover day-to-day handoff needs.
