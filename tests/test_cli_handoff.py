import pytest
import os
import subprocess
from sb_tracker import cli

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite"
    os.environ["SB_DB_PATH"] = str(path)
    cli.init()
    return str(path)

def test_handoff_report_basic(db_path, capsys, monkeypatch):
    # Setup: Repo and some tasks
    repo = "/mock/repo"
    monkeypatch.setattr(cli, "get_repo_root", lambda: repo)
    monkeypatch.setattr(cli, "_run_git", lambda args, cwd=None: "M file.py" if "status" in args else "mock-output")
    
    cli.add("Task 1", repo=repo, db_path=db_path)
    cli.add("Task 2", repo=repo, db_path=db_path)
    db = cli.load_db(db_path=db_path)
    tid1 = db["issues"][0]["id"]
    cli.set_status(tid1, "Doing", db_path=db_path)
    
    capsys.readouterr()
    cli.generate_handoff_report(db_path=db_path)
    out, _ = capsys.readouterr()
    
    assert "# AGENT HANDOFF REPORT" in out
    assert "**Progress:** 0/2" in out
    assert "Active Task: Task 1" in out
    assert "Pending Git Changes" in out
    assert "M file.py" in out
    assert "Ready Queue" in out

def test_handoff_no_active_task(db_path, capsys, monkeypatch):
    repo = "/mock/repo"
    monkeypatch.setattr(cli, "get_repo_root", lambda: repo)
    
    cli.add("Task 1", repo=repo, db_path=db_path)
    
    capsys.readouterr()
    cli.generate_handoff_report(db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Active Task: None" in out
