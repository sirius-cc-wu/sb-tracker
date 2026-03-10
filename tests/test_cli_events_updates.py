import pytest
import os
from sb_tracker import cli

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite"
    os.environ["SB_DB_PATH"] = str(path)
    cli.init()
    return str(path)

def test_update_issue(db_path, capsys):
    cli.add("Original", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    cli.update_issue(task_id, title="Updated", priority=0, db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task = db["issues"][0]
    assert task["title"] == "Updated"
    assert task["priority"] == 0

def test_update_issue_invalid_parent(db_path, capsys):
    cli.add("Task", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    capsys.readouterr() # Clear buffer
    
    cli.update_issue(task_id, parent_id="missing", db_path=db_path)
    out, _ = capsys.readouterr()
    # update_issue doesn't check parent currently, so it should say "Updated"
    assert "Updated" in out

def test_update_issue_no_changes(db_path, capsys):
    cli.add("No Change", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    capsys.readouterr()
    cli.update_issue(task_id, db_path=db_path)
    out, _ = capsys.readouterr()
    assert "No changes specified" in out

def test_add_invalid_parent(db_path, capsys):
    cli.add("Task with bad parent", parent_id="missing", db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Error: Parent issue missing not found" in out

def test_event_ingestion(db_path, capsys, monkeypatch):
    repo = "/mock/repo"
    cli.add("Event Task", repo=repo, db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    # Mock branch resolution
    monkeypatch.setattr(cli, "get_repo_root", lambda **kwargs: repo)
    monkeypatch.setattr(cli, "get_repo_branch", lambda **kwargs: "feat/test")
    
    # Link task to branch
    cli.link_issue(task_id, branch="feat/test", db_path=db_path)
    
    # Ingest switch event (should move to Doing)
    cli.record_event("switch", repo=repo, branch="feat/test", db_path=db_path)
    
    db = cli.load_db(db_path=db_path)
    task = next(i for i in db["issues"] if i["id"] == task_id)
    assert task["status"] == "Doing"
