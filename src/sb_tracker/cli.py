#!/usr/bin/env python3
"""
Simple Beads (sb) - A minimal, standalone issue tracker for individuals.
No git hooks, no complex dependencies, just one JSON file.
"""

import json
import os
import sys
import hashlib
import subprocess
from datetime import datetime


def resolve_db_path():
    env_path = os.environ.get("SB_DB_PATH")
    if env_path:
        return os.path.expanduser(env_path)
    return os.path.expanduser("~/.sb.json")


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


def _next_sequential_id(issues):
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
    return f"sb-{max_id + 1}"


def _next_hash_id(issues, title, description, created_at):
    existing_ids = {issue.get("id", "") for issue in issues}
    for length in range(6, 9):
        for nonce in range(100):
            content = f"{title}|{description}|{created_at}|{nonce}"
            digest = hashlib.sha256(content.encode("utf-8")).digest()[:5]
            short = _encode_base36(digest, length)
            candidate = f"sb-{short}"
            if candidate not in existing_ids:
                return candidate
    raise RuntimeError("failed to generate unique hash ID")


def _next_top_level_id(db, title, description, created_at):
    mode = db.get("meta", {}).get("id_mode", "hash")
    if mode == "sequential":
        return _next_sequential_id(db["issues"])
    return _next_hash_id(db["issues"], title, description, created_at)


def load_db(db_path=None):
    db_path = db_path or resolve_db_path()
    if not os.path.exists(db_path):
        return _ensure_db_shape({"issues": []})
    try:
        with open(db_path, "r") as f:
            return _ensure_db_shape(json.load(f))
    except json.JSONDecodeError as exc:
        print(f"Error: Failed to parse database file '{db_path}': {exc}", file=sys.stderr)
        raise SystemExit(1)
    except OSError as exc:
        print(f"Error: Unable to read database file '{db_path}': {exc}", file=sys.stderr)
        raise SystemExit(1)


def save_db(db, db_path=None):
    db_path = db_path or resolve_db_path()
    db = _ensure_db_shape(db)
    with open(db_path, "w") as f:
        json.dump(db, f, indent=2)


def init():
    db_path = resolve_db_path()
    if os.path.exists(db_path):
        print(f"Error: {db_path} already exists.")
        return
    save_db(
        {
            "issues": [],
            "meta": {
                "id_mode": "hash",
                "child_counters": {},
                "child_counters_bootstrapped": True,
            },
        },
        db_path=db_path,
    )
    print(f"Initialized Simple Beads in {db_path}")


def search_issues(
    keyword, as_json=False, repo_filter=None, global_only=False, db_path=None
):
    db = load_db(db_path=db_path)
    keyword = keyword.lower()
    results = []
    for i in db["issues"]:
        if global_only and i.get("repo") is not None:
            continue
        if repo_filter is not None and i.get("repo") != repo_filter:
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
    repo_force=False,
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
    db_path=None,
):
    db = load_db(db_path=db_path)
    created_at = datetime.now().isoformat()

    if parent_id:
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
        new_id = _next_top_level_id(db, title, description, created_at)

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

    log_event(issue, "created", {"title": title})
    db["issues"].append(issue)
    save_db(db, db_path=db_path)
    print(f"Created {new_id}: {title} (P{priority})")


def add_dependency(child_id, parent_id, db_path=None):
    db = load_db(db_path=db_path)
    child = next((i for i in db["issues"] if i["id"] == child_id), None)
    parent = next((i for i in db["issues"] if i["id"] == parent_id), None)

    if not child:
        print(f"Error: Child issue {child_id} not found.")
        return
    if not parent:
        print(f"Error: Parent issue {parent_id} not found.")
        return

    if parent_id not in child["depends_on"]:
        child["depends_on"].append(parent_id)
        log_event(child, "dep_added", {"parent": parent_id})
        save_db(db, db_path=db_path)
        print(f"Linked {child_id} -> depends on -> {parent_id}")
    else:
        print(f"Already linked.")


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
    elif repo_filter is not None:
        issues = [i for i in issues if i.get("repo") == repo_filter]

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
        print(
            f"{i['id']:<12} {i.get('priority', 2):<2} {status:<12} {deps:<10} {indent}{i['title']}"
        )


def board_view(as_json=False, repo_filter=None, global_only=False, db_path=None):
    db = load_db(db_path=db_path)
    issues = db["issues"]

    if global_only:
        issues = [i for i in issues if i.get("repo") is None]
    elif repo_filter is not None:
        issues = [i for i in issues if i.get("repo") == repo_filter]

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
    print("  add <title> [p] [desc] [parent]   Add issue")
    print("  list [--all] [--json]     List issues")
    print("  ready [--json]            List issues with no open blockers")
    print("  search <keyword> [--json] Search titles and descriptions")
    print("  board [--json]            Show Kanban board")
    print("  stats                     Show task statistics")
    print("  compact                   Remove done issues")
    print("  dep <child> <parent>      Add dependency")
    print("  update <id> [field=val]   Update title, desc, p, status, parent")
    print("  status <id> <state>       Move issue to a Kanban state")
    print("  promote <id>              Export task as Markdown")
    print("  show <id> [--json]        Show issue details")
    print("  done <id>                 Close issue")
    print("  rm <id>                   Delete issue")
    print("  version                   Show version")
    print("\nGlobal tracker flags:")
    print("  --repo [path]             Filter by repo (default: current repo)")
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
            print("Usage: sb add <title> [priority] [description] [parent_id]")
        else:
            title = args[0]
            p = 2
            desc = ""
            parent = None

            rest = args[1:]
            if rest:
                try:
                    p = int(rest[0])
                    rest = rest[1:]
                except ValueError:
                    pass

            if rest:
                desc = rest[0]
                rest = rest[1:]

            if rest:
                parent = rest[0]

            repo = None
            repo_commit = None
            if not opts["global_only"]:
                repo = resolve_repo_filter(opts, default_current=True)
                if repo:
                    repo_commit = get_repo_commit(cwd=repo)

            add(
                title,
                desc,
                p,
                parent_id=parent,
                repo=repo,
                repo_commit=repo_commit,
                db_path=resolve_db_path(),
            )
    elif cmd == "list":
        args, opts = parse_common_flags(sys.argv[2:])
        show_all = "--all" in args
        as_json = "--json" in args
        repo_filter = resolve_repo_filter(opts)
        list_issues(
            show_all,
            as_json,
            repo_filter=repo_filter,
            global_only=opts["global_only"],
            db_path=resolve_db_path(),
        )
    elif cmd == "ready":
        args, opts = parse_common_flags(sys.argv[2:])
        as_json = "--json" in args
        repo_filter = resolve_repo_filter(opts)
        list_issues(
            as_json=as_json,
            ready_only=True,
            repo_filter=repo_filter,
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
            search_issues(
                args[0],
                as_json,
                repo_filter=repo_filter,
                global_only=opts["global_only"],
                db_path=resolve_db_path(),
            )
    elif cmd == "board":
        args, opts = parse_common_flags(sys.argv[2:])
        as_json = "--json" in args
        repo_filter = resolve_repo_filter(opts)
        board_view(
            as_json=as_json,
            repo_filter=repo_filter,
            global_only=opts["global_only"],
            db_path=resolve_db_path(),
        )
    elif cmd == "update":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb update <id> [title=...] [desc=...] [p=...] [status=...] [parent=...]")
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
            repo = None
            repo_commit = None
            repo_force = False
            if not opts["global_only"]:
                repo = resolve_repo_filter(opts, default_current=True)
                repo_force = bool(opts["repo_current"] or opts["repo"])
                if repo:
                    repo_commit = get_repo_commit(cwd=repo)
            update_issue(
                issue_id,
                repo=repo,
                repo_commit=repo_commit,
                repo_force=repo_force,
                db_path=resolve_db_path(),
                **kwargs,
            )
    elif cmd == "status":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 2:
            print("Usage: sb status <id> <state>")
        else:
            set_status(args[0], args[1], db_path=resolve_db_path())
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
            print("Usage: sb dep <child_id> <parent_id>")
        else:
            add_dependency(args[0], args[1], db_path=resolve_db_path())
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
    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
