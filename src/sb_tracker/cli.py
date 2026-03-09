#!/usr/bin/env python3
"""
Simple Beads (sb) - A minimal, standalone issue tracker for individuals.
No git hooks, no complex dependencies, just one local database file.
"""

import json
import os
import sys
import hashlib
import sqlite3
import subprocess
from datetime import datetime, timedelta

from . import importer

DEFAULT_DB_PATH = "~/.sb.sqlite"
LEGACY_JSON_DB_PATH = "~/.sb.json"
VALID_EVENT_TYPES = {"switch", "create", "merge", "remove"}
COMPACT_RETENTION_DAYS = 90


def _default_db_state():
    return _ensure_db_shape(
        {
            "issues": [],
            "meta": {
                "id_mode": "hash",
                "id_prefix": "sb",
                "child_counters": {},
                "child_counters_bootstrapped": True,
            },
        }
    )


def resolve_db_path():
    env_path = os.environ.get("SB_DB_PATH")
    if env_path:
        return os.path.expanduser(env_path)
    return os.path.expanduser(DEFAULT_DB_PATH)


def _validate_sqlite_db_path(db_path):
    if os.path.splitext(db_path)[1].lower() == ".json":
        print(
            "Error: JSON database paths are no longer supported. Use a .sqlite path for SB_DB_PATH.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _fail_if_legacy_json_exists(db_path):
    if db_path != os.path.expanduser(DEFAULT_DB_PATH):
        return
    legacy_path = os.path.expanduser(LEGACY_JSON_DB_PATH)
    if os.path.exists(legacy_path):
        print(
            f"Error: Legacy JSON database '{legacy_path}' is no longer supported. "
            "Please migrate it manually to ~/.sb.sqlite and remove the JSON file.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _run_git(args, cwd=None):
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return result.stdout.strip()


def get_repo_root(cwd=None):
    cwd = cwd or os.getcwd()
    common_dir = _run_git(["rev-parse", "--git-common-dir"], cwd=cwd)
    if not common_dir:
        return None
    common_abs = os.path.abspath(os.path.join(cwd, common_dir))
    return os.path.realpath(os.path.dirname(common_abs))


def get_repo_commit(cwd=None):
    return _run_git(["rev-parse", "HEAD"], cwd=cwd)


def get_repo_branch(cwd=None):
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    if branch == "HEAD":
        return None
    return branch


def get_worktree_path(cwd=None):
    top = _run_git(["rev-parse", "--show-toplevel"], cwd=cwd)
    if not top:
        return None
    return os.path.realpath(top)


def _encode_base36(data, length):
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    num = int.from_bytes(data, "big")
    if num == 0:
        encoded = "0"
    else:
        chars = []
        while num > 0:
            num, rem = divmod(num, 36)
            chars.append(alphabet[rem])
        encoded = "".join(reversed(chars))
    if len(encoded) < length:
        encoded = ("0" * (length - len(encoded))) + encoded
    if len(encoded) > length:
        encoded = encoded[-length:]
    return encoded


def _ensure_db_shape(db):
    if not isinstance(db, dict):
        db = {}
    if "issues" not in db or not isinstance(db["issues"], list):
        db["issues"] = []
    if "meta" not in db or not isinstance(db["meta"], dict):
        db["meta"] = {}
    meta = db["meta"]
    if "id_mode" not in meta or not isinstance(meta["id_mode"], str):
        meta["id_mode"] = "hash"
    if "id_prefix" not in meta or not isinstance(meta["id_prefix"], str):
        meta["id_prefix"] = "sb"
    if "prefix_by_repo" not in meta or not isinstance(meta["prefix_by_repo"], dict):
        meta["prefix_by_repo"] = {}
    if "kanban" not in meta or not isinstance(meta["kanban"], dict):
        meta["kanban"] = {
            "columns": ["Backlog", "Ready", "Doing", "Review", "Done"],
            "backlog": "Backlog",
            "done": "Done",
        }
    else:
        if "columns" not in meta["kanban"] or not isinstance(meta["kanban"]["columns"], list):
            meta["kanban"]["columns"] = ["Backlog", "Ready", "Doing", "Review", "Done"]
        if "backlog" not in meta["kanban"] or not isinstance(meta["kanban"]["backlog"], str):
            meta["kanban"]["backlog"] = "Backlog"
        if "done" not in meta["kanban"] or not isinstance(meta["kanban"]["done"], str):
            meta["kanban"]["done"] = "Done"
    if "kanban_by_repo" not in meta or not isinstance(meta["kanban_by_repo"], dict):
        meta["kanban_by_repo"] = {}
    return db


def _normalize_kanban_config(config, fallback):
    normalized = {}
    normalized["columns"] = config.get("columns") if isinstance(config, dict) else None
    if not isinstance(normalized["columns"], list):
        normalized["columns"] = fallback["columns"]
    normalized["columns"] = list(normalized["columns"])
    normalized["backlog"] = config.get("backlog") if isinstance(config, dict) else None
    if not isinstance(normalized["backlog"], str):
        normalized["backlog"] = fallback["backlog"]
    normalized["done"] = config.get("done") if isinstance(config, dict) else None
    if not isinstance(normalized["done"], str):
        normalized["done"] = fallback["done"]
    if normalized["backlog"] not in normalized["columns"]:
        normalized["columns"].append(normalized["backlog"])
    if normalized["done"] not in normalized["columns"]:
        normalized["columns"].append(normalized["done"])
    return normalized


def get_kanban_config(db, repo_root=None):
    meta = db.get("meta", {})
    base = meta.get("kanban", {"columns": ["Backlog", "Ready", "Doing", "Review", "Done"], "backlog": "Backlog", "done": "Done"})
    if repo_root:
        repo_config = meta.get("kanban_by_repo", {}).get(repo_root)
        if isinstance(repo_config, dict):
            return _normalize_kanban_config(repo_config, base)
    return _normalize_kanban_config(base, base)


def normalize_status(status, config):
    if status == "open":
        return config["backlog"]
    if status == "closed":
        return config["done"]
    if status in config["columns"]:
        return status
    return None


def is_done_status(status, config):
    normalized = normalize_status(status, config)
    return normalized == config["done"]


def is_issue_done(issue, db):
    config = get_kanban_config(db, issue.get("repo"))
    return is_done_status(issue.get("status"), config)


def _apply_status_change(issue, new_status, config):
    normalized = normalize_status(new_status, config)
    if normalized is None:
        valid = ", ".join(config["columns"])
        print(f"Error: Invalid status '{new_status}'. Valid statuses: {valid}")
        return False
    old_status = issue.get("status")
    if old_status == normalized:
        return False
    issue["status"] = normalized
    log_event(issue, "status_changed", {"old": old_status, "new": normalized})
    if is_done_status(normalized, config):
        issue["closed_at"] = datetime.now().isoformat()
    else:
        if "closed_at" in issue:
            del issue["closed_at"]
    return True


def _next_sequential_id(issues, prefix="sb"):
    max_id = 0
    for issue in issues:
        issue_id = issue.get("id", "")
        if "." in issue_id:
            continue
        try:
            if "-" in issue_id:
                val = int(issue_id.split("-")[1])
                if val > max_id:
                    max_id = val
        except (IndexError, ValueError):
            continue
    return f"{prefix}-{max_id + 1}"


def _next_hash_id(issues, title, description, created_at, prefix="sb"):
    existing_ids = {issue.get("id", "") for issue in issues}
    for length in range(6, 9):
        for nonce in range(100):
            content = f"{title}|{description}|{created_at}|{nonce}"
            digest = hashlib.sha256(content.encode("utf-8")).digest()[:5]
            short = _encode_base36(digest, length)
            candidate = f"{prefix}-{short}"
            if candidate not in existing_ids:
                return candidate
    raise RuntimeError("failed to generate unique hash ID")


def _resolve_prefix(db, repo=None):
    meta = db.get("meta", {})
    if repo:
        repo_prefix = meta.get("prefix_by_repo", {}).get(repo)
        if repo_prefix:
            return repo_prefix
    return meta.get("id_prefix", "sb")


def _next_top_level_id(db, title, description, created_at, repo=None):
    mode = db.get("meta", {}).get("id_mode", "hash")
    prefix = _resolve_prefix(db, repo)
    if mode == "sequential":
        return _next_sequential_id(db["issues"], prefix=prefix)
    return _next_hash_id(db["issues"], title, description, created_at, prefix=prefix)


def _connect_sqlite(db_path):
    dir_name = os.path.dirname(db_path) or "."
    os.makedirs(dir_name, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _table_exists(conn, table_name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _is_v2_schema(conn):
    return (
        _table_exists(conn, "schema_info")
        and _table_exists(conn, "meta")
        and _table_exists(conn, "issues")
        and _table_exists(conn, "issue_dependencies")
        and _table_exists(conn, "issue_events")
    )


def _has_legacy_blob_storage(conn):
    if not _table_exists(conn, "storage"):
        return False
    row = conn.execute(
        "SELECT 1 FROM storage WHERE key = 'db_json'"
    ).fetchone()
    return row is not None


def _create_v2_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_info (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS issues (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            priority INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            closed_at TEXT,
            parent TEXT,
            repo TEXT,
            repo_commit TEXT,
            repo_branch TEXT,
            worktree_path TEXT,
            needs_review INTEGER NOT NULL DEFAULT 0,
            lifecycle_started_at TEXT,
            lifecycle_last_event_type TEXT,
            linked_files_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS issue_dependencies (
            child_id TEXT NOT NULL,
            parent_id TEXT NOT NULL,
            PRIMARY KEY (child_id, parent_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS issue_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_id TEXT NOT NULL,
            type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            payload_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_issue_events_issue_id
        ON issue_events(issue_id, id)
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO schema_info (key, value)
        VALUES ('version', '2')
        """
    )


def _upsert_meta(conn, key, value):
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        (key, value),
    )


def _delete_meta(conn, key):
    conn.execute("DELETE FROM meta WHERE key = ?", (key,))


def _serialize_event_payload(event):
    payload = {k: v for k, v in event.items() if k not in ("type", "timestamp")}
    if not payload:
        return None
    return json.dumps(payload, sort_keys=True)


def _write_v2_state(conn, db, revision):
    payload_db = dict(_ensure_db_shape(db))
    payload_db.pop("_storage_revision", None)

    conn.execute("DELETE FROM issue_events")
    conn.execute("DELETE FROM issue_dependencies")
    conn.execute("DELETE FROM issues")

    for issue in payload_db.get("issues", []):
        lifecycle = issue.get("lifecycle") or {}
        conn.execute(
            """
            INSERT INTO issues (
                id, title, description, priority, status, created_at, closed_at,
                parent, repo, repo_commit, repo_branch, worktree_path,
                needs_review, lifecycle_started_at, lifecycle_last_event_type,
                linked_files_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                issue["id"],
                issue["title"],
                issue.get("description", ""),
                issue.get("priority", 2),
                issue.get("status", "Backlog"),
                issue.get("created_at", datetime.now().isoformat()),
                issue.get("closed_at"),
                issue.get("parent"),
                issue.get("repo"),
                issue.get("repo_commit"),
                issue.get("repo_branch"),
                issue.get("worktree_path"),
                1 if issue.get("needs_review") else 0,
                lifecycle.get("started_at"),
                lifecycle.get("last_event_type"),
                json.dumps(issue.get("linked_files", []), sort_keys=True),
            ),
        )
        for dep in issue.get("depends_on", []):
            conn.execute(
                "INSERT OR IGNORE INTO issue_dependencies (child_id, parent_id) VALUES (?, ?)",
                (issue["id"], dep),
            )
        for event in issue.get("events", []):
            conn.execute(
                """
                INSERT INTO issue_events (issue_id, type, timestamp, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    issue["id"],
                    event.get("type", "unknown"),
                    event.get("timestamp", datetime.now().isoformat()),
                    _serialize_event_payload(event),
                ),
            )

    _upsert_meta(conn, "db_meta_json", json.dumps(payload_db.get("meta", {}), sort_keys=True))
    _upsert_meta(conn, "revision", str(revision))

    if "compaction_log" in payload_db:
        _upsert_meta(
            conn,
            "compaction_log_json",
            json.dumps(payload_db.get("compaction_log", []), sort_keys=True),
        )
    else:
        _delete_meta(conn, "compaction_log_json")


def _load_v2_state(conn):
    meta_row = conn.execute(
        "SELECT value FROM meta WHERE key = 'db_meta_json'"
    ).fetchone()
    revision_row = conn.execute(
        "SELECT value FROM meta WHERE key = 'revision'"
    ).fetchone()
    compaction_row = conn.execute(
        "SELECT value FROM meta WHERE key = 'compaction_log_json'"
    ).fetchone()

    default_meta = _default_db_state()["meta"]
    if meta_row is None:
        meta = default_meta
    else:
        try:
            parsed_meta = json.loads(meta_row[0])
        except json.JSONDecodeError as exc:
            print(
                f"Error: Failed to parse SQLite meta payload: {exc}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        meta = parsed_meta if isinstance(parsed_meta, dict) else default_meta

    try:
        revision = int(revision_row[0]) if revision_row else 0
    except (TypeError, ValueError):
        revision = 0

    deps = {}
    for child_id, parent_id in conn.execute(
        "SELECT child_id, parent_id FROM issue_dependencies"
    ).fetchall():
        deps.setdefault(child_id, []).append(parent_id)

    events = {}
    for issue_id, event_type, timestamp, payload_json in conn.execute(
        "SELECT issue_id, type, timestamp, payload_json FROM issue_events ORDER BY id"
    ).fetchall():
        event = {"type": event_type, "timestamp": timestamp}
        if payload_json:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError as exc:
                print(
                    f"Error: Failed to parse SQLite event payload: {exc}",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            if isinstance(payload, dict):
                event.update(payload)
        events.setdefault(issue_id, []).append(event)

    issues = []
    for row in conn.execute(
        """
        SELECT
            id, title, description, priority, status, created_at, closed_at, parent,
            repo, repo_commit, repo_branch, worktree_path, needs_review,
            lifecycle_started_at, lifecycle_last_event_type, linked_files_json
        FROM issues
        """
    ).fetchall():
        (
            issue_id,
            title,
            description,
            priority,
            status,
            created_at,
            closed_at,
            parent,
            repo,
            repo_commit,
            repo_branch,
            worktree_path,
            needs_review,
            lifecycle_started_at,
            lifecycle_last_event_type,
            linked_files_json,
        ) = row
        issue = {
            "id": issue_id,
            "title": title,
            "description": description or "",
            "priority": priority if priority is not None else 2,
            "status": status or "Backlog",
            "depends_on": deps.get(issue_id, []),
            "events": events.get(issue_id, []),
            "created_at": created_at or datetime.now().isoformat(),
        }
        if closed_at:
            issue["closed_at"] = closed_at
        if parent:
            issue["parent"] = parent
        if repo:
            issue["repo"] = repo
        if repo_commit:
            issue["repo_commit"] = repo_commit
        if repo_branch:
            issue["repo_branch"] = repo_branch
        if worktree_path:
            issue["worktree_path"] = worktree_path
        if needs_review:
            issue["needs_review"] = True
        if lifecycle_started_at or lifecycle_last_event_type:
            issue["lifecycle"] = {}
            if lifecycle_started_at:
                issue["lifecycle"]["started_at"] = lifecycle_started_at
            if lifecycle_last_event_type:
                issue["lifecycle"]["last_event_type"] = lifecycle_last_event_type
        
        if linked_files_json:
            try:
                issue["linked_files"] = json.loads(linked_files_json)
            except json.JSONDecodeError:
                issue["linked_files"] = []
        else:
            issue["linked_files"] = []
            
        issues.append(issue)

    db = _ensure_db_shape({"issues": issues, "meta": meta})
    if compaction_row and compaction_row[0]:
        try:
            compaction_log = json.loads(compaction_row[0])
        except json.JSONDecodeError as exc:
            print(
                f"Error: Failed to parse SQLite compaction log payload: {exc}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        if isinstance(compaction_log, list):
            db["compaction_log"] = compaction_log
    db["_storage_revision"] = revision
    return db


def _backup_sqlite_before_migration(conn, db_path):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = f"{db_path}.bak.{timestamp}"
    try:
        backup_conn = sqlite3.connect(backup_path, timeout=10.0)
        try:
            conn.backup(backup_conn)
        finally:
            backup_conn.close()
    except sqlite3.Error as exc:
        print(
            f"Error: Failed to create backup '{backup_path}' before migration: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return backup_path


def _migrate_legacy_blob_to_v2(conn, db_path):
    legacy_state_row = conn.execute(
        "SELECT value FROM storage WHERE key = 'db_json'"
    ).fetchone()
    legacy_revision_row = conn.execute(
        "SELECT value FROM storage WHERE key = 'revision'"
    ).fetchone()

    if not legacy_state_row:
        return

    backup_path = _backup_sqlite_before_migration(conn, db_path)
    try:
        legacy_db = _ensure_db_shape(json.loads(legacy_state_row[0]))
    except json.JSONDecodeError as exc:
        print(
            f"Error: Failed to parse legacy SQLite state payload in '{db_path}': {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    try:
        revision = int(legacy_revision_row[0]) if legacy_revision_row else 0
    except (TypeError, ValueError):
        revision = 0

    try:
        conn.execute("BEGIN IMMEDIATE")
        _create_v2_schema(conn)
        _write_v2_state(conn, legacy_db, revision)
        conn.execute("DROP TABLE IF EXISTS storage")
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        print(f"Error: SQLite migration failed for '{db_path}': {exc}", file=sys.stderr)
        raise SystemExit(1)

    print(
        f"Migrated legacy SQLite blob storage in '{db_path}' to normalized schema (backup: '{backup_path}').",
        file=sys.stderr,
    )


def _migrate_schema_if_needed(conn):
    # Check if linked_files_json column exists in issues table
    cursor = conn.execute("PRAGMA table_info(issues)")
    columns = [row[1] for row in cursor.fetchall()]
    if "linked_files_json" not in columns:
        try:
            conn.execute("ALTER TABLE issues ADD COLUMN linked_files_json TEXT")
            # Default to empty list JSON
            conn.execute("UPDATE issues SET linked_files_json = '[]'")
        except sqlite3.Error as exc:
            print(f"Error migrating schema: {exc}", file=sys.stderr)


def _ensure_sqlite_storage(conn, db_path=None):
    if _is_v2_schema(conn):
        _migrate_schema_if_needed(conn)
        return
    if _has_legacy_blob_storage(conn):
        if not db_path:
            print("Error: Missing database path for SQLite migration.", file=sys.stderr)
            raise SystemExit(1)
        _migrate_legacy_blob_to_v2(conn, db_path)
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        _create_v2_schema(conn)
        _write_v2_state(conn, _default_db_state(), 0)
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        print(f"Error: SQLite schema initialization failed: {exc}", file=sys.stderr)
        raise SystemExit(1)


def _load_db_from_sqlite(db_path):
    try:
        conn = _connect_sqlite(db_path)
    except sqlite3.Error as exc:
        print(f"Error: Unable to open SQLite database '{db_path}': {exc}", file=sys.stderr)
        raise SystemExit(1)
    try:
        _ensure_sqlite_storage(conn, db_path=db_path)
        db = _load_v2_state(conn)
    finally:
        conn.close()
    return db


def _save_db_to_sqlite(db, db_path):
    expected_revision = db.get("_storage_revision")

    try:
        conn = _connect_sqlite(db_path)
    except sqlite3.Error as exc:
        print(f"Error: Unable to open SQLite database '{db_path}': {exc}", file=sys.stderr)
        raise SystemExit(1)

    try:
        _ensure_sqlite_storage(conn, db_path=db_path)
        conn.execute("BEGIN IMMEDIATE")
        current_row = conn.execute(
            "SELECT value FROM meta WHERE key = 'revision'"
        ).fetchone()
        current_revision = int(current_row[0]) if current_row else 0
        if expected_revision is None:
            expected_revision = current_revision
        if expected_revision != current_revision:
            conn.rollback()
            print(
                "Error: Database changed by another process. Please retry the command.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        _write_v2_state(conn, db, current_revision + 1)
        conn.commit()
        db["_storage_revision"] = current_revision + 1
    except sqlite3.Error as exc:
        conn.rollback()
        print(f"Error: SQLite write failed for '{db_path}': {exc}", file=sys.stderr)
        raise SystemExit(1)
    finally:
        conn.close()


def load_db(db_path=None):
    db_path = db_path or resolve_db_path()
    _validate_sqlite_db_path(db_path)
    _fail_if_legacy_json_exists(db_path)
    return _load_db_from_sqlite(db_path)


def save_db(db, db_path=None):
    db_path = db_path or resolve_db_path()
    _validate_sqlite_db_path(db_path)
    _fail_if_legacy_json_exists(db_path)
    _save_db_to_sqlite(db, db_path)


def init():
    db_path = resolve_db_path()
    if os.path.exists(db_path):
        print(f"Error: {db_path} already exists.")
        return
    save_db(_default_db_state(), db_path=db_path)
    print(f"Initialized Simple Beads in {db_path}")


def search_issues(
    keyword,
    as_json=False,
    repo_filter=None,
    branch_filter=None,
    worktree_filter=None,
    global_only=False,
    db_path=None,
):
    db = load_db(db_path=db_path)
    keyword = keyword.lower()
    results = []
    for i in db["issues"]:
        if global_only and i.get("repo") is not None:
            continue
        if repo_filter is not None and i.get("repo") != repo_filter:
            continue
        if branch_filter is not None and i.get("repo_branch") != branch_filter:
            continue
        if worktree_filter is not None and i.get("worktree_path") != worktree_filter:
            continue
        if keyword in i["title"].lower() or keyword in i.get("description", "").lower():
            results.append(i)

    if as_json:
        print(json.dumps(results, indent=2))
        return

    if not results:
        print(f"No results found for '{keyword}'")
        return

    print(f"Search results for '{keyword}':")
    print(f"{'ID':<12} {'Status':<12} {'Title'}")
    print("-" * 60)
    for i in results:
        print(f"{i['id']:<12} {i['status']:<12} {i['title']}")


def update_issue(
    issue_id,
    title=None,
    description=None,
    priority=None,
    status=None,
    parent_id=None,
    repo=None,
    repo_commit=None,
    repo_branch=None,
    worktree_path=None,
    repo_force=False,
    needs_review=None,
    db_path=None,
):
    db = load_db(db_path=db_path)
    issue = next((i for i in db["issues"] if i["id"] == issue_id), None)
    if not issue:
        print(f"Error: Issue {issue_id} not found.")
        return

    changes = {}
    status_changed = False
    if title:
        changes["title"] = (issue["title"], title)
        issue["title"] = title
    if description is not None:
        changes["description"] = "updated"
        issue["description"] = description
    if priority is not None:
        changes["priority"] = (issue.get("priority", 2), priority)
        issue["priority"] = priority
    if status is not None:
        config = get_kanban_config(db, issue.get("repo"))
        status_changed = _apply_status_change(issue, status, config)
        if status_changed is False and normalize_status(status, config) is None:
            return
    if parent_id is not None:
        # Hierarchy change
        old_parent = issue.get("parent")
        if parent_id == "":  # Remove parent
            if "parent" in issue:
                del issue["parent"]
            changes["parent"] = (old_parent, None)
        else:
            issue["parent"] = parent_id
            changes["parent"] = (old_parent, parent_id)
    current_repo = issue.get("repo")
    if repo is not None:
        if current_repo is None and repo_force:
            issue["repo"] = repo
            current_repo = repo
            changes["repo"] = (None, repo)
        elif current_repo == repo:
            pass
    if repo_commit is not None:
        if current_repo is None and repo_force:
            issue["repo_commit"] = repo_commit
            changes["repo_commit"] = "updated"
        elif current_repo == repo:
            issue["repo_commit"] = repo_commit
            changes["repo_commit"] = "updated"
    if repo_branch is not None:
        if current_repo is None and repo_force:
            issue["repo_branch"] = repo_branch
            changes["repo_branch"] = "updated"
        elif current_repo == repo:
            issue["repo_branch"] = repo_branch
            changes["repo_branch"] = "updated"
    if worktree_path is not None:
        if current_repo is None and repo_force:
            issue["worktree_path"] = worktree_path
            changes["worktree_path"] = "updated"
        elif current_repo == repo:
            issue["worktree_path"] = worktree_path
            changes["worktree_path"] = "updated"

    if needs_review is not None:
        if needs_review:
            if not issue.get("needs_review"):
                issue["needs_review"] = True
                changes["needs_review"] = (False, True)
        else:
            if issue.get("needs_review"):
                del issue["needs_review"]
                changes["needs_review"] = (True, False)

    if changes:
        log_event(issue, "updated", {"changes": changes})
    if changes or status_changed:
        save_db(db, db_path=db_path)
        print(f"Updated {issue_id}")
    else:
        print("No changes specified.")


def promote_issue(issue_id, db_path=None):
    db = load_db(db_path=db_path)
    issue = next((i for i in db["issues"] if i["id"] == issue_id), None)
    if not issue:
        print(f"Error: Issue {issue_id} not found.")
        return

    children = [i for i in db["issues"] if i.get("parent") == issue_id]

    print(f"### [{issue['id']}] {issue['title']}")
    issue_config = get_kanban_config(db, issue.get("repo"))
    issue_status = normalize_status(issue["status"], issue_config) or "Unmapped"
    print(f"**Status:** {issue_status} | **Priority:** P{issue.get('priority', 2)}")
    if issue.get("description"):
        print(f"\n{issue['description']}")

    if children:
        print("\n#### Sub-tasks")
        for child in children:
            check = "x" if is_issue_done(child, db) else " "
            print(f"- [{check}] {child['id']}: {child['title']}")

    if issue.get("events"):
        print("\n#### Activity Log")
        for e in issue["events"]:
            ts = e["timestamp"].split("T")[0]
            if e["type"] == "created":
                print(f"- {ts}: Created")
            elif e["type"] == "status_changed":
                print(f"- {ts}: {e['old']} -> {e['new']}")
            elif e["type"] == "updated":
                print(f"- {ts}: Details updated")


def log_event(issue, event_type, details=None):
    event = {
        "type": event_type,
        "timestamp": datetime.now().isoformat(),
    }
    if details:
        event.update(details)
    if "events" not in issue:
        issue["events"] = []
    issue["events"].append(event)


def add(
    title,
    description="",
    priority=2,
    depends_on=None,
    parent_id=None,
    repo=None,
    repo_commit=None,
    repo_branch=None,
    worktree_path=None,
    needs_review=False,
    custom_id=None,
    db_path=None,
):
    db = load_db(db_path=db_path)
    created_at = datetime.now().isoformat()

    if custom_id is not None:
        existing_ids = {issue.get("id", "") for issue in db["issues"]}
        if custom_id in existing_ids:
            print(f"Error: ID '{custom_id}' already exists.")
            return
        new_id = custom_id
    else:
        if parent_id:
            parent = next((i for i in db["issues"] if i["id"] == parent_id), None)
            if not parent:
                print(f"Error: Parent issue {parent_id} not found.")
                return

        new_id = _next_top_level_id(db, title, description, created_at, repo=repo)

    config = get_kanban_config(db, repo)
    issue = {
        "id": new_id,
        "title": title,
        "description": description,
        "priority": priority,
        "status": config["backlog"],
        "depends_on": depends_on or [],
        "events": [],
        "created_at": created_at,
    }
    if parent_id:
        issue["parent"] = parent_id
    if repo is not None:
        issue["repo"] = repo
    if repo_commit is not None:
        issue["repo_commit"] = repo_commit
    if repo_branch is not None:
        issue["repo_branch"] = repo_branch
    if worktree_path is not None:
        issue["worktree_path"] = worktree_path
    if needs_review:
        issue["needs_review"] = True

    log_event(issue, "created", {"title": title})
    db["issues"].append(issue)
    save_db(db, db_path=db_path)
    print(f"Created {new_id}: {title} (P{priority})")


def add_dependency(child_id, parent_id, db_path=None, repo_filter=None, global_only=False):
    db = load_db(db_path=db_path)
    child = next((i for i in db["issues"] if i["id"] == child_id), None)
    parent = next((i for i in db["issues"] if i["id"] == parent_id), None)

    if not child:
        print(f"Error: Child issue {child_id} not found.")
        return
    if not parent:
        print(f"Error: Parent issue {parent_id} not found.")
        return

    if global_only:
        if child.get("repo") is not None:
            print(f"Error: {child_id} is not a global (non-repo) issue.")
            return
        if parent.get("repo") is not None:
            print(f"Error: {parent_id} is not a global (non-repo) issue.")
            return
    elif repo_filter is not None:
        if child.get("repo") != repo_filter:
            print(f"Error: {child_id} does not belong to repo {repo_filter}.")
            return
        if parent.get("repo") != repo_filter:
            print(f"Error: {parent_id} does not belong to repo {repo_filter}.")
            return

    if parent_id not in child["depends_on"]:
        child["depends_on"].append(parent_id)
        log_event(child, "dep_added", {"parent": parent_id})
        save_db(db, db_path=db_path)
        print(f"Linked {child_id} -> depends on -> {parent_id}")
    else:
        print(f"Already linked.")


def _touch_lifecycle(issue, event_type, started=False):
    now = datetime.now().isoformat()
    lifecycle = issue.setdefault("lifecycle", {})
    lifecycle["last_event_at"] = now
    lifecycle["last_event_type"] = event_type
    if started and "started_at" not in lifecycle:
        lifecycle["started_at"] = now


def _capture_context_from_cwd():
    repo = get_repo_root()
    if not repo:
        return None
    return {
        "repo": repo,
        "repo_commit": get_repo_commit(cwd=repo),
        "repo_branch": get_repo_branch(cwd=repo),
        "worktree_path": get_worktree_path(cwd=repo),
    }


def _apply_context_to_issue(issue, context):
    if not context:
        return False
    issue_repo = issue.get("repo")
    context_repo = context.get("repo")
    # Never silently overwrite context from another repo.
    if issue_repo and issue_repo != context_repo:
        return False
    changed = False
    for key in ("repo", "repo_commit", "repo_branch", "worktree_path"):
        value = context.get(key)
        if value is not None and issue.get(key) != value:
            issue[key] = value
            changed = True
    return changed


def _lifecycle_target(current_status, action, done_status, issue=None):
    if action == "begin":
        if current_status == done_status:
            return None
        return "Doing"
    if action == "pause":
        return "Ready" if current_status == "Doing" else None
    if action == "review":
        return "Review" if current_status == "Doing" else None
    if action == "finish":
        if current_status == "Review":
            return done_status
        if current_status == "Doing":
            if issue and issue.get("needs_review"):
                return "Review"
            return done_status
        return None
    return None


def _persist_lifecycle_outcome(db, issue, issue_id, event_name, changed, db_path):
    result = "updated" if changed else "noop"
    log_event(issue, event_name, {"result": result, "status": issue.get("status")})
    save_db(db, db_path=db_path)
    if changed:
        print(f"Updated {issue_id} status to {issue.get('status')}")
    else:
        print(f"No changes for {issue_id}")


def lifecycle_action(issue_id, action, force_reopen=False, db_path=None):
    db = load_db(db_path=db_path)
    issue = next((i for i in db["issues"] if i["id"] == issue_id), None)
    if not issue:
        print(f"Error: Issue {issue_id} not found.")
        return

    config = get_kanban_config(db, issue.get("repo"))
    current_status = normalize_status(issue.get("status"), config) or issue.get("status")
    done_status = config["done"]

    if action == "begin" and current_status == done_status and not force_reopen:
        _touch_lifecycle(issue, "lifecycle_begin")
        log_event(issue, "lifecycle_begin", {"result": "noop", "reason": "done"})
        save_db(db, db_path=db_path)
        print(f"No changes for {issue_id}: task is Done (use --force-reopen to resume)")
        return

    target = _lifecycle_target(current_status, action, done_status, issue=issue)
    changed = False
    if target is not None:
        changed = _apply_status_change(issue, target, config)

    # begin captures current repository context.
    context_changed = False
    if action == "begin":
        context_changed = _apply_context_to_issue(issue, _capture_context_from_cwd())

    event_name = f"lifecycle_{action}"
    changed_any = changed or context_changed
    _touch_lifecycle(issue, event_name, started=(action == "begin" and changed_any))
    _persist_lifecycle_outcome(db, issue, issue_id, event_name, changed_any, db_path)

    if action == "finish" and target == "Review":
        print(f"  ↳ Human sign-off required — run `sb finish {issue_id}` again to close.")


def link_issue(issue_id, branch=None, worktree=None, files=None, db_path=None):
    db = load_db(db_path=db_path)
    issue = next((i for i in db["issues"] if i["id"] == issue_id), None)
    if not issue:
        print(f"Error: Issue {issue_id} not found.")
        return
    if branch is None and worktree is None and files is None:
        print("Usage: sb link <id> [branch=<name>] [worktree=<path>] [file=<path>]")
        return

    changes = {}
    if branch is not None and issue.get("repo_branch") != branch:
        changes["repo_branch"] = {"old": issue.get("repo_branch"), "new": branch}
        issue["repo_branch"] = branch
    if worktree is not None:
        worktree_norm = os.path.realpath(os.path.abspath(os.path.expanduser(worktree)))
        if issue.get("worktree_path") != worktree_norm:
            changes["worktree_path"] = {
                "old": issue.get("worktree_path"),
                "new": worktree_norm,
            }
            issue["worktree_path"] = worktree_norm
    if files:
        # Normalize paths relative to worktree if available, else absolute
        normalized_files = []
        for f in files:
            normalized_files.append(os.path.realpath(os.path.abspath(os.path.expanduser(f))))
        
        current_files = issue.get("linked_files", [])
        new_files = list(set(current_files + normalized_files))
        if len(new_files) != len(current_files):
            changes["linked_files"] = {"old": current_files, "new": new_files}
            issue["linked_files"] = new_files

    _touch_lifecycle(issue, "context_linked")
    if changes:
        log_event(issue, "context_linked", {"result": "updated", "changes": changes})
        save_db(db, db_path=db_path)
        print(f"Linked context for {issue_id}")
    else:
        log_event(issue, "context_linked", {"result": "noop"})
        save_db(db, db_path=db_path)
        print(f"No changes for {issue_id}")


def _open_issues(db):
    return [i for i in db["issues"] if not is_issue_done(i, db)]


def _resolve_event_target(db, task_id=None, repo=None, branch=None, worktree=None):
    if task_id:
        issue = next((i for i in db["issues"] if i["id"] == task_id), None)
        if not issue:
            return None, "not_found"
        return issue, None

    candidates = _open_issues(db)
    if repo is not None:
        candidates = [i for i in candidates if i.get("repo") == repo]
    if branch is not None:
        branch_matches = [i for i in candidates if i.get("repo_branch") == branch]
        if len(branch_matches) == 1:
            return branch_matches[0], None
        if len(branch_matches) > 1:
            return None, "ambiguous_branch"
    if worktree is not None:
        worktree_matches = [i for i in candidates if i.get("worktree_path") == worktree]
        if len(worktree_matches) == 1:
            return worktree_matches[0], None
        if len(worktree_matches) > 1:
            return None, "ambiguous_worktree"
    return None, "no_match"


def _apply_event(issue, event_type, db):
    config = get_kanban_config(db, issue.get("repo"))
    current_status = normalize_status(issue.get("status"), config) or issue.get("status")
    done_status = config["done"]

    changed = False
    if event_type in ("switch", "create"):
        if current_status != done_status:
            changed = _apply_status_change(issue, "Doing", config)
    elif event_type == "merge":
        if current_status in ("Doing", "Review"):
            changed = _apply_status_change(issue, "Review", config)
    elif event_type == "remove":
        changed = False

    _touch_lifecycle(issue, "external_event")
    log_event(
        issue,
        "external_event",
        {
            "event": event_type,
            "result": "updated" if changed else "noop",
            "status": issue.get("status"),
        },
    )
    return changed
def record_event(
    event_type,
    task_id=None,
    repo=None,
    branch=None,
    worktree=None,
    db_path=None,
):
    if event_type not in VALID_EVENT_TYPES:
        print("Usage: sb event <switch|create|merge|remove> [--task <id>]")
        return

    db = load_db(db_path=db_path)
    issue, error = _resolve_event_target(
        db, task_id=task_id, repo=repo, branch=branch, worktree=worktree
    )
    if error:
        messages = {
            "not_found": f"Error: Issue {task_id} not found.",
            "ambiguous_branch": "No changes: multiple open tasks match repo+branch",
            "ambiguous_worktree": "No changes: multiple open tasks match repo+worktree",
            "no_match": "No changes: no matching open task",
        }
        print(messages[error])
        return

    changed = _apply_event(issue, event_type, db)
    save_db(db, db_path=db_path)
    if changed:
        print(f"Event {event_type}: updated {issue['id']} to {issue.get('status')}")
    else:
        print(f"Event {event_type}: recorded for {issue['id']}")


def is_ready(issue, all_issues, db):
    if is_issue_done(issue, db):
        return False

    # Check if all dependencies are done
    for dep_id in issue.get("depends_on", []):
        dep = next((i for i in all_issues if i["id"] == dep_id), None)
        if dep and not is_issue_done(dep, db):
            return False
    return True


def list_issues(
    show_all=False,
    as_json=False,
    ready_only=False,
    repo_filter=None,
    branch_filter=None,
    worktree_filter=None,
    global_only=False,
    db_path=None,
):
    db = load_db(db_path=db_path)
    all_issues = db["issues"]

    if ready_only:
        issues = [i for i in all_issues if is_ready(i, all_issues, db)]
    elif not show_all:
        issues = [i for i in all_issues if not is_issue_done(i, db)]
    else:
        issues = all_issues

    if global_only:
        issues = [i for i in issues if i.get("repo") is None]
    else:
        if repo_filter is not None:
            issues = [i for i in issues if i.get("repo") == repo_filter]
        if branch_filter is not None:
            issues = [i for i in issues if i.get("repo_branch") == branch_filter]
        if worktree_filter is not None:
            issues = [i for i in issues if i.get("worktree_path") == worktree_filter]

    # Sort by ID (to keep hierarchy together), then priority
    issues.sort(key=lambda x: (x["id"], x.get("priority", 2)))

    if as_json:
        # Include compaction log in JSON if it exists
        output = {"issues": issues}
        if db.get("compaction_log"):
            output["compaction_log"] = db["compaction_log"]
        print(json.dumps(output, indent=2))
        return

    if not issues:
        print("No issues found matching criteria.")
        if db.get("compaction_log"):
            print("\nCompaction Log (Archived):")
            for entry in db["compaction_log"]:
                print(f"  - {entry['summary']}")
        return

    # Build tree
    issue_map = {i["id"]: i for i in issues}
    children_map = {}
    roots = []

    # Populate children map and roots
    for i in issues:
        # Check "parent" (storage key)
        pid = i.get("parent")
        
        # Fallback to old dot-notation for legacy IDs
        if not pid and "." in i["id"]:
            pid = i["id"].rsplit(".", 1)[0]
        
        if pid and pid in issue_map:
            children_map.setdefault(pid, []).append(i)
        else:
            roots.append(i)

    # Sort roots and children
    roots.sort(key=lambda x: (x.get("priority", 2), x["id"]))
    for pid in children_map:
        children_map[pid].sort(key=lambda x: (x.get("priority", 2), x["id"]))

    print(f"{'ID':<12} {'P':<2} {'Status':<12} {'Deps':<10} {'Title'}")
    print("-" * 80)

    def print_tree_recursive(issue, prefix="", is_last=False, is_root=True):
        config = get_kanban_config(db, issue.get("repo"))
        status = normalize_status(issue.get("status", "Backlog"), config) or "Unmapped"
        deps = ",".join(issue.get("depends_on", []))
        if len(deps) > 10:
             deps = deps[:7] + "..."
        
        # Determine connector for THIS node
        connector = ""
        if not is_root:
             connector = "└─ " if is_last else "├─ "

        nr_tag = " ⚑" if issue.get("needs_review") else ""
        
        # Print current node
        print(f"{issue['id']:<12} {issue.get('priority', 2):<2} {status:<12} {deps:<10} {prefix}{connector}{issue['title']}{nr_tag}")

        # Prepare prefix for CHILDREN of this node
        child_prefix = prefix
        if not is_root:
             child_prefix += "   " if is_last else "│  "
        
        children = children_map.get(issue["id"], [])
        children.sort(key=lambda x: (x.get("priority", 2), x["id"]))

        for idx, child in enumerate(children):
             print_tree_recursive(child, child_prefix, is_last=(idx == len(children) - 1), is_root=False)

    for root in roots:
        print_tree_recursive(root)


def board_view(
    as_json=False,
    repo_filter=None,
    branch_filter=None,
    worktree_filter=None,
    global_only=False,
    db_path=None,
):
    db = load_db(db_path=db_path)
    issues = db["issues"]

    if global_only:
        issues = [i for i in issues if i.get("repo") is None]
    else:
        if repo_filter is not None:
            issues = [i for i in issues if i.get("repo") == repo_filter]
        if branch_filter is not None:
            issues = [i for i in issues if i.get("repo_branch") == branch_filter]
        if worktree_filter is not None:
            issues = [i for i in issues if i.get("worktree_path") == worktree_filter]

    config = get_kanban_config(db, repo_filter)
    columns = list(config["columns"])
    board = {col: [] for col in columns}
    unmapped = []

    for issue in issues:
        issue_config = get_kanban_config(db, issue.get("repo"))
        status = normalize_status(issue["status"], issue_config)
        if status in board:
            board[status].append(issue)
        else:
            unmapped.append(issue)

    for col in board:
        board[col].sort(key=lambda x: (x["id"], x.get("priority", 2)))
    unmapped.sort(key=lambda x: (x["id"], x.get("priority", 2)))

    if as_json:
        output = {"columns": []}
        for col in columns:
            output["columns"].append({"name": col, "issues": board[col]})
        if unmapped:
            output["columns"].append({"name": "Unmapped", "issues": unmapped})
        print(json.dumps(output, indent=2))
        return

    if not issues:
        print("No issues found matching criteria.")
        return

    for col in columns:
        print(f"{col}")
        print("-" * len(col))
        if not board[col]:
            print("  (empty)")
        else:
            for i in board[col]:
                print(f"  {i['id']}: {i['title']}")
        print("")

    if unmapped:
        print("Unmapped")
        print("--------")
        for i in unmapped:
            print(f"  {i['id']}: {i['title']} (status: {i['status']})")


def show_stats(db_path=None):
    db = load_db(db_path=db_path)
    issues = db["issues"]

    total = len(issues)
    open_count = len([i for i in issues if not is_issue_done(i, db)])
    closed_count = len([i for i in issues if is_issue_done(i, db)])
    ready_count = len([i for i in issues if is_ready(i, issues, db)])

    p_counts = {}
    for i in issues:
        p = f"P{i.get('priority', 2)}"
        p_counts[p] = p_counts.get(p, 0) + 1

    print("════════════════════════════════════════")
    print("  SB Tracker Statistics")
    print("════════════════════════════════════════")
    print(f"Total Issues:   {total}")
    print(f"Open:           {open_count}")
    print(f"Ready:          {ready_count}")
    print(f"Done:           {closed_count}")
    print("----------------------------------------")
    print("Priority Breakdown:")
    for p in sorted(p_counts.keys()):
        print(f"  {p}: {p_counts[p]}")

    if db.get("compaction_log"):
        print("----------------------------------------")
        print(f"Archived via Compaction: {len(db['compaction_log'])} entries")
    print("════════════════════════════════════════")


def compact(db_path=None):
    db = load_db(db_path=db_path)
    cutoff_naive = datetime.now() - timedelta(days=COMPACT_RETENTION_DAYS)
    compactable_ids = set()

    for issue in db["issues"]:
        if not is_issue_done(issue, db):
            continue
        closed_at = issue.get("closed_at")
        if not isinstance(closed_at, str):
            continue
        normalized = closed_at.replace("Z", "+00:00")
        try:
            closed_dt = datetime.fromisoformat(normalized)
        except ValueError:
            continue
        if closed_dt.tzinfo is None:
            if closed_dt <= cutoff_naive:
                compactable_ids.add(issue["id"])
            continue
        cutoff_aware = datetime.now(closed_dt.tzinfo) - timedelta(days=COMPACT_RETENTION_DAYS)
        if closed_dt <= cutoff_aware:
            compactable_ids.add(issue["id"])

    if not compactable_ids:
        print(f"No done issues older than {COMPACT_RETENTION_DAYS} days to compact.")
        return

    db["issues"] = [i for i in db["issues"] if i.get("id") not in compactable_ids]

    save_db(db, db_path=db_path)
    print(f"Successfully removed {len(compactable_ids)} done issues.")


def set_status(issue_id, status, db_path=None):
    db = load_db(db_path=db_path)
    for i in db["issues"]:
        if i["id"] == issue_id:
            config = get_kanban_config(db, i.get("repo"))
            target_status = status if status is not None else config["done"]
            changed = _apply_status_change(i, target_status, config)
            if not changed:
                return
            save_db(db, db_path=db_path)
            print(f"Updated {issue_id} status to {i['status']}")
            return
    print(f"Error: Issue {issue_id} not found.")


def delete_issue(issue_id, db_path=None):
    db = load_db(db_path=db_path)
    original_count = len(db["issues"])
    db["issues"] = [i for i in db["issues"] if i["id"] != issue_id]
    if len(db["issues"]) < original_count:
        save_db(db, db_path=db_path)
        print(f"Deleted {issue_id}")
    else:
        print(f"Error: Issue {issue_id} not found.")


def show_issue(
    issue_id, as_json=False, repo_filter=None, global_only=False, db_path=None
):
    db = load_db(db_path=db_path)
    for i in db["issues"]:
        if i["id"] == issue_id:
            if global_only and i.get("repo") is not None:
                print(f"Error: Issue {issue_id} not found.")
                return
            if repo_filter is not None and i.get("repo") != repo_filter:
                print(f"Error: Issue {issue_id} not found.")
                return
            if as_json:
                print(json.dumps(i, indent=2))
            else:
                print(f"ID:          {i['id']}")
                print(f"Title:       {i['title']}")
                print(f"Priority:    P{i.get('priority', 2)}")
                config = get_kanban_config(db, i.get("repo"))
                status = normalize_status(i["status"], config) or "Unmapped"
                print(f"Status:      {status}")
                print(f"Created:     {i['created_at']}")
                print(f"Depends On:  {', '.join(i.get('depends_on', [])) or 'None'}")
                if i.get("needs_review"):
                    print("Needs Review: yes")

                dependents = [
                    dep["id"]
                    for dep in db["issues"]
                    if i["id"] in dep.get("depends_on", [])
                ]
                print(f"Blocking:    {', '.join(dependents) or 'None'}")

                if i.get("description"):
                    print(f"\nDescription:\n{i['description']}")

                if i.get("repo"):
                    print(f"\nRepo:        {i['repo']}")
                if i.get("repo_commit"):
                    print(f"Repo Commit: {i['repo_commit']}")
                if i.get("repo_branch"):
                    print(f"Repo Branch: {i['repo_branch']}")
                if i.get("worktree_path"):
                    print(f"Worktree:    {i['worktree_path']}")
                if i.get("lifecycle"):
                    lifecycle = i["lifecycle"]
                    if lifecycle.get("started_at"):
                        print(f"Started At:  {lifecycle['started_at']}")
                    if lifecycle.get("last_event_type"):
                        print(f"Last Event:  {lifecycle.get('last_event_type')}")
                    if "last_verification_exit_code" in lifecycle:
                        code = lifecycle["last_verification_exit_code"]
                        result = "PASS" if code == 0 else f"FAIL ({code})"
                        print(f"Last Verify: {result}")

                if i.get("events"):
                    print("\nAudit Log:")
                    for e in i["events"]:
                        ts = e["timestamp"].split("T")[1][:8]
                        if e["type"] == "created":
                            print(f"  [{ts}] Created")
                        elif e["type"] == "status_changed":
                            print(f"  [{ts}] Status: {e['old']} -> {e['new']}")
                        elif e["type"] == "dep_added":
                            print(f"  [{ts}] Dependency added: {e['parent']}")
                        elif e["type"] == "verification_result":
                            res = "PASS" if e["exit_code"] == 0 else f"FAIL ({e['exit_code']})"
                            print(f"  [{ts}] Verified: {res} (cmd: {e['command']})")
            return
    print(f"Error: Issue {issue_id} not found.")



def import_tasks(file_path, parent_id=None, dry_run=False, db_path=None):
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' not found.")
        return

    try:
        with open(file_path, "r") as f:
            content = f.read()
    except OSError as e:
        print(f"Error reading file: {e}")
        return

    parsed_tasks = importer.parse_markdown_tasks(content)
    if not parsed_tasks:
        print("No tasks found in file.")
        return

    if dry_run:
        print(f"(dry run) would import {len(parsed_tasks)} tasks from {file_path}")
        # Indent display
        for task in parsed_tasks:
            indent = "  " * task["level"]
            status = "[x]" if task["status"] == "done" else "[ ]"
            print(f"{indent}{status} {task['title']}")
        return

    db = load_db(db_path=db_path)
    created_at = datetime.now().isoformat()
    config = get_kanban_config(db)
    
    # Context resolution
    repo = None
    repo_commit = None
    repo_branch = None
    worktree_path = None
    
    # Try to resolve context from current directory
    # (import assumes we are in the repo context of the plan)
    repo = get_repo_root()
    if repo:
        repo_commit = get_repo_commit(cwd=repo)
        repo_branch = get_repo_branch(cwd=repo)
        worktree_path = get_worktree_path(cwd=repo)

    # Stack to track parent IDs: [(level, id), ...]
    # Initialize with user-provided parent if any
    parent_stack = []
    if parent_id:
        parent = next((i for i in db["issues"] if i["id"] == parent_id), None)
        if not parent:
            print(f"Error: Parent issue {parent_id} not found.")
            return
        # Base level is -1 so level 0 tasks are children of parent_id
        parent_stack.append((-1, parent_id))

    imported_count = 0
    skipped_count = 0

    for task in parsed_tasks:
        # Resolve parent
        current_level = task["level"]
        
        # Pop from stack until we find a parent with level < current_level
        while parent_stack and parent_stack[-1][0] >= current_level:
            parent_stack.pop()
            
        current_parent_id = parent_stack[-1][1] if parent_stack else None

        # Check idempotency
        # Match by Title + Parent + Repo
        existing = None
        for issue in db["issues"]:
            if issue["title"] == task["title"]:
                # Check parent equality
                i_parent = issue.get("parent")
                if i_parent == current_parent_id:
                    # Check repo equality
                    if issue.get("repo") == repo:
                        existing = issue
                        break
        
        if existing:
            skipped_count += 1
            # Push to stack so children can find it
            parent_stack.append((current_level, existing["id"]))
            
            # Optional: Update status if plan says done but task is not?
            # For now, simplistic: if plan says done, mark done.
            if task["status"] == "done" and not is_issue_done(existing, db):
                 _apply_status_change(existing, config["done"], config)
            continue

        # Create new task
        new_id = _next_top_level_id(db, task["title"], "", created_at, repo=repo)
        
        issue = {
            "id": new_id,
            "title": task["title"],
            "description": "",
            "priority": 2,
            "status": config["done"] if task["status"] == "done" else config["backlog"],
            "depends_on": [],
            "events": [],
            "created_at": created_at,
        }
        if current_parent_id:
            issue["parent"] = current_parent_id
        if repo:
            issue["repo"] = repo
            issue["repo_commit"] = repo_commit
            issue["repo_branch"] = repo_branch
            issue["worktree_path"] = worktree_path
            
        if task["status"] == "done":
             issue["closed_at"] = created_at

        log_event(issue, "created", {"title": task["title"], "source": "import"})
        db["issues"].append(issue)
        imported_count += 1
        
        # Push to stack
        parent_stack.append((current_level, new_id))

    if imported_count > 0 or skipped_count > 0: # Only save if we did something or skipped something (meaning we read the DB)
        # Actually we only need to save if imported_count > 0 OR we updated status of existing tasks
        # For safety, just save.
        save_db(db, db_path=db_path)
        
    print(f"Imported {imported_count} tasks, Skipped {skipped_count} tasks.")



def run_verification(issue_id, command, db_path=None):
    db = load_db(db_path=db_path)
    issue = next((i for i in db["issues"] if i["id"] == issue_id), None)
    if not issue:
        print(f"Error: Issue {issue_id} not found.")
        return

    print(f"Verifying {issue_id} using command: {command}")
    
    try:
        # Run the command and capture output
        # Use shell=True to support pipelines and complex commands
        result = subprocess.run(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Merge stderr into stdout
            text=True,
            timeout=300 # 5 minute timeout for safety
        )
        output = result.stdout
        exit_code = result.returncode
    except subprocess.TimeoutExpired:
        print(f"Error: Verification timed out after 5 minutes.")
        output = "Verification timed out."
        exit_code = -1
    except Exception as e:
        print(f"Error executing command: {e}")
        output = str(e)
        exit_code = -2

    # Truncate output to avoid massive token usage in history
    max_output_len = 2048
    if len(output) > max_output_len:
        output = output[:max_output_len] + "\n... (output truncated)"

    # Log the result
    log_event(issue, "verification_result", {
        "command": command,
        "exit_code": exit_code,
        "output": output
    })
    
    # Store last result for quick show
    issue.setdefault("lifecycle", {})["last_verification_exit_code"] = exit_code

    config = get_kanban_config(db, issue.get("repo"))
    if exit_code == 0:
        print(f"Verification SUCCESS (Exit 0)")
        # Auto-advance status
        if issue.get("needs_review"):
            _apply_status_change(issue, "Review", config)
        else:
            _apply_status_change(issue, config["done"], config)
    else:
        print(f"Verification FAILED (Exit {exit_code})")
        # Ensure task remains in Doing or moves to Doing if it was in Backlog/Ready
        current_status = normalize_status(issue.get("status"), config)
        if current_status in (config["backlog"], "Ready"):
             _apply_status_change(issue, "Doing", config)

    save_db(db, db_path=db_path)


def show_context(issue_id, include_files=False, db_path=None):
    db = load_db(db_path=db_path)
    issue = next((i for i in db["issues"] if i["id"] == issue_id), None)
    if not issue:
        print(f"Error: Issue {issue_id} not found.")
        return

    config = get_kanban_config(db, issue.get("repo"))
    status = normalize_status(issue["status"], config) or "Unmapped"
    
    print(f"--- Task Context: {issue['id']} ---")
    print(f"Title: {issue['title']}")
    print(f"Status: {status} | Priority: P{issue.get('priority', 2)}")
    if issue.get("description"):
        print(f"\nDescription:\n{issue['description']}")

    # Environment
    print("\n--- Environment ---")
    if issue.get("repo"):
        print(f"Repo:   {issue['repo']}")
    if issue.get("repo_branch"):
        print(f"Branch: {issue['repo_branch']}")
    if issue.get("repo_commit"):
        print(f"Commit: {issue['repo_commit']}")

    # Verification Result
    last_verify = None
    if issue.get("events"):
        # Find the most recent verification_result
        for e in reversed(issue["events"]):
            if e["type"] == "verification_result":
                last_verify = e
                break
    
    if last_verify:
        print("\n--- Last Verification ---")
        res = "SUCCESS" if last_verify["exit_code"] == 0 else f"FAILED (Exit {last_verify['exit_code']})"
        print(f"Result:  {res}")
        print(f"Command: {last_verify['command']}")
        print(f"Time:    {last_verify['timestamp']}")
        print(f"\nOutput Snippet:\n{last_verify['output']}")

    # Linked Files
    linked_files = issue.get("linked_files", [])
    if linked_files:
        print("\n--- Linked Files ---")
        for f in linked_files:
            print(f"- {f}")
            if include_files:
                if os.path.exists(f):
                    try:
                        with open(f, "r") as fp:
                            content = fp.read(4096) # Truncate at 4KB
                            print(f"  ```\n{content}\n  ```")
                    except Exception as e:
                        print(f"  (Error reading file: {e})")
                else:
                    print("  (File not found)")

    # Sub-tasks
    children = [i for i in db["issues"] if i.get("parent") == issue_id]
    if children:
        print("\n--- Sub-tasks ---")
        for child in children:
            c_status = normalize_status(child["status"], config) or "Unmapped"
            print(f"- [{child['id']}] {c_status}: {child['title']}")

    print("\n--- End of Context ---")


def print_help():


    print("Usage: sb <command> [args]")
    print("Commands:")
    print("  init                      Initialize database (global by default)")
    print("  add <title> [--priority/-p N] [--desc/-d TEXT] [--parent ID]   Add issue")
    print("  import <file>             Import tasks from markdown list")
    print("  list [--all] [--json]     List all open issues (use --all to include closed)")
    print("  ready [--json]            List only issues with no unresolved dependencies")
    print("  search <keyword> [--json] Search titles and descriptions")
    print("  board [--json]            Show issues grouped into Kanban columns")
    print("  stats                     Show task statistics")
    print(f"  compact                   Remove done issues older than {COMPACT_RETENTION_DAYS} days")
    print("  dep <child> <parent>      Add dependency")
    print("  update <id> [field=val]   Update title, desc, p, status, parent")
    print("  begin <id> [--force-reopen]   Move task to Doing and capture context")
    print("  pause <id>                Move task to Ready")
    print("  review <id>               Move task to Review")
    print("  verify <id> --cmd \"<CMD>\"  Run verification command and log result")
    print("  finish <id>               Kanban transition: Doing/Review → Done state")
    print("  event <type> [--task <id>]    Record external lifecycle event")
    print("  link <id> [branch=...] [worktree=...]   Link task to context")
    print("  promote <id>              Export task as Markdown")
    print("  context <id> [--files]    Show hydration context for agents")
    print("  show <id> [--json]        Show issue details")
    print("  close <id>                Close/archive issue (marks task complete from any state)")
    print("  rm <id>                   Delete issue")
    print("  config prefix <PREFIX>    Set ID prefix for current repo (e.g. BNC)")
    print("  config prefix <PREFIX> --global  Set global default ID prefix")
    print("  config get prefix         Show effective ID prefix")
    print("  version                   Show version")
    print("\nGlobal tracker flags:")
    print("  --repo [path]             Filter by repo (default: current repo)")
    print("  --branch [name]           Filter by branch (default: current branch)")
    print("  --worktree [path]         Filter by worktree (default: current worktree)")
    print("  --global                  Filter only tasks with no repo")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ["help", "--help", "-h"]:
        print_help()
        return

    def parse_common_flags(args):
        opts = {
            "global_only": False,
            "repo": None,
            "repo_current": False,
            "branch": None,
            "branch_current": False,
            "worktree": None,
            "worktree_current": False,
        }
        cleaned = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--global":
                opts["global_only"] = True
                i += 1
                continue
            if arg == "--repo":
                if i + 1 < len(args) and not args[i + 1].startswith("-"):
                    opts["repo"] = args[i + 1]
                    i += 2
                else:
                    opts["repo_current"] = True
                    i += 1
                continue
            if arg == "--branch":
                if i + 1 < len(args) and not args[i + 1].startswith("-"):
                    opts["branch"] = args[i + 1]
                    i += 2
                else:
                    opts["branch_current"] = True
                    i += 1
                continue
            if arg == "--worktree":
                if i + 1 < len(args) and not args[i + 1].startswith("-"):
                    opts["worktree"] = args[i + 1]
                    i += 2
                else:
                    opts["worktree_current"] = True
                    i += 1
                continue
            cleaned.append(arg)
            i += 1
        return cleaned, opts

    def resolve_repo_filter(opts, cwd=None, default_current=False):
        if opts["global_only"]:
            return None
        if opts["repo_current"]:
            return get_repo_root(cwd=cwd)
        if opts["repo"]:
            repo_path = os.path.abspath(os.path.expanduser(opts["repo"]))
            repo_root = get_repo_root(cwd=repo_path)
            return repo_root or os.path.realpath(repo_path)
        if default_current:
            return get_repo_root(cwd=cwd)
        return None

    def resolve_worktree_filter(opts, cwd=None):
        if opts["global_only"]:
            return None
        if opts["worktree_current"]:
            return get_worktree_path(cwd=cwd)
        if opts["worktree"]:
            worktree = os.path.abspath(os.path.expanduser(opts["worktree"]))
            detected = get_worktree_path(cwd=worktree)
            return detected or os.path.realpath(worktree)
        return None

    def resolve_branch_filter(opts, cwd=None):
        if opts["global_only"]:
            return None
        if opts["branch_current"]:
            return get_repo_branch(cwd=cwd)
        if opts["branch"]:
            return opts["branch"]
        return None

    cmd = sys.argv[1]
    if cmd in ["version", "--version", "-v"]:
        import sb_tracker

        print(f"sb-tracker {sb_tracker.__version__}")
        return
    if cmd == "init":
        args, opts = parse_common_flags(sys.argv[2:])
        if args:
            print("Usage: sb init")
            return
        init()
    elif cmd == "add":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb add <title> [--priority/-p N] [--desc/-d TEXT] [--parent ID]")
        else:
            title = args[0]
            p = 2
            desc = ""
            parent = None
            needs_review = False
            custom_id = None

            rest = args[1:]
            named = []
            i = 0
            while i < len(rest):
                if rest[i] in ("--priority", "-p") and i + 1 < len(rest):
                    try:
                        p = int(rest[i + 1])
                    except ValueError:
                        pass
                    i += 2
                elif rest[i] in ("--desc", "-d") and i + 1 < len(rest):
                    desc = rest[i + 1]
                    i += 2
                elif rest[i] == "--parent" and i + 1 < len(rest):
                    parent = rest[i + 1]
                    i += 2
                elif rest[i] == "--needs-review":
                    needs_review = True
                    i += 1
                elif rest[i] == "--id" and i + 1 < len(rest):
                    custom_id = rest[i + 1]
                    i += 2
                else:
                    named.append(rest[i])
                    i += 1
            if named:
                print(f"Unrecognized add arguments: {' '.join(named)}")
                print("Usage: sb add <title> [--priority/-p N] [--desc/-d TEXT] [--parent ID] [--needs-review] [--id EXTERNAL_ID]")
                return

            repo = None
            repo_commit = None
            repo_branch = None
            worktree_path = None
            if not opts["global_only"]:
                repo = resolve_repo_filter(opts, default_current=True)
                if repo:
                    repo_commit = get_repo_commit(cwd=repo)
                    repo_branch = get_repo_branch(cwd=repo)
                    worktree_path = get_worktree_path(cwd=repo)

            add(
                title,
                desc,
                p,
                parent_id=parent,
                repo=repo,
                repo_commit=repo_commit,
                repo_branch=repo_branch,
                worktree_path=worktree_path,
                needs_review=needs_review,
                custom_id=custom_id,
                db_path=resolve_db_path(),
            )
    elif cmd == "import":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb import <file_path> [--parent ID] [--dry-run]")
        else:
            file_path = args[0]
            parent_id = None
            dry_run = False
            
            i = 1
            while i < len(args):
                if args[i] == "--parent" and i + 1 < len(args):
                    parent_id = args[i + 1]
                    i += 2
                elif args[i] == "--dry-run":
                    dry_run = True
                    i += 1
                else:
                    i += 1
            
            import_tasks(
                file_path, 
                parent_id=parent_id, 
                dry_run=dry_run, 
                db_path=resolve_db_path()
            )
    elif cmd == "list":
        args, opts = parse_common_flags(sys.argv[2:])
        show_all = "--all" in args
        as_json = "--json" in args
        repo_filter = resolve_repo_filter(opts)
        branch_filter = resolve_branch_filter(opts)
        worktree_filter = resolve_worktree_filter(opts)
        list_issues(
            show_all,
            as_json,
            repo_filter=repo_filter,
            branch_filter=branch_filter,
            worktree_filter=worktree_filter,
            global_only=opts["global_only"],
            db_path=resolve_db_path(),
        )
    elif cmd == "ready":
        args, opts = parse_common_flags(sys.argv[2:])
        as_json = "--json" in args
        repo_filter = resolve_repo_filter(opts)
        branch_filter = resolve_branch_filter(opts)
        worktree_filter = resolve_worktree_filter(opts)
        list_issues(
            as_json=as_json,
            ready_only=True,
            repo_filter=repo_filter,
            branch_filter=branch_filter,
            worktree_filter=worktree_filter,
            global_only=opts["global_only"],
            db_path=resolve_db_path(),
        )
    elif cmd == "search":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb search <keyword> [--json]")
        else:
            as_json = "--json" in args
            repo_filter = resolve_repo_filter(opts)
            branch_filter = resolve_branch_filter(opts)
            worktree_filter = resolve_worktree_filter(opts)
            search_issues(
                args[0],
                as_json,
                repo_filter=repo_filter,
                branch_filter=branch_filter,
                worktree_filter=worktree_filter,
                global_only=opts["global_only"],
                db_path=resolve_db_path(),
            )
    elif cmd == "board":
        args, opts = parse_common_flags(sys.argv[2:])
        as_json = "--json" in args
        repo_filter = resolve_repo_filter(opts)
        branch_filter = resolve_branch_filter(opts)
        worktree_filter = resolve_worktree_filter(opts)
        board_view(
            as_json=as_json,
            repo_filter=repo_filter,
            branch_filter=branch_filter,
            worktree_filter=worktree_filter,
            global_only=opts["global_only"],
            db_path=resolve_db_path(),
        )
    elif cmd == "update":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb update <id> [title=...] [desc=...] [p=...] [status=...] [parent=...] [needs_review=true|false]")
        else:
            issue_id = args[0]
            kwargs = {}
            for arg in args[1:]:
                if "=" in arg:
                    k, v = arg.split("=", 1)
                    if k == "p":
                        kwargs["priority"] = int(v)
                    elif k == "title":
                        kwargs["title"] = v
                    elif k == "desc":
                        kwargs["description"] = v
                    elif k == "status":
                        kwargs["status"] = v
                    elif k == "parent":
                        kwargs["parent_id"] = v
                    elif k == "needs_review":
                        kwargs["needs_review"] = v.lower() in ("true", "1", "yes")
            repo = None
            repo_commit = None
            repo_branch = None
            worktree_path = None
            repo_force = False
            if not opts["global_only"]:
                repo = resolve_repo_filter(opts, default_current=True)
                repo_force = bool(opts["repo_current"] or opts["repo"])
                if repo:
                    repo_commit = get_repo_commit(cwd=repo)
                    repo_branch = get_repo_branch(cwd=repo)
                    worktree_path = get_worktree_path(cwd=repo)
            update_issue(
                issue_id,
                repo=repo,
                repo_commit=repo_commit,
                repo_branch=repo_branch,
                worktree_path=worktree_path,
                repo_force=repo_force,
                db_path=resolve_db_path(),
                **kwargs,
            )
    elif cmd == "begin":
        args, opts = parse_common_flags(sys.argv[2:])
        force_reopen = "--force-reopen" in args
        args = [a for a in args if a != "--force-reopen"]
        if len(args) < 1:
            print("Usage: sb begin <id> [--force-reopen]")
        else:
            lifecycle_action(args[0], "begin", force_reopen=force_reopen, db_path=resolve_db_path())
    elif cmd == "pause":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb pause <id>")
        else:
            lifecycle_action(args[0], "pause", db_path=resolve_db_path())
    elif cmd == "review":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb review <id>")
        else:
            lifecycle_action(args[0], "review", db_path=resolve_db_path())
    elif cmd == "verify":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb verify <id> --cmd \"<command>\"")
        else:
            issue_id = args[0]
            command = None
            i = 1
            while i < len(args):
                if args[i] == "--cmd" and i + 1 < len(args):
                    command = args[i + 1]
                    i += 2
                else:
                    i += 1
            if not command:
                print("Usage: sb verify <id> --cmd \"<command>\"")
            else:
                run_verification(issue_id, command, db_path=resolve_db_path())
    elif cmd == "finish":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb finish <id>")
        else:
            lifecycle_action(args[0], "finish", db_path=resolve_db_path())
    elif cmd == "event":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb event <switch|create|merge|remove> [--task <id>]")
        else:
            event_type = args[0]
            task_id = None
            i = 1
            while i < len(args):
                if args[i] == "--task" and i + 1 < len(args):
                    task_id = args[i + 1]
                    i += 2
                else:
                    i += 1
            repo_filter = resolve_repo_filter(opts, default_current=True)
            branch_filter = resolve_branch_filter(opts)
            worktree_filter = resolve_worktree_filter(opts)
            record_event(
                event_type,
                task_id=task_id,
                repo=repo_filter,
                branch=branch_filter,
                worktree=worktree_filter,
                db_path=resolve_db_path(),
            )
    elif cmd == "link":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb link <id> [branch=...] [worktree=...] [file=...]")
        else:
            issue_id = args[0]
            branch = None
            worktree = None
            files = []
            for arg in args[1:]:
                if arg.startswith("branch="):
                    branch = arg.split("=", 1)[1]
                elif arg.startswith("worktree="):
                    worktree = arg.split("=", 1)[1]
                elif arg.startswith("file="):
                    files.append(arg.split("=", 1)[1])
            link_issue(issue_id, branch=branch, worktree=worktree, files=files, db_path=resolve_db_path())
    elif cmd == "promote":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb promote <id>")
        else:
            promote_issue(args[0], db_path=resolve_db_path())
    elif cmd == "context":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb context <id> [--files]")
        else:
            issue_id = args[0]
            include_files = "--files" in args
            show_context(issue_id, include_files=include_files, db_path=resolve_db_path())
    elif cmd == "stats":
        args, opts = parse_common_flags(sys.argv[2:])
        show_stats(db_path=resolve_db_path())
    elif cmd == "compact":
        args, opts = parse_common_flags(sys.argv[2:])
        compact(db_path=resolve_db_path())
    elif cmd == "dep":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 2:
            print("Usage: sb dep <child_id> <parent_id> [--repo|--global]")
        else:
            add_dependency(
                args[0],
                args[1],
                db_path=resolve_db_path(),
                repo_filter=resolve_repo_filter(opts),
                global_only=opts["global_only"],
            )
    elif cmd == "show":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb show <id> [--json]")
        else:
            as_json = "--json" in args
            repo_filter = resolve_repo_filter(opts)
            show_issue(
                args[0],
                as_json,
                repo_filter=repo_filter,
                global_only=opts["global_only"],
                db_path=resolve_db_path(),
            )
    elif cmd == "close":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb close <id>")
        else:
            set_status(args[0], None, db_path=resolve_db_path())
    elif cmd == "rm":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb rm <id>")
        else:
            delete_issue(args[0], db_path=resolve_db_path())
    elif cmd == "config":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 2:
            print("Usage: sb config prefix <PREFIX> [--global]")
            print("       sb config get prefix")
        elif args[0] == "get" and args[1] == "prefix":
            db = load_db(db_path=resolve_db_path())
            repo = resolve_repo_filter(opts, default_current=True)
            prefix = _resolve_prefix(db, repo)
            source = "repo" if (repo and db["meta"].get("prefix_by_repo", {}).get(repo)) else "global"
            print(f"Effective prefix: {prefix} (from {source})")
        elif args[0] == "prefix":
            raw_prefix = args[1].rstrip("-").upper()
            db = load_db(db_path=resolve_db_path())
            if opts["global_only"]:
                db["meta"]["id_prefix"] = raw_prefix
                save_db(db, db_path=resolve_db_path())
                print(f"Global prefix set to: {raw_prefix}")
            else:
                repo = resolve_repo_filter(opts, default_current=True)
                if not repo:
                    print("Error: not inside a git repo. Use --global to set the global prefix.")
                    return
                db["meta"].setdefault("prefix_by_repo", {})[repo] = raw_prefix
                save_db(db, db_path=resolve_db_path())
                print(f"Prefix for {repo} set to: {raw_prefix}")
        else:
            print("Usage: sb config prefix <PREFIX> [--global]")
            print("       sb config get prefix")
    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
