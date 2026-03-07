# PRD: sb-tracker Lifecycle Implementation Plan

## Document Metadata
- Status: Completed (implementation reference)
- Owner: sb-tracker
- Last Updated: 2026-02-28
- Target: implementation tracking for `sb-lifecycle.md`

## 1. Problem Statement

The lifecycle PRD (`sb-lifecycle.md`) required a decision-complete execution plan that maps product requirements to concrete code and test changes.

## 2. Goals

1. Break lifecycle work into independently trackable tasks.
2. Map each task to exact files and test targets.
3. Define dependency ordering to reduce integration risk.
4. Define validation gates for acceptance.

## 3. Non-Goals

1. Introduce new product behavior beyond `sb-lifecycle.md`.
2. Replace the lifecycle PRD as source of requirements.
3. Track non-lifecycle roadmap work.

## 4. Scope and Delivery Strategy

1. Execute under epic `sb-tgtt4h`.
2. Keep `sb-tracker` standalone; external hooks call `sb` commands only.
3. Preserve backward compatibility for existing commands and records.

## 5. Work Breakdown Structure

### 5.1 Lifecycle command surface and transition engine
- Add `begin`, `pause`, `review`, `finish` command handlers.
- Implement transition rules and idempotent no-op behavior.
- Add lifecycle audit events.
- Preserve close-command behavior.

Primary files:
- `sb-tracker/src/sb_tracker/cli.py`

Primary tests:
- `sb-tracker/tests/test_cli_coverage.py`

### 5.2 External event ingestion
- Add `sb event <event_type> [--task <id>] [--repo <path>] [--branch <name>] [--worktree <path>]`.
- Support `switch`, `create`, `merge`, `remove`.
- Emit deterministic outcome messages.
- Record `external_event` audit entries.

Primary files:
- `sb-tracker/src/sb_tracker/cli.py`

Primary tests:
- `sb-tracker/tests/test_cli_coverage.py`

### 5.3 Task resolution and context linkage
- Resolve event target by explicit task first.
- Resolve by unique open-task match (`repo+branch`, then `repo+worktree`).
- No mutation on ambiguity/no match.
- Add `sb link <id> [branch=<name>] [worktree=<path>]`.

Primary files:
- `sb-tracker/src/sb_tracker/cli.py`

Primary tests:
- `sb-tracker/tests/test_cli_coverage.py`

### 5.4 Query enhancements
- Add `--branch [name]` for `list`, `ready`, `search`, `board`.
- Infer current branch when value omitted.
- Ensure coexistence with `--repo`, `--worktree`, `--global`.

Primary files:
- `sb-tracker/src/sb_tracker/cli.py`

Primary tests:
- `sb-tracker/tests/test_cli_coverage.py`

### 5.5 Data compatibility and output behavior
- Keep additive fields only (`repo_branch`, `worktree_path`, `lifecycle`).
- Avoid migration requirements.
- Preserve existing output behavior where unchanged.

Primary files:
- `sb-tracker/src/sb_tracker/cli.py`

Primary tests:
- `sb-tracker/tests/test_storage.py`
- `sb-tracker/tests/test_cli_coverage.py`

### 5.6 Documentation and adoption
- Update README workflow and integration examples.
- Update AGENTS operational loop.
- Update skill instructions.

Primary files:
- `sb-tracker/README.md`
- `sb-tracker/AGENTS.md`
- `sb-tracker/skills/sb-tracker/SKILL.md`

## 6. Tracker Mapping

Epic:
- `sb-tgtt4h` Integrate worktree context into sb issues

Implementation tasks:
- `sb-tgtt4h.1` Implement lifecycle transition engine + commands
- `sb-tgtt4h.2` Implement external event ingestion command
- `sb-tgtt4h.3` Implement task resolution by repo+branch/worktree
- `sb-tgtt4h.4` Implement `sb link` command for context binding
- `sb-tgtt4h.5` Add `--branch` filter support to list/ready/search/board
- `sb-tgtt4h.6` Add lifecycle and event test coverage
- `sb-tgtt4h.7` Update README/AGENTS/skill docs for lifecycle workflow

Related:
- `sb-cbme9h` Document worktrunk hook recipes for status automation

## 7. Implementation Order

1. `sb-tgtt4h.1` lifecycle engine and commands
2. `sb-tgtt4h.2` event command
3. `sb-tgtt4h.3` resolver logic
4. `sb-tgtt4h.4` link command
5. `sb-tgtt4h.5` branch filter
6. `sb-tgtt4h.6` tests and regression checks
7. `sb-tgtt4h.7` documentation updates

## 8. Validation and Acceptance

Validation commands:
- `PYTHONPATH=src python -m pytest -q -o addopts=''`

Acceptance criteria:
1. Lifecycle commands and event ingestion are implemented and tested.
2. Existing command behavior remains compatible.
3. Documentation reflects the implemented lifecycle workflow.
4. Tracker tasks above are completed.
