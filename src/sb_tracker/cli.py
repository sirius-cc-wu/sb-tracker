#!/usr/bin/env python3
"""
Simple Beads (sb) - A minimal, standalone issue tracker for individuals.
No git hooks, no complex dependencies, just one local database file.
"""

import json
import os
import sys
import hashlib
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime

DEFAULT_DB_PATH = "~/.sb.sqlite"
LEGACY_JSON_DB_PATH = "~/.sb.json"
VALID_EVENT_TYPES = {"switch", "create", "merge", "remove"}


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


def _is_json_db_path(db_path):
    return os.path.splitext(db_path)[1].lower() == ".json"


def resolve_legacy_json_db_path():
    return os.path.expanduser(LEGACY_JSON_DB_PATH)


def resolve_db_path():
    env_path = os.environ.get("SB_DB_PATH")
    if env_path:
        return os.path.expanduser(env_path)
    return os.path.expanduser(DEFAULT_DB_PATH)


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


def _is_hierarchical_id(issue_id):
    if "." not in issue_id:
        return False
    parent, suffix = issue_id.rsplit(".", 1)
    return bool(parent) and suffix.isdigit()


def _bootstrap_child_counters(db):
    meta = db["meta"]
    counters = meta["child_counters"]
    if meta.get("child_counters_bootstrapped"):
        return
    for issue in db["issues"]:
        issue_id = issue.get("id", "")
        if not _is_hierarchical_id(issue_id):
            continue
        parent_id, suffix = issue_id.rsplit(".", 1)
        try:
            child_num = int(suffix)
        except ValueError:
            continue
        if child_num > counters.get(parent_id, 0):
            counters[parent_id] = child_num
    meta["child_counters_bootstrapped"] = True


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
    if "child_counters" not in meta or not isinstance(meta["child_counters"], dict):
        meta["child_counters"] = {}
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
    _bootstrap_child_counters(db)
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


def _load_db_from_json(db_path):
    if not os.path.exists(db_path):
        return _default_db_state()
    try:
        with open(db_path, "r") as f:
            return _ensure_db_shape(json.load(f))
    except json.JSONDecodeError as exc:
        print(
            f"Error: Failed to parse database file '{db_path}': {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    except OSError as exc:
        print(f"Error: Unable to read database file '{db_path}': {exc}", file=sys.stderr)
        raise SystemExit(1)


def _save_db_to_json(db, db_path):
    db = dict(_ensure_db_shape(db))
    db.pop("_storage_revision", None)

    dir_name = os.path.dirname(db_path) or "."
    os.makedirs(dir_name, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".sb-json-", suffix=".tmp", dir=dir_name)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(db, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, db_path)
    except OSError as exc:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        print(f"Error: Unable to write database file '{db_path}': {exc}", file=sys.stderr)
        raise SystemExit(1)


def _connect_sqlite(db_path):
    dir_name = os.path.dirname(db_path) or "."
    os.makedirs(dir_name, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _ensure_sqlite_storage(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS storage (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    state_row = conn.execute(
        "SELECT value FROM storage WHERE key = 'db_json'"
    ).fetchone()
    if state_row is None:
        conn.execute(
            "INSERT INTO storage (key, value) VALUES ('db_json', ?)",
            (json.dumps(_default_db_state(), indent=2),),
        )
    revision_row = conn.execute(
        "SELECT value FROM storage WHERE key = 'revision'"
    ).fetchone()
    if revision_row is None:
        conn.execute(
            "INSERT INTO storage (key, value) VALUES ('revision', '0')"
        )
    conn.commit()


def _load_db_from_sqlite(db_path):
    try:
        conn = _connect_sqlite(db_path)
    except sqlite3.Error as exc:
        print(f"Error: Unable to open SQLite database '{db_path}': {exc}", file=sys.stderr)
        raise SystemExit(1)
    try:
        _ensure_sqlite_storage(conn)
        state_row = conn.execute(
            "SELECT value FROM storage WHERE key = 'db_json'"
        ).fetchone()
        revision_row = conn.execute(
            "SELECT value FROM storage WHERE key = 'revision'"
        ).fetchone()
    finally:
        conn.close()

    try:
        db = _ensure_db_shape(json.loads(state_row[0] if state_row else "{}"))
    except json.JSONDecodeError as exc:
        print(
            f"Error: Failed to parse SQLite state payload in '{db_path}': {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    try:
        revision = int(revision_row[0]) if revision_row else 0
    except (TypeError, ValueError):
        revision = 0
    db["_storage_revision"] = revision
    return db


def _save_db_to_sqlite(db, db_path):
    expected_revision = db.get("_storage_revision")
    payload_db = dict(_ensure_db_shape(db))
    payload_db.pop("_storage_revision", None)
    payload = json.dumps(payload_db, indent=2)

    try:
        conn = _connect_sqlite(db_path)
    except sqlite3.Error as exc:
        print(f"Error: Unable to open SQLite database '{db_path}': {exc}", file=sys.stderr)
        raise SystemExit(1)

    try:
        _ensure_sqlite_storage(conn)
        conn.execute("BEGIN IMMEDIATE")
        current_row = conn.execute(
            "SELECT value FROM storage WHERE key = 'revision'"
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

        conn.execute(
            "UPDATE storage SET value = ? WHERE key = 'db_json'",
            (payload,),
        )
        conn.execute(
            "UPDATE storage SET value = ? WHERE key = 'revision'",
            (str(current_revision + 1),),
        )
        conn.commit()
        db["_storage_revision"] = current_revision + 1
    except sqlite3.Error as exc:
        conn.rollback()
        print(f"Error: SQLite write failed for '{db_path}': {exc}", file=sys.stderr)
        raise SystemExit(1)
    finally:
        conn.close()


def _migrate_legacy_json_to_sqlite_if_needed(db_path):
    default_db_path = os.path.expanduser(DEFAULT_DB_PATH)
    if db_path != default_db_path or os.path.exists(db_path):
        return
    legacy_path = resolve_legacy_json_db_path()
    if not os.path.exists(legacy_path):
        return

    legacy_db = _load_db_from_json(legacy_path)
    backup_path = f"{legacy_path}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
    try:
        shutil.copy2(legacy_path, backup_path)
    except OSError as exc:
        print(
            f"Error: Failed to create backup '{backup_path}' before migration: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    _save_db_to_sqlite(legacy_db, db_path)
    print(
        f"Migrated legacy database from '{legacy_path}' to '{db_path}' (backup: '{backup_path}').",
        file=sys.stderr,
    )


def load_db(db_path=None):
    db_path = db_path or resolve_db_path()
    if _is_json_db_path(db_path):
        return _load_db_from_json(db_path)
    _migrate_legacy_json_to_sqlite_if_needed(db_path)
    return _load_db_from_sqlite(db_path)


def save_db(db, db_path=None):
    db_path = db_path or resolve_db_path()
    if _is_json_db_path(db_path):
        _save_db_to_json(db, db_path)
        return
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
    elif parent_id:
        parent = next((i for i in db["issues"] if i["id"] == parent_id), None)
        if not parent:
            print(f"Error: Parent issue {parent_id} not found.")
            return

        counters = db["meta"]["child_counters"]
        next_sub = int(counters.get(parent_id, 0)) + 1
        existing_ids = {issue.get("id", "") for issue in db["issues"]}
        new_id = f"{parent_id}.{next_sub}"
        while new_id in existing_ids:
            next_sub += 1
            new_id = f"{parent_id}.{next_sub}"
        counters[parent_id] = next_sub
    else:
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


def link_issue(issue_id, branch=None, worktree=None, db_path=None):
    db = load_db(db_path=db_path)
    issue = next((i for i in db["issues"] if i["id"] == issue_id), None)
    if not issue:
        print(f"Error: Issue {issue_id} not found.")
        return
    if branch is None and worktree is None:
        print("Usage: sb link <id> [branch=<name>] [worktree=<path>]")
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

    print(f"{'ID':<12} {'P':<2} {'Status':<12} {'Deps':<10} {'Title'}")
    print("-" * 80)
    for i in issues:
        config = get_kanban_config(db, i.get("repo"))
        status = normalize_status(i["status"], config) or "Unmapped"
        deps = ",".join(i.get("depends_on", []))
        if len(deps) > 10:
            deps = deps[:7] + "..."
        # Indent children
        indent = "  " * i["id"].count(".")
        nr_tag = " ⚑" if i.get("needs_review") else ""
        print(
            f"{i['id']:<12} {i.get('priority', 2):<2} {status:<12} {deps:<10} {indent}{i['title']}{nr_tag}"
        )


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
    closed_issues = [i for i in db["issues"] if is_issue_done(i, db)]

    if not closed_issues:
        print("No done issues to compact.")
        return

    # Remove done issues
    db["issues"] = [i for i in db["issues"] if not is_issue_done(i, db)]

    save_db(db, db_path=db_path)
    print(f"Successfully removed {len(closed_issues)} done issues.")


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
            return
    print(f"Error: Issue {issue_id} not found.")


def print_help():
    print("Usage: sb <command> [args]")
    print("Commands:")
    print("  init                      Initialize database (global by default)")
    print("  add <title> [--priority/-p N] [--desc/-d TEXT] [--parent ID]   Add issue")
    print("  list [--all] [--json]     List all open issues (use --all to include closed)")
    print("  ready [--json]            List only issues with no unresolved dependencies")
    print("  search <keyword> [--json] Search titles and descriptions")
    print("  board [--json]            Show issues grouped into Kanban columns")
    print("  stats                     Show task statistics")
    print("  compact                   Remove done issues")
    print("  dep <child> <parent>      Add dependency")
    print("  update <id> [field=val]   Update title, desc, p, status, parent")
    print("  begin <id> [--force-reopen]   Move task to Doing and capture context")
    print("  pause <id>                Move task to Ready")
    print("  review <id>               Move task to Review")
    print("  finish <id>               Kanban transition: Doing/Review → Done state")
    print("  event <type> [--task <id>]    Record external lifecycle event")
    print("  link <id> [branch=...] [worktree=...]   Link task to context")
    print("  promote <id>              Export task as Markdown")
    print("  show <id> [--json]        Show issue details")
    print("  done <id>                 Close/archive issue (marks task complete from any state)")
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
            print("Usage: sb link <id> [branch=<name>] [worktree=<path>]")
        else:
            issue_id = args[0]
            branch = None
            worktree = None
            for arg in args[1:]:
                if arg.startswith("branch="):
                    branch = arg.split("=", 1)[1]
                elif arg.startswith("worktree="):
                    worktree = arg.split("=", 1)[1]
            link_issue(issue_id, branch=branch, worktree=worktree, db_path=resolve_db_path())
    elif cmd == "promote":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb promote <id>")
        else:
            promote_issue(args[0], db_path=resolve_db_path())
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
    elif cmd == "done":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb done <id>")
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
