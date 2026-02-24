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

def find_db_path(cwd=None):
    """Walk up the directory tree to find .sb.json (local mode)."""
    cwd = cwd or os.getcwd()
    while cwd != os.path.dirname(cwd):  # Stop at root
        potential_path = os.path.join(cwd, ".sb.json")
        if os.path.exists(potential_path):
            return potential_path
        # Also stop at git root to keep it project-local
        if os.path.exists(os.path.join(cwd, ".git")):
            return os.path.join(cwd, ".sb.json")
        cwd = os.path.dirname(cwd)
    return os.path.join(os.getcwd(), ".sb.json")

def resolve_db_path(local=False, cwd=None):
    if local:
        return find_db_path(cwd=cwd)
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
    _bootstrap_child_counters(db)
    return db


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
    except (json.JSONDecodeError, IOError):
        return _ensure_db_shape({"issues": []})

def save_db(db, db_path=None):
    db_path = db_path or resolve_db_path()
    db = _ensure_db_shape(db)
    with open(db_path, "w") as f:
        json.dump(db, f, indent=2)

def init(local=False):
    db_path = resolve_db_path(local=local)
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
    
    # Create or append to AGENTS.md (local mode only)
    if not local:
        return

    # Create or append to AGENTS.md
    agents_md_content = """## Using SB Tracker

This project uses [SB Tracker](https://github.com/sirius-cc-wu/sb-tracker) for task tracking.

### Prerequisite

Install `sb` and ensure it is on your `PATH` before using these commands:
- `pipx install sb-tracker` (recommended for CLI tools)
- or `pip install sb-tracker`
- verify with `sb --help`

**Agents**: Please use the `sb` command to track work:
- `sb add "Task title" [priority] [description]` - Create a task
- `sb list` - View open tasks
- `sb ready` - See tasks ready to work on
- `sb done <id>` - Mark a task as complete
- `sb promote <id>` - Optional: generate a Markdown summary of task progress

### Priority Levels (Required Numeric Values)

When using `sb add`, specify priority as a **numeric value** (0-3):
- **0** = P0 (Critical) - Blocking other work
- **1** = P1 (High) - Important, do soon
- **2** = P2 (Medium) - Normal priority (default)
- **3** = P3 (Low) - Nice to have

Example: `sb add "Fix critical bug" 0 "This blocks release"`

Run `sb --help` for more commands.

### Landing the Plane (Session Completion)

**When ending a work session**, complete these steps:

1. **File remaining work** - Create issues for any follow-up tasks
2. **Verify** - Run project tests or take a screenshot to confirm the work is complete
3. **Update task status** - Mark completed work as done with `sb done <id>`
4. **Clean up** - Run `sb compact` if you want to remove closed tasks
5. **Commit local changes** - Commit code and `.sb.json` together. If a `commit` skill is available in the agent environment, use it. Otherwise run:
   ```bash
   git add -A
   git commit -m "type(scope): description of change"
   ```
6. **Final state check** - Run `sb list --all` and confirm no tasks are left ambiguous
7. **Handoff** - Share a short summary of what was completed and what remains

**CRITICAL RULES:**
- Always update task status before ending a session
- Never leave tasks in an ambiguous state; close them or create explicit sub-tasks
- Do not leave finished work uncommitted; commit issue-by-issue so progress is resumable
- Prefer the `commit` skill for commits when available; use raw git commit only as fallback
- `sb promote` is optional and only needed when you want a Markdown report
"""
    
    agents_md_path = os.path.join(os.path.dirname(db_path), "AGENTS.md")
    
    if os.path.exists(agents_md_path):
        # Check if "Using SB Tracker" section already exists
        with open(agents_md_path, "r") as f:
            content = f.read()
        
        if "## Using SB Tracker" not in content:
            # Append to existing file
            with open(agents_md_path, "a") as f:
                if not content.endswith("\n"):
                    f.write("\n")
                f.write("\n" + agents_md_content)
            print(f"Appended SB Tracker instructions to {agents_md_path}")
        # else: already has "Using SB Tracker" section, don't duplicate
    else:
        # Create new AGENTS.md
        with open(agents_md_path, "w") as f:
            f.write(agents_md_content)
        print(f"Created {agents_md_path} with SB Tracker instructions")

def search_issues(keyword, as_json=False, repo_filter=None, global_only=False, db_path=None):
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

def update_issue(issue_id, title=None, description=None, priority=None, parent_id=None, repo=None, repo_commit=None, repo_force=False, db_path=None):
    db = load_db(db_path=db_path)
    issue = next((i for i in db["issues"] if i["id"] == issue_id), None)
    if not issue:
        print(f"Error: Issue {issue_id} not found.")
        return

    changes = {}
    if title:
        changes["title"] = (issue["title"], title)
        issue["title"] = title
    if description is not None:
        changes["description"] = "updated"
        issue["description"] = description
    if priority is not None:
        changes["priority"] = (issue.get("priority", 2), priority)
        issue["priority"] = priority
    if parent_id is not None:
        # Hierarchy change
        old_parent = issue.get("parent")
        if parent_id == "": # Remove parent
            if "parent" in issue: del issue["parent"]
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
    print(f"**Status:** {issue['status']} | **Priority:** P{issue.get('priority', 2)}")
    if issue.get("description"):
        print(f"\n{issue['description']}")
    
    if children:
        print("\n#### Sub-tasks")
        for child in children:
            check = "x" if child["status"] == "closed" else " "
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

def add(title, description="", priority=2, depends_on=None, parent_id=None, repo=None, repo_commit=None, db_path=None):
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

    issue = {
        "id": new_id,
        "title": title,
        "description": description,
        "priority": priority,
        "status": "open",
        "depends_on": depends_on or [],
        "events": [],
        "created_at": created_at
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

def is_ready(issue, all_issues):
    if issue["status"] != "open":
        return False
    
    # Check if all dependencies are closed
    for dep_id in issue.get("depends_on", []):
        dep = next((i for i in all_issues if i["id"] == dep_id), None)
        if dep and dep["status"] != "closed":
            return False
    return True

def list_issues(show_all=False, as_json=False, ready_only=False, repo_filter=None, global_only=False, db_path=None):
    db = load_db(db_path=db_path)
    all_issues = db["issues"]
    
    if ready_only:
        issues = [i for i in all_issues if is_ready(i, all_issues)]
    elif not show_all:
        issues = [i for i in all_issues if i["status"] == "open"]
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
        status = i["status"]
        deps = ",".join(i.get("depends_on", []))
        if len(deps) > 10: deps = deps[:7] + "..."
        # Indent children
        indent = "  " * i["id"].count(".")
        print(f"{i['id']:<12} {i.get('priority', 2):<2} {status:<12} {deps:<10} {indent}{i['title']}")

def show_stats(db_path=None):
    db = load_db(db_path=db_path)
    issues = db["issues"]
    
    total = len(issues)
    open_count = len([i for i in issues if i["status"] == "open"])
    closed_count = len([i for i in issues if i["status"] == "closed"])
    ready_count = len([i for i in issues if is_ready(i, issues)])
    
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
    print(f"Closed:         {closed_count}")
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
    closed_issues = [i for i in db["issues"] if i["status"] == "closed"]
    
    if not closed_issues:
        print("No closed issues to compact.")
        return

    # Remove closed issues
    db["issues"] = [i for i in db["issues"] if i["status"] != "closed"]
    
    save_db(db, db_path=db_path)
    print(f"Successfully removed {len(closed_issues)} closed issues.")

def update_status(issue_id, status, db_path=None):
    db = load_db(db_path=db_path)
    for i in db["issues"]:
        if i["id"] == issue_id:
            old_status = i["status"]
            if old_status == status: return
            i["status"] = status
            log_event(i, "status_changed", {"old": old_status, "new": status})
            if status == "closed":
                i["closed_at"] = datetime.now().isoformat()
            save_db(db, db_path=db_path)
            print(f"Updated {issue_id} status to {status}")
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

def show_issue(issue_id, as_json=False, repo_filter=None, global_only=False, db_path=None):
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
                print(f"Status:      {i['status']}")
                print(f"Created:     {i['created_at']}")
                print(f"Depends On:  {', '.join(i.get('depends_on', [])) or 'None'}")
                
                dependents = [dep['id'] for dep in db["issues"] if i['id'] in dep.get('depends_on', [])]
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
    print("  stats                     Show task statistics")
    print("  compact                   Remove closed issues")
    print("  dep <child> <parent>      Add dependency")
    print("  update <id> [field=val]   Update title, desc, p, parent")
    print("  promote <id>              Export task as Markdown")
    print("  show <id> [--json]        Show issue details")
    print("  done <id>                 Close issue")
    print("  rm <id>                   Delete issue")
    print("  version                   Show version")
    print("\nGlobal tracker flags:")
    print("  --local                   Use repo-local .sb.json")
    print("  --repo [path]             Filter by repo (default: current repo)")
    print("  --global                  Filter only tasks with no repo")

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ["help", "--help", "-h"]:
        print_help()
        return

    def parse_common_flags(args):
        opts = {
            "local": False,
            "global_only": False,
            "repo": None,
            "repo_current": False,
        }
        cleaned = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--local":
                opts["local"] = True
                i += 1
                continue
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
            print("Usage: sb init [--local]")
            return
        init(local=opts["local"])
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
                except ValueError: pass
            
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
                db_path=resolve_db_path(local=opts["local"]),
            )
    elif cmd == "list":
        args, opts = parse_common_flags(sys.argv[2:])
        show_all = "--all" in args
        as_json = "--json" in args
        repo_filter = resolve_repo_filter(opts)
        list_issues(show_all, as_json, repo_filter=repo_filter, global_only=opts["global_only"], db_path=resolve_db_path(local=opts["local"]))
    elif cmd == "ready":
        args, opts = parse_common_flags(sys.argv[2:])
        as_json = "--json" in args
        repo_filter = resolve_repo_filter(opts)
        list_issues(as_json=as_json, ready_only=True, repo_filter=repo_filter, global_only=opts["global_only"], db_path=resolve_db_path(local=opts["local"]))
    elif cmd == "search":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb search <keyword> [--json]")
        else:
            as_json = "--json" in args
            repo_filter = resolve_repo_filter(opts)
            search_issues(args[0], as_json, repo_filter=repo_filter, global_only=opts["global_only"], db_path=resolve_db_path(local=opts["local"]))
    elif cmd == "update":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb update <id> [title=...] [desc=...] [p=...] [parent=...]")
        else:
            issue_id = args[0]
            kwargs = {}
            for arg in args[1:]:
                if "=" in arg:
                    k, v = arg.split("=", 1)
                    if k == "p": kwargs["priority"] = int(v)
                    elif k == "title": kwargs["title"] = v
                    elif k == "desc": kwargs["description"] = v
                    elif k == "parent": kwargs["parent_id"] = v
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
                db_path=resolve_db_path(local=opts["local"]),
                **kwargs,
            )
    elif cmd == "promote":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb promote <id>")
        else:
            promote_issue(args[0], db_path=resolve_db_path(local=opts["local"]))
    elif cmd == "stats":
        args, opts = parse_common_flags(sys.argv[2:])
        show_stats(db_path=resolve_db_path(local=opts["local"]))
    elif cmd == "compact":
        args, opts = parse_common_flags(sys.argv[2:])
        compact(db_path=resolve_db_path(local=opts["local"]))
    elif cmd == "dep":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 2:
            print("Usage: sb dep <child_id> <parent_id>")
        else:
            add_dependency(args[0], args[1], db_path=resolve_db_path(local=opts["local"]))
    elif cmd == "show":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb show <id> [--json]")
        else:
            as_json = "--json" in args
            repo_filter = resolve_repo_filter(opts)
            show_issue(args[0], as_json, repo_filter=repo_filter, global_only=opts["global_only"], db_path=resolve_db_path(local=opts["local"]))
    elif cmd == "done":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb done <id>")
        else:
            update_status(args[0], "closed", db_path=resolve_db_path(local=opts["local"]))
    elif cmd == "rm":
        args, opts = parse_common_flags(sys.argv[2:])
        if len(args) < 1:
            print("Usage: sb rm <id>")
        else:
            delete_issue(args[0], db_path=resolve_db_path(local=opts["local"]))
    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()
