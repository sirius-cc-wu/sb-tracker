import pytest
import subprocess
from sb_tracker import cli

@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite"
    monkeypatch.setenv("SB_DB_PATH", str(path))
    cli.init()
    return str(path)

def test_verify_success(db_path, capsys):
    cli.add("Task 1", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    # Run verify with a successful command
    cli.run_verification(task_id, "echo 'hello world'", db_path=db_path)
    out, _ = capsys.readouterr()
    
    assert "Verification SUCCESS" in out
    
    db = cli.load_db(db_path=db_path)
    task = db["issues"][0]
    # Default behavior for success is Done
    assert task["status"] == "Done"
    
    # Check audit log
    events = [e for e in task["events"] if e["type"] == "verification_result"]
    assert len(events) == 1
    assert events[0]["exit_code"] == 0
    assert "hello world" in events[0]["output"]

def test_verify_failure(db_path, capsys):
    cli.add("Task 2", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    # Run verify with a failing command
    cli.run_verification(task_id, "exit 1", db_path=db_path)
    out, _ = capsys.readouterr()
    
    assert "Verification FAILED" in out
    
    db = cli.load_db(db_path=db_path)
    task = db["issues"][0]
    # Should NOT be Done
    assert task["status"] != "Done"
    
    # Check audit log
    events = [e for e in task["events"] if e["type"] == "verification_result"]
    assert len(events) == 1
    assert events[0]["exit_code"] != 0

def test_verify_with_needs_review(db_path, capsys):
    cli.add("Task 3", needs_review=True, db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    # Run verify with success
    cli.run_verification(task_id, "echo 'ready'", db_path=db_path)
    
    db = cli.load_db(db_path=db_path)
    task = db["issues"][0]
    # Should be Review, not Done
    assert task["status"] == "Review"
