# PRD: sb-tracker Storage and Migration

## Document Metadata
- Status: Draft (implementation-aligned)
- Owner: sb-tracker
- Last Updated: 2026-02-28
- Target: `sb-tracker` persistence layer

## 1. Problem Statement

`sb-tracker` needs durable local state with:
- zero external services,
- safe concurrent writes across CLI invocations,
- a single SQLite storage backend.

## 2. Goals

1. Provide a default global local database (`~/.sb.sqlite`) with robust writes.
2. Reject non-SQLite DB paths deterministically.
3. Reject stale concurrent writes deterministically.

## 3. Non-Goals

1. Multi-user networked storage.
2. ORM or external DB dependencies.
3. Cross-machine synchronization.

## 4. Functional Requirements

### 4.1 DB Path Resolution

1. If `SB_DB_PATH` is set, use it.
2. Else use `~/.sb.sqlite`.
3. If DB path extension is `.json`, fail with a deterministic error.

### 4.2 SQLite Storage Model

1. Use one `storage` table with key/value rows:
   - `db_json` (full logical state payload)
   - `revision` (monotonic integer revision)
2. Enforce WAL and durability-oriented pragmas:
   - `journal_mode=WAL`
   - `synchronous=FULL`
   - `busy_timeout=5000`

### 4.3 Concurrency Safety

1. Writes run in `BEGIN IMMEDIATE`.
2. Writes compare expected revision against current revision.
3. On mismatch, reject write with deterministic error:
   - `"Database changed by another process. Please retry the command."`

### 4.4 Legacy JSON Rejection

1. If legacy `~/.sb.json` exists, fail with a deterministic error.
2. No automatic migration or backup path is provided.

### 4.5 Logical State Shape

State must always normalize to:
- `issues: []`
- `meta` with:
  - `id_mode`
  - `child_counters`
  - `child_counters_bootstrapped`
  - `kanban`
  - `kanban_by_repo`

## 5. Interfaces

Primary implementation interfaces:
- `load_db(db_path=None)`
- `save_db(db, db_path=None)`
- `_load_db_from_sqlite`, `_save_db_to_sqlite`

## 6. Error Handling Requirements

1. Invalid JSON payloads must fail with parse error and non-zero exit.
2. SQLite connection/write failures must fail with non-zero exit.
3. JSON DB path and legacy `.sb.json` presence must fail with non-zero exit.

## 7. Testing Requirements

1. SQLite round-trip persistence.
2. Stale revision write rejection.
3. JSON DB path rejection.
4. Legacy `.sb.json` rejection.
5. SQLite open/write error paths.

Primary tests:
- `sb-tracker/tests/test_storage.py`
- `sb-tracker/tests/test_cli_coverage.py`

## 8. Acceptance Criteria

1. Fresh install runs with `~/.sb.sqlite` by default.
2. Concurrent stale writes are rejected safely.
3. JSON DB paths are rejected deterministically.
4. Legacy `~/.sb.json` presence is rejected deterministically.
