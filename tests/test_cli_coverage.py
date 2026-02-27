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

    cli.add_dependency("missing", parent_id, db_path=str(db_path))
    cli.add_dependency(blocked_id, "missing", db_path=str(db_path))
    cli.add_dependency(blocked_id, parent_id, db_path=str(db_path))
    cli.add_dependency(blocked_id, parent_id, db_path=str(db_path))

    cli.update_issue("missing", title="x", db_path=str(db_path))
    cli.update_issue(parent_id, status="bad-status", db_path=str(db_path))
    cli.update_issue(parent_id, db_path=str(db_path))
    cli.update_issue(parent_id, title="parent2", description="d2", priority=0, status="Doing", parent_id="", db_path=str(db_path))

    cli.list_issues(db_path=str(db_path))
    cli.list_issues(show_all=True, as_json=True, db_path=str(db_path))
    cli.list_issues(ready_only=True, db_path=str(db_path))
    cli.list_issues(repo_filter="/nope", db_path=str(db_path))
    cli.list_issues(global_only=True, db_path=str(db_path))
    cli.search_issues("parent", db_path=str(db_path))
    cli.search_issues("no-match", db_path=str(db_path))
    cli.board_view(db_path=str(db_path))
    cli.board_view(as_json=True, db_path=str(db_path))
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
        (["status", "only-id"], "Usage: sb status"),
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
    out, _ = _run_main(monkeypatch, capsys, db_path, ["add", "--global", "task", "1", "desc"])
    assert "Created" in out
    out, _ = _run_main(monkeypatch, capsys, db_path, ["list", "--all", "--json"])
    issue_id = json.loads(out)["issues"][0]["id"]

    _run_main(monkeypatch, capsys, db_path, ["update", issue_id, "title=renamed", "desc=zzz", "p=0", "status=Ready", "parent="])
    _run_main(monkeypatch, capsys, db_path, ["status", issue_id, "Doing"])
    _run_main(monkeypatch, capsys, db_path, ["ready", "--json"])
    _run_main(monkeypatch, capsys, db_path, ["search", "rename"])
    _run_main(monkeypatch, capsys, db_path, ["board", "--json"])
    _run_main(monkeypatch, capsys, db_path, ["show", issue_id, "--json"])
    _run_main(monkeypatch, capsys, db_path, ["stats"])
    _run_main(monkeypatch, capsys, db_path, ["done", issue_id])
    _run_main(monkeypatch, capsys, db_path, ["compact"])
    _run_main(monkeypatch, capsys, db_path, ["rm", issue_id])
    _run_main(monkeypatch, capsys, db_path, ["list", "--repo", "--json"])
    _run_main(monkeypatch, capsys, db_path, ["list", "--repo", str(tmp_path), "--json"])


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
    db["issues"][0]["events"] = [{"type": "dep_added", "timestamp": "2026-01-01T12:00:00", "parent": "sb-x"}]
    cli.save_db(db, str(db_path))

    cli.search_issues("task", global_only=True, db_path=str(db_path))
    cli.search_issues("task", repo_filter="/repo", db_path=str(db_path))
    cli.list_issues(as_json=True, db_path=str(db_path))
    cli.list_issues(show_all=True, db_path=str(db_path))
    cli.list_issues(show_all=True, global_only=True, db_path=str(db_path))
    cli.list_issues(show_all=True, repo_filter="/missing", db_path=str(db_path))
    cli.board_view(global_only=True, db_path=str(db_path))
    cli.board_view(repo_filter="/repo", db_path=str(db_path))
    cli.board_view(db_path=str(db_path))
    cli.show_stats(db_path=str(db_path))
    cli.show_issue("sb-1", db_path=str(db_path))
    cli.show_issue("sb-1", global_only=True, db_path=str(db_path))
    cli.set_status("sb-1", "Backlog", db_path=str(db_path))
    cli.add("orphan", parent_id="missing-parent", db_path=str(db_path))

    out = capsys.readouterr().out
    assert "already exists" in out
    assert "Compaction Log" in out
    assert "Unmapped" in out
    assert "Repo Commit" in out
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
        ["add", "--repo", str(non_git_path), "task", "oops", "desc", "parent-x"],
    )
    assert "Created" in out or "Parent issue" in out
