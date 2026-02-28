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
- compatibility with legacy JSON users.

## 2. Goals

1. Provide a default global local database (`~/.sb.sqlite`) with robust writes.
2. Preserve support for explicit JSON DB paths.
3. Automatically migrate legacy `~/.sb.json` to SQLite with backup.
4. Reject stale concurrent writes deterministically.

## 3. Non-Goals

1. Multi-user networked storage.
2. ORM or external DB dependencies.
3. Cross-machine synchronization.

## 4. Functional Requirements

### 4.1 DB Path Resolution

1. If `SB_DB_PATH` is set, use it.
2. Else use `~/.sb.sqlite`.
3. If DB path extension is `.json`, use JSON read/write mode.

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

### 4.4 Legacy Migration

1. On first default SQLite use, if `~/.sb.sqlite` is missing and `~/.sb.json` exists:
   - load legacy JSON,
   - create timestamped backup (`.sb.json.bak.<timestamp>`),
   - write state into SQLite.
2. Migration occurs only for default DB path, not custom DB targets.

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
- `_load_db_from_json`, `_save_db_to_json`
- `_load_db_from_sqlite`, `_save_db_to_sqlite`
- `_migrate_legacy_json_to_sqlite_if_needed`

## 6. Error Handling Requirements

1. Invalid JSON payloads must fail with parse error and non-zero exit.
2. SQLite connection/write failures must fail with non-zero exit.
3. Backup failures during migration must fail (no silent partial migration).

## 7. Testing Requirements

1. SQLite round-trip persistence.
2. Legacy JSON auto-migration and backup creation.
3. Stale revision write rejection.
4. Malformed JSON parse failure.
5. SQLite open/write error paths.

Primary tests:
- `sb-tracker/tests/test_storage.py`
- `sb-tracker/tests/test_cli_coverage.py`

## 8. Acceptance Criteria

1. Fresh install runs with `~/.sb.sqlite` by default.
2. Concurrent stale writes are rejected safely.
3. Legacy `~/.sb.json` users migrate automatically with backup.
4. JSON-mode DB path still works when explicitly selected.
