import json
import sqlite3

import pytest

from sb_tracker import cli


def _issue(issue_id, title="task", status="Backlog", parent=None, repo=None):
    issue = {
        "id": issue_id,
        "title": title,
        "description": "",
        "priority": 2,
        "status": status,
        "depends_on": [],
        "events": [],
        "created_at": "2026-01-01T00:00:00",
    }
    if parent is not None:
        issue["parent"] = parent
    if repo is not None:
        issue["repo"] = repo
    return issue


def _run_main(monkeypatch, capsys, db_path, args):
    monkeypatch.setenv("SB_DB_PATH", str(db_path))
    monkeypatch.setattr(cli.sys, "argv", ["sb", *args])
    cli.main()
    captured = capsys.readouterr()
    return captured.out, captured.err


def test_core_helper_paths(capsys):
    assert cli._encode_base36(b"\x00", 4) == "0000"
    assert len(cli._encode_base36(b"\xff\xff\xff", 2)) == 2
    assert cli._is_hierarchical_id("sb-1.2")
    assert not cli._is_hierarchical_id("sb-1.x")
    assert not cli._is_hierarchical_id("sb-1")

    db = {
        "issues": [_issue("sb-1.2"), _issue("sb-1.5"), _issue("sb-bad.x")],
        "meta": {"child_counters": {}},
    }
    shaped = cli._ensure_db_shape(db)
    assert shaped["meta"]["child_counters"]["sb-1"] == 5
    assert shaped["meta"]["child_counters_bootstrapped"] is True

    fallback = {"columns": ["Backlog"], "backlog": "Backlog", "done": "Done"}
    normalized = cli._normalize_kanban_config({"columns": ["Doing"]}, fallback)
    assert "Backlog" in normalized["columns"]
    assert "Done" in normalized["columns"]

    kanban_db = {
        "meta": {
            "kanban": fallback,
            "kanban_by_repo": {
                "/tmp/repo": {"columns": ["Todo"], "backlog": "Todo", "done": "Shipped"}
            },
        }
    }
    repo_cfg = cli.get_kanban_config(kanban_db, "/tmp/repo")
    assert repo_cfg["backlog"] == "Todo"
    assert repo_cfg["done"] == "Shipped"
    assert cli.normalize_status("open", repo_cfg) == "Todo"
    assert cli.normalize_status("closed", repo_cfg) == "Shipped"
    assert cli.normalize_status("unknown", repo_cfg) is None

    issue = _issue("sb-1", status="Todo")
    assert cli._apply_status_change(issue, "invalid", repo_cfg) is False
    out = capsys.readouterr().out
    assert "Invalid status" in out

    assert cli._apply_status_change(issue, "Todo", repo_cfg) is False
    assert cli._apply_status_change(issue, "closed", repo_cfg) is True
    assert "closed_at" in issue
    assert cli._apply_status_change(issue, "Todo", repo_cfg) is True
    assert "closed_at" not in issue

    ids = [_issue("sb-1"), _issue("sb-3"), _issue("bad-id"), _issue("sb-2.1")]
    assert cli._next_sequential_id(ids) == "sb-4"
    assert cli._next_hash_id([], "t", "d", "ts").startswith("sb-")
    assert cli._next_top_level_id({"issues": ids, "meta": {"id_mode": "sequential"}}, "t", "d", "ts") == "sb-4"

    assert cli.get_repo_branch(cwd="/tmp/nope") is None
    assert cli.get_worktree_path(cwd="/tmp/nope") is None
    assert cli._lifecycle_target("Backlog", "begin", "Done") == "Doing"
    assert cli._lifecycle_target("Doing", "pause", "Done") == "Ready"
    assert cli._lifecycle_target("Doing", "review", "Done") == "Review"
    assert cli._lifecycle_target("Review", "finish", "Done") == "Done"
    assert cli._lifecycle_target("Done", "begin", "Done") is None


def test_json_and_sqlite_error_paths(tmp_path, monkeypatch):
    json_path = tmp_path / "data.json"
    cli._save_db_to_json(cli._default_db_state(), str(json_path))
    loaded = cli._load_db_from_json(str(json_path))
    assert loaded["issues"] == []

    broken = tmp_path / "broken.json"
    broken.write_text('{"issues":[{"id":"x",}]}', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        cli._load_db_from_json(str(broken))
    assert exc.value.code == 1

    monkeypatch.setattr(cli.os, "replace", lambda *_a, **_k: (_ for _ in ()).throw(OSError("replace failed")))
    with pytest.raises(SystemExit) as exc:
        cli._save_db_to_json(cli._default_db_state(), str(tmp_path / "will_fail.json"))
    assert exc.value.code == 1

    with pytest.raises(SystemExit) as exc:
        cli._load_db_from_sqlite(str(tmp_path))
    assert exc.value.code == 1

    sqlite_path = tmp_path / "state.sqlite"
    conn = cli._connect_sqlite(str(sqlite_path))
    cli._ensure_sqlite_storage(conn)
    conn.execute("UPDATE storage SET value = ? WHERE key = 'db_json'", ("{not json",))
    conn.commit()
    conn.close()
    with pytest.raises(SystemExit) as exc:
        cli._load_db_from_sqlite(str(sqlite_path))
    assert exc.value.code == 1

    sqlite_path_2 = tmp_path / "open-fail.sqlite"
    monkeypatch.setattr(
        cli.sqlite3,
        "connect",
        lambda *_a, **_k: (_ for _ in ()).throw(sqlite3.Error("connect fail")),
    )
    with pytest.raises(SystemExit) as exc:
        cli._save_db_to_sqlite(cli._default_db_state(), str(sqlite_path_2))
    assert exc.value.code == 1


def test_legacy_migration_failure_and_skip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy = tmp_path / ".sb.json"
    legacy.write_text(json.dumps(cli._default_db_state()), encoding="utf-8")

    custom_path = tmp_path / "custom.sqlite"
    cli._migrate_legacy_json_to_sqlite_if_needed(str(custom_path))
    assert not custom_path.exists()

    default_path = tmp_path / ".sb.sqlite"
    monkeypatch.setattr(
        cli.shutil,
        "copy2",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("backup failed")),
    )
    with pytest.raises(SystemExit) as exc:
        cli._migrate_legacy_json_to_sqlite_if_needed(str(default_path))
    assert exc.value.code == 1


def test_functional_commands_cover_paths(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "db.sqlite"
    monkeypatch.setenv("SB_DB_PATH", str(db_path))
    cli.init()
    out = capsys.readouterr().out
    assert "Initialized" in out

    cli.add("parent", "desc", 1, db_path=str(db_path))
    parent_id = cli.load_db(str(db_path))["issues"][0]["id"]
    cli.add("child", "", 2, parent_id=parent_id, db_path=str(db_path))
    db = cli.load_db(str(db_path))
    child_id = [i["id"] for i in db["issues"] if i.get("parent") == parent_id][0]

    cli.add("blocked", "", 2, db_path=str(db_path))
    blocked_id = [i["id"] for i in cli.load_db(str(db_path))["issues"] if i["title"] == "blocked"][0]
    cli.add(
        "with-meta",
        "",
        2,
        repo="/repo",
        repo_commit="c0ffee",
        repo_branch="feature-meta",
        worktree_path="/repo.feature-meta",
        db_path=str(db_path),
    )
    with_meta = next(i for i in cli.load_db(str(db_path))["issues"] if i["title"] == "with-meta")
    assert with_meta["repo_branch"] == "feature-meta"
    assert with_meta["worktree_path"] == "/repo.feature-meta"

    cli.add_dependency("missing", parent_id, db_path=str(db_path))
    cli.add_dependency(blocked_id, "missing", db_path=str(db_path))
    cli.add_dependency(blocked_id, parent_id, db_path=str(db_path))
    cli.add_dependency(blocked_id, parent_id, db_path=str(db_path))

    with_meta_id = with_meta["id"]

    cli.update_issue("missing", title="x", db_path=str(db_path))
    cli.update_issue(parent_id, status="bad-status", db_path=str(db_path))
    cli.update_issue(parent_id, db_path=str(db_path))
    cli.update_issue(parent_id, title="parent2", description="d2", priority=0, status="Doing", parent_id="", db_path=str(db_path))
    cli.update_issue(
        parent_id,
        repo="/repo",
        repo_force=True,
        repo_commit="abc123",
        repo_branch="feature-x",
        worktree_path="/repo.feature-x",
        db_path=str(db_path),
    )
    updated = next(i for i in cli.load_db(str(db_path))["issues"] if i["id"] == parent_id)
    assert updated["repo"] == "/repo"
    assert updated["repo_commit"] == "abc123"
    assert updated["repo_branch"] == "feature-x"
    assert updated["worktree_path"] == "/repo.feature-x"

    cli.list_issues(db_path=str(db_path))
    cli.list_issues(show_all=True, as_json=True, db_path=str(db_path))
    cli.list_issues(ready_only=True, db_path=str(db_path))
    cli.list_issues(repo_filter="/nope", db_path=str(db_path))
    cli.list_issues(branch_filter="feature-x", db_path=str(db_path))
    cli.list_issues(global_only=True, db_path=str(db_path))
    cli.search_issues("parent", db_path=str(db_path))
    cli.search_issues("no-match", db_path=str(db_path))
    cli.search_issues("parent", branch_filter="feature-x", db_path=str(db_path))
    cli.search_issues("parent", worktree_filter="/repo.feature-x", db_path=str(db_path))
    cli.board_view(db_path=str(db_path))
    cli.board_view(as_json=True, db_path=str(db_path))
    cli.board_view(branch_filter="feature-x", db_path=str(db_path))
    cli.board_view(worktree_filter="/repo.feature-x", db_path=str(db_path))
    cli.lifecycle_action(parent_id, "begin", db_path=str(db_path))
    cli.lifecycle_action(parent_id, "pause", db_path=str(db_path))
    cli.lifecycle_action(parent_id, "begin", db_path=str(db_path))
    cli.lifecycle_action(parent_id, "review", db_path=str(db_path))
    cli.lifecycle_action(parent_id, "finish", db_path=str(db_path))
    cli.lifecycle_action(parent_id, "begin", db_path=str(db_path))
    cli.lifecycle_action(parent_id, "begin", force_reopen=True, db_path=str(db_path))
    cli.link_issue(parent_id, branch="feature-link", worktree="/repo.feature-link", db_path=str(db_path))
    cli.record_event("switch", task_id=parent_id, db_path=str(db_path))
    cli.record_event("remove", task_id=parent_id, db_path=str(db_path))
    cli.record_event("bad", task_id=parent_id, db_path=str(db_path))
    cli.record_event("switch", db_path=str(db_path))
    cli.show_issue(parent_id, db_path=str(db_path))
    cli.show_issue(parent_id, as_json=True, db_path=str(db_path))
    cli.show_issue(parent_id, repo_filter="/nope", db_path=str(db_path))
    cli.show_issue(parent_id, global_only=True, db_path=str(db_path))
    cli.show_issue("missing", db_path=str(db_path))
    cli.promote_issue("missing", db_path=str(db_path))
    cli.promote_issue(parent_id, db_path=str(db_path))
    cli.show_stats(db_path=str(db_path))
    cli.set_status("missing", "Done", db_path=str(db_path))
    cli.set_status(parent_id, "Done", db_path=str(db_path))
    cli.compact(db_path=str(db_path))
    cli.compact(db_path=str(db_path))
    cli.delete_issue("missing", db_path=str(db_path))
    cli.delete_issue(child_id, db_path=str(db_path))

    assert "No results found" in capsys.readouterr().out


def test_main_command_dispatch(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "main.sqlite"

    monkeypatch.setattr(cli.sys, "argv", ["sb"])
    cli.main()
    assert "Usage: sb" in capsys.readouterr().out

    for args, expected in [
        (["--help"], "Usage: sb"),
        (["version"], "sb-tracker"),
        (["init", "extra"], "Usage: sb init"),
        (["add"], "Usage: sb add"),
        (["search"], "Usage: sb search"),
        (["update"], "Usage: sb update"),
        (["begin"], "Usage: sb begin"),
        (["pause"], "Usage: sb pause"),
        (["review"], "Usage: sb review"),
        (["finish"], "Usage: sb finish"),
        (["event"], "Usage: sb event"),
        (["link"], "Usage: sb link"),
        (["promote"], "Usage: sb promote"),
        (["dep", "x"], "Usage: sb dep"),
        (["show"], "Usage: sb show"),
        (["done"], "Usage: sb done"),
        (["rm"], "Usage: sb rm"),
        (["unknown"], "Unknown command"),
    ]:
        out, _ = _run_main(monkeypatch, capsys, db_path, args)
        assert expected in out

    _run_main(monkeypatch, capsys, db_path, ["init"])
    out, _ = _run_main(monkeypatch, capsys, db_path, ["add", "--global", "task", "-p", "1", "--desc", "desc"])
    assert "Created" in out
    out, _ = _run_main(monkeypatch, capsys, db_path, ["list", "--all", "--json"])
    issue_id = json.loads(out)["issues"][0]["id"]

    _run_main(monkeypatch, capsys, db_path, ["update", issue_id, "title=renamed", "desc=zzz", "p=0", "status=Ready", "parent="])
    _run_main(monkeypatch, capsys, db_path, ["begin", issue_id])
    _run_main(monkeypatch, capsys, db_path, ["pause", issue_id])
    _run_main(monkeypatch, capsys, db_path, ["begin", issue_id])
    _run_main(monkeypatch, capsys, db_path, ["review", issue_id])
    _run_main(monkeypatch, capsys, db_path, ["finish", issue_id])
    _run_main(monkeypatch, capsys, db_path, ["begin", issue_id, "--force-reopen"])
    _run_main(monkeypatch, capsys, db_path, ["link", issue_id, "branch=feature-main", f"worktree={tmp_path}"])
    _run_main(monkeypatch, capsys, db_path, ["event", "switch", "--task", issue_id])
    _run_main(monkeypatch, capsys, db_path, ["ready", "--json"])
    _run_main(monkeypatch, capsys, db_path, ["search", "rename", "--branch", "feature-main"])
    _run_main(monkeypatch, capsys, db_path, ["board", "--json", "--branch", "feature-main"])
    _run_main(monkeypatch, capsys, db_path, ["show", issue_id, "--json"])
    _run_main(monkeypatch, capsys, db_path, ["stats"])
    _run_main(monkeypatch, capsys, db_path, ["done", issue_id])
    _run_main(monkeypatch, capsys, db_path, ["compact"])
    _run_main(monkeypatch, capsys, db_path, ["rm", issue_id])
    _run_main(monkeypatch, capsys, db_path, ["list", "--repo", "--json"])
    _run_main(monkeypatch, capsys, db_path, ["list", "--repo", str(tmp_path), "--json"])
    _run_main(monkeypatch, capsys, db_path, ["list", "--branch", "feature-main", "--json"])
    _run_main(monkeypatch, capsys, db_path, ["list", "--worktree", str(tmp_path), "--json"])
    _run_main(monkeypatch, capsys, db_path, ["search", "rename", "--worktree", str(tmp_path)])
    _run_main(monkeypatch, capsys, db_path, ["board", "--worktree", str(tmp_path)])


def test_additional_branches(tmp_path, monkeypatch, capsys):
    malformed_shape = cli._ensure_db_shape({"issues": "bad", "meta": {"kanban": {"columns": "bad", "backlog": 1, "done": 2}}})
    assert isinstance(malformed_shape["issues"], list)
    assert malformed_shape["meta"]["kanban"]["backlog"] == "Backlog"

    with pytest.raises(RuntimeError):
        existing = [{"id": "sb-dup"}]
        monkeypatch.setattr(cli, "_encode_base36", lambda *_a, **_k: "dup")
        cli._next_hash_id(existing, "t", "d", "x")

    monkeypatch.undo()
    legacyless_home = tmp_path / "home-no-legacy"
    legacyless_home.mkdir()
    monkeypatch.setenv("HOME", str(legacyless_home))
    cli._migrate_legacy_json_to_sqlite_if_needed(str(legacyless_home / ".sb.sqlite"))

    db_path = tmp_path / "branch.sqlite"
    monkeypatch.setenv("SB_DB_PATH", str(db_path))
    cli.init()
    cli.init()

    db = cli.load_db(str(db_path))
    db["compaction_log"] = [{"summary": "archived"}]
    db["issues"] = [_issue("sb-1", repo="/repo"), _issue("sb-2", status="Unknown")]
    db["issues"][0]["depends_on"] = ["a" * 20]
    db["issues"][0]["description"] = "hello"
    db["issues"][0]["repo_commit"] = "abc"
    db["issues"][0]["repo_branch"] = "feature/a"
    db["issues"][0]["worktree_path"] = "/repo.feature-a"
    db["issues"][0]["events"] = [{"type": "dep_added", "timestamp": "2026-01-01T12:00:00", "parent": "sb-x"}]
    cli.save_db(db, str(db_path))

    cli.search_issues("task", global_only=True, db_path=str(db_path))
    cli.search_issues("task", repo_filter="/repo", db_path=str(db_path))
    cli.search_issues("task", branch_filter="feature/a", db_path=str(db_path))
    cli.search_issues("task", worktree_filter="/repo.feature-a", db_path=str(db_path))
    cli.list_issues(as_json=True, db_path=str(db_path))
    cli.list_issues(show_all=True, db_path=str(db_path))
    cli.list_issues(show_all=True, global_only=True, db_path=str(db_path))
    cli.list_issues(show_all=True, repo_filter="/missing", db_path=str(db_path))
    cli.list_issues(show_all=True, branch_filter="feature/a", db_path=str(db_path))
    cli.list_issues(show_all=True, worktree_filter="/repo.feature-a", db_path=str(db_path))
    cli.board_view(global_only=True, db_path=str(db_path))
    cli.board_view(repo_filter="/repo", db_path=str(db_path))
    cli.board_view(branch_filter="feature/a", db_path=str(db_path))
    cli.board_view(worktree_filter="/repo.feature-a", db_path=str(db_path))
    cli.board_view(db_path=str(db_path))
    cli.show_stats(db_path=str(db_path))
    cli.show_issue("sb-1", db_path=str(db_path))
    cli.show_issue("sb-1", global_only=True, db_path=str(db_path))
    cli.set_status("sb-1", "Backlog", db_path=str(db_path))
    cli.add("orphan", parent_id="missing-parent", db_path=str(db_path))
    cli.record_event("switch", repo="/repo", branch="feature/a", db_path=str(db_path))
    cli.record_event("switch", repo="/repo", branch="feature/missing", db_path=str(db_path))
    db = cli.load_db(str(db_path))
    db["issues"].append(
        {
            "id": "sb-amb",
            "title": "ambiguous",
            "description": "",
            "priority": 2,
            "status": "Backlog",
            "depends_on": [],
            "events": [],
            "created_at": "2026-01-01T00:00:00",
            "repo": "/repo",
            "repo_branch": "feature/a",
        }
    )
    cli.save_db(db, str(db_path))
    cli.record_event("switch", repo="/repo", branch="feature/a", db_path=str(db_path))

    out = capsys.readouterr().out
    assert "already exists" in out
    assert "Compaction Log" in out
    assert "Unmapped" in out
    assert "Repo Commit" in out
    assert "Repo Branch" in out
    assert "Worktree" in out
    assert "No changes: no matching open task" in out
    assert "No changes: multiple open tasks match repo+branch" in out
    assert "Parent issue missing-parent not found" in out

    monkeypatch.setattr(
        cli,
        "_ensure_sqlite_storage",
        lambda *_a, **_k: (_ for _ in ()).throw(sqlite3.Error("boom")),
    )
    with pytest.raises(SystemExit):
        cli._save_db_to_sqlite(cli._default_db_state(), str(tmp_path / "sqlite-fail.sqlite"))

    import builtins

    monkeypatch.setattr(
        builtins,
        "open",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("open fail")),
    )
    existing_json = tmp_path / "existing.json"
    existing_json.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        cli._load_db_from_json(str(existing_json))

    monkeypatch.undo()
    monkeypatch.setattr(cli.os, "replace", lambda *_a, **_k: (_ for _ in ()).throw(OSError("replace fail")))
    monkeypatch.setattr(cli.os, "unlink", lambda *_a, **_k: (_ for _ in ()).throw(OSError("unlink fail")))
    with pytest.raises(SystemExit):
        cli._save_db_to_json(cli._default_db_state(), str(tmp_path / "json-fail.json"))

    non_git_path = tmp_path / "not-repo"
    non_git_path.mkdir()
    out, _ = _run_main(
        monkeypatch,
        capsys,
        tmp_path / "main2.sqlite",
        ["add", "--repo", str(non_git_path), "task", "--parent", "parent-x"],
    )
    assert "Created" in out or "Parent issue" in out


def test_add_dependency_scope_validation(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "db.sqlite")
    monkeypatch.setenv("SB_DB_PATH", db_path)
    cli.init()

    cli.add("global-a", "", 2, db_path=db_path)
    cli.add("global-b", "", 2, db_path=db_path)
    cli.add("repo-a", "", 2, repo="/myrepo", db_path=db_path)
    cli.add("repo-b", "", 2, repo="/myrepo", db_path=db_path)

    db = cli.load_db(db_path)
    gid_a = next(i["id"] for i in db["issues"] if i["title"] == "global-a")
    gid_b = next(i["id"] for i in db["issues"] if i["title"] == "global-b")
    rid_a = next(i["id"] for i in db["issues"] if i["title"] == "repo-a")
    rid_b = next(i["id"] for i in db["issues"] if i["title"] == "repo-b")

    def get_deps(issue_id):
        return next(i for i in cli.load_db(db_path)["issues"] if i["id"] == issue_id)["depends_on"]

    # --global rejects issues that have a repo
    cli.add_dependency(rid_a, gid_a, db_path=db_path, global_only=True)
    out = capsys.readouterr().out
    assert "not a global" in out
    assert gid_a not in get_deps(rid_a)  # dep was not saved

    cli.add_dependency(gid_a, rid_a, db_path=db_path, global_only=True)
    out = capsys.readouterr().out
    assert "not a global" in out
    assert rid_a not in get_deps(gid_a)  # dep was not saved

    # --global succeeds for two global issues
    cli.add_dependency(gid_b, gid_a, db_path=db_path, global_only=True)
    out = capsys.readouterr().out
    assert "Linked" in out

    # --repo rejects issues not in that repo
    cli.add_dependency(gid_a, gid_b, db_path=db_path, repo_filter="/myrepo")
    out = capsys.readouterr().out
    assert "does not belong to repo" in out
    assert gid_b not in get_deps(gid_a)  # dep was not saved

    cli.add_dependency(rid_a, gid_b, db_path=db_path, repo_filter="/myrepo")
    out = capsys.readouterr().out
    assert "does not belong to repo" in out
    assert gid_b not in get_deps(rid_a)  # dep was not saved

    # --repo succeeds for two issues in the same repo
    cli.add_dependency(rid_b, rid_a, db_path=db_path, repo_filter="/myrepo")
    out = capsys.readouterr().out
    assert "Linked" in out
    assert rid_a in get_deps(rid_b)  # dep was saved


def test_needs_review_lifecycle(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "db.sqlite")
    monkeypatch.setenv("SB_DB_PATH", db_path)
    cli.init()
    capsys.readouterr()

    # Task with needs_review=True
    cli.add("guarded", "", 1, needs_review=True, db_path=db_path)
    issue_id = cli.load_db(db_path)["issues"][0]["id"]

    # Move to Doing
    cli.lifecycle_action(issue_id, "begin", db_path=db_path)
    capsys.readouterr()

    # finish from Doing → should stop at Review, not Done
    cli.lifecycle_action(issue_id, "finish", db_path=db_path)
    out = capsys.readouterr().out
    status = cli.load_db(db_path)["issues"][0]["status"]
    assert status == "Review"
    assert "sign-off" in out or "Review" in out

    # finish from Review → should close (Done)
    cli.lifecycle_action(issue_id, "finish", db_path=db_path)
    capsys.readouterr()
    status = cli.load_db(db_path)["issues"][0]["status"]
    assert status == "Done"

    # Task without needs_review — finish from Doing goes directly to Done
    cli.add("free", "", 1, needs_review=False, db_path=db_path)
    free_id = next(i["id"] for i in cli.load_db(db_path)["issues"] if i["title"] == "free")
    cli.lifecycle_action(free_id, "begin", db_path=db_path)
    capsys.readouterr()
    cli.lifecycle_action(free_id, "finish", db_path=db_path)
    capsys.readouterr()
    free_status = next(i["status"] for i in cli.load_db(db_path)["issues"] if i["id"] == free_id)
    assert free_status == "Done"

    # sb done bypasses needs_review flag
    cli.add("force-close", "", 1, needs_review=True, db_path=db_path)
    fc_id = next(i["id"] for i in cli.load_db(db_path)["issues"] if i["title"] == "force-close")
    cli.lifecycle_action(fc_id, "begin", db_path=db_path)
    cli.set_status(fc_id, None, db_path=db_path)  # done bypasses flag
    capsys.readouterr()
    fc_status = next(i["status"] for i in cli.load_db(db_path)["issues"] if i["id"] == fc_id)
    assert fc_status == "Done"

    # update_issue can toggle needs_review
    cli.add("toggleable", "", 1, db_path=db_path)
    tg_id = next(i["id"] for i in cli.load_db(db_path)["issues"] if i["title"] == "toggleable")
    tg = next(i for i in cli.load_db(db_path)["issues"] if i["id"] == tg_id)
    assert not tg.get("needs_review")  # default off
    cli.update_issue(tg_id, needs_review=True, db_path=db_path)
    capsys.readouterr()
    tg = next(i for i in cli.load_db(db_path)["issues"] if i["id"] == tg_id)
    assert tg.get("needs_review") is True
    cli.update_issue(tg_id, needs_review=False, db_path=db_path)
    capsys.readouterr()
    tg = next(i for i in cli.load_db(db_path)["issues"] if i["id"] == tg_id)
    assert not tg.get("needs_review")


def test_prefix_config_and_custom_id(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "db.sqlite")
    monkeypatch.setenv("SB_DB_PATH", db_path)
    cli.init()
    capsys.readouterr()

    # Default prefix is "sb"
    cli.add("default task", db_path=db_path)
    db = cli.load_db(db_path)
    assert db["issues"][0]["id"].startswith("sb-")

    # Set global prefix
    db["meta"]["id_prefix"] = "BNC"
    cli.save_db(db, db_path=db_path)

    cli.add("bnc task", db_path=db_path)
    db = cli.load_db(db_path)
    bnc_task = next(i for i in db["issues"] if i["title"] == "bnc task")
    assert bnc_task["id"].startswith("BNC-")

    # Set repo-specific prefix (overrides global)
    db["meta"]["prefix_by_repo"]["/myrepo"] = "SB"
    cli.save_db(db, db_path=db_path)

    cli.add("sb task", db_path=db_path, repo="/myrepo")
    db = cli.load_db(db_path)
    sb_task = next(i for i in db["issues"] if i["title"] == "sb task")
    assert sb_task["id"].startswith("SB-")

    # _resolve_prefix: repo with no config falls back to global
    prefix = cli._resolve_prefix(db, repo="/unknown-repo")
    assert prefix == "BNC"

    # custom_id creates task with literal external ID
    cli.add("jira mirror", custom_id="B1XF-3213", db_path=db_path)
    capsys.readouterr()
    db = cli.load_db(db_path)
    jira = next(i for i in db["issues"] if i["id"] == "B1XF-3213")
    assert jira["title"] == "jira mirror"

    # duplicate custom_id is rejected
    cli.add("duplicate", custom_id="B1XF-3213", db_path=db_path)
    out = capsys.readouterr().out
    assert "already exists" in out
    assert len([i for i in cli.load_db(db_path)["issues"] if i["id"] == "B1XF-3213"]) == 1


def test_config_command(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "db.sqlite"

    # Set global prefix via CLI
    out, _ = _run_main(monkeypatch, capsys, db_path, ["init"])
    out, _ = _run_main(monkeypatch, capsys, db_path, ["config", "prefix", "BNC-", "--global"])
    assert "BNC" in out

    # Get prefix shows global
    out, _ = _run_main(monkeypatch, capsys, db_path, ["config", "get", "prefix"])
    assert "BNC" in out

    # Set repo prefix (no git repo here, so it errors gracefully)
    out, _ = _run_main(monkeypatch, capsys, db_path, ["config", "prefix", "SB"])
    # Either sets it (if git detected) or prints an error — both are valid

    # Unknown config subcommand shows usage
    out, _ = _run_main(monkeypatch, capsys, db_path, ["config", "unknown", "arg"])
    assert "Usage" in out

    # Missing args shows usage
    out, _ = _run_main(monkeypatch, capsys, db_path, ["config"])
    assert "Usage" in out

    # Add with --id flag via CLI
    out, _ = _run_main(monkeypatch, capsys, db_path, ["add", "--global", "jira task", "--id", "PROJ-999"])
    assert "PROJ-999" in out

    # Duplicate --id rejected
    out, _ = _run_main(monkeypatch, capsys, db_path, ["add", "--global", "dup", "--id", "PROJ-999"])
    assert "already exists" in out
