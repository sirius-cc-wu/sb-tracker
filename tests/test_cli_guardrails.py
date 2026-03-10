import pytest
import os
import json
from sb_tracker import cli

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite"
    os.environ["SB_DB_PATH"] = str(path)
    cli.init()
    return str(path)

def test_finish_blocked_by_guardrail(db_path, tmp_path, monkeypatch):
    # Setup repo root and config
    repo = tmp_path / "repo"
    repo.mkdir()
    config_dir = repo / ".sb"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps({
        "completion": {
            "require_verification": True
        }
    }))
    
    monkeypatch.chdir(repo)
    monkeypatch.setattr(cli, "get_repo_root", lambda: str(repo))
    
    cli.add("Task X", repo=str(repo), db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    # Try to finish without verification
    import sys
    from io import StringIO
    out = StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    
    cli.lifecycle_action(task_id, "finish", db_path=db_path)
    
    assert "cannot be finished without a successful verification" in out.getvalue()
    
    db = cli.load_db(db_path=db_path)
    assert db["issues"][0]["status"] != "Done"

def test_finish_allowed_after_verify(db_path, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    config_dir = repo / ".sb"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(json.dumps({
        "completion": { "require_verification": True }
    }))
    
    monkeypatch.chdir(repo)
    monkeypatch.setattr(cli, "get_repo_root", lambda: str(repo))
    
    cli.add("Task Y", repo=str(repo), db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    # Verify first
    cli.run_verification(task_id, "echo ok", db_path=db_path)
    
    # Now finish should work (actually run_verification auto-advances, but let's test manual finish too)
    # If run_verification auto-advances, it might bypass the check or satisfy it.
    # In my implementation, run_verification calls _apply_status_change directly. 
    # I should ensure _apply_status_change or lifecycle_action respects the guardrail.
    
    # Actually, lifecycle_action "finish" is what we want to guard.
    cli.update_issue(task_id, status="Doing", db_path=db_path) # reset to Doing
    
    cli.lifecycle_action(task_id, "finish", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    assert db["issues"][0]["status"] == "Done"

def test_close_overrides_guardrail(db_path, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    config_dir = repo / ".sb"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(json.dumps({
        "completion": { "require_verification": True }
    }))
    
    monkeypatch.chdir(repo)
    monkeypatch.setattr(cli, "get_repo_root", lambda: str(repo))
    
    cli.add("Task Z", repo=str(repo), db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    # sb close should work even without verification
    cli.set_status(task_id, None, db_path=db_path)
    db = cli.load_db(db_path=db_path)
    assert db["issues"][0]["status"] == "Done"

def test_load_config_invalid_json(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    config_dir = repo / ".sb"
    config_dir.mkdir()
    (config_dir / "config.json").write_text("invalid json")
    
    monkeypatch.chdir(repo)
    monkeypatch.setattr(cli, "get_repo_root", lambda: str(repo))
    
    import sys
    config = cli.load_project_config()
    assert config == {}
    _, err = capsys.readouterr()
    assert "Warning: Failed to load .sb/config.json" in err
