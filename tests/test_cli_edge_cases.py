import pytest
import os
import sqlite3
from sb_tracker import cli

def test_resolve_db_path_env(monkeypatch):
    monkeypatch.setenv("SB_DB_PATH", "/tmp/env.sqlite")
    assert cli.resolve_db_path() == "/tmp/env.sqlite"

def test_resolve_repo_filter_global(monkeypatch):
    opts = {"global_only": True, "repo_current": False, "repo": None}
    assert cli.resolve_repo_filter(opts) is None

def test_resolve_repo_filter_current(monkeypatch):
    repo = "/tmp/repo"
    monkeypatch.setattr(cli, "get_repo_root", lambda **kwargs: repo)
    opts = {"global_only": False, "repo_current": True, "repo": None}
    assert cli.resolve_repo_filter(opts) == repo

def test_resolve_repo_filter_explicit(tmp_path):
    repo = tmp_path / "explicit"
    repo.mkdir()
    (repo / ".git").mkdir()
    opts = {"global_only": False, "repo_current": False, "repo": str(repo)}
    # resolve_repo_filter calls get_repo_root on the path
    assert cli.resolve_repo_filter(opts) == str(repo)

def test_apply_status_change_noop(capsys):
    issue = {"status": "Doing"}
    config = {"columns": ["Backlog", "Doing", "Done"], "backlog": "Backlog", "done": "Done"}
    assert cli._apply_status_change(issue, "Doing", config) is False

def test_apply_status_change_invalid(capsys):
    issue = {"status": "Doing"}
    config = {"columns": ["Backlog", "Doing", "Done"], "backlog": "Backlog", "done": "Done"}
    assert cli._apply_status_change(issue, "Invalid", config) is False
    out, _ = capsys.readouterr()
    assert "Invalid status" in out

def test_get_kanban_config_default():
    db = {"meta": {}}
    cfg = cli.get_kanban_config(db)
    assert cfg["backlog"] == "Backlog"
    assert "Done" in cfg["columns"]

def test_get_kanban_config_with_repo():
    db = {"meta": {}}
    cfg = cli.get_kanban_config(db, repo_root="/some/repo")
    assert cfg["backlog"] == "Backlog"

def test_ensure_db_shape_malformed():
    db = {"issues": "not a list"}
    shaped = cli._ensure_db_shape(db)
    assert isinstance(shaped["issues"], list)
    assert "kanban" in shaped["meta"]

def test_is_ready_blocked():
    issues = [
        {"id": "sb-1", "status": "Backlog"},
        {"id": "sb-2", "status": "Backlog", "depends_on": ["sb-1"]}
    ]
    db = {"meta": {"kanban": {"columns": ["Backlog", "Done"], "backlog": "Backlog", "done": "Done"}}, "issues": issues}
    assert cli.is_ready(issues[1], issues, db) is False
    
    issues[0]["status"] = "Done"
    assert cli.is_ready(issues[1], issues, db) is True
