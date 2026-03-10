import pytest
import os
from sb_tracker import cli

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite"
    os.environ["SB_DB_PATH"] = str(path)
    cli.init()
    return str(path)

def test_compact_tasks(db_path, capsys):
    # Add a task and close it
    cli.add("Old Task", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    cli.set_status(task_id, "Done", db_path=db_path)
    
    # Backdate it by 100 days
    from datetime import datetime, timedelta
    db = cli.load_db(db_path=db_path)
    task = db["issues"][0]
    task["closed_at"] = (datetime.now() - timedelta(days=100)).isoformat()
    cli.save_db(db, db_path=db_path)
    
    cli.compact(db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Successfully removed 1 done issues" in out
    
    db = cli.load_db(db_path=db_path)
    assert len(db["issues"]) == 0

def test_compact_no_tasks(db_path, capsys):
    # Fresh DB has no compactable tasks
    cli.compact(db_path=db_path)
    out, _ = capsys.readouterr()
    assert "No done issues older than" in out

def test_delete_issue(db_path, capsys):
    cli.add("To Delete", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    capsys.readouterr() # Clear buffer
    
    cli.delete_issue(task_id, db_path=db_path)
    out, _ = capsys.readouterr()
    assert f"Deleted {task_id}" in out
    
    db = cli.load_db(db_path=db_path)
    assert len(db["issues"]) == 0

def test_delete_issue_not_found(db_path, capsys):
    cli.delete_issue("missing", db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Error: Issue missing not found" in out
