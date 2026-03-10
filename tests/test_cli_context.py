import pytest
import os
from sb_tracker import cli

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite"
    os.environ["SB_DB_PATH"] = str(path)
    cli.init()
    return str(path)

def test_context_aggregation(db_path, capsys):
    # Setup: Task with description and priority
    cli.add("Root Task", description="This is a spec.", priority=1, db_path=db_path)
    db = cli.load_db(db_path=db_path)
    root_id = db["issues"][0]["id"]
    
    # Sub-task
    cli.add("Child Task", parent_id=root_id, db_path=db_path)
    
    # Linked file (assuming we enhance sb link)
    cli.link_issue(root_id, branch="main", db_path=db_path)
    
    # Failed verification
    cli.run_verification(root_id, "exit 1", db_path=db_path)
    
    # Clear buffer from previous commands
    capsys.readouterr()
    
    # Capture context
    cli.show_context(root_id, db_path=db_path)
    out, _ = capsys.readouterr()
    
    assert f"Task Context: {root_id}" in out
    assert "Title: Root Task" in out
    assert "This is a spec." in out
    assert "Status: Doing" in out
    assert "Priority: P1" in out
    assert "Branch: main" in out
    assert "FAILED (Exit 1)" in out
    assert "Sub-tasks" in out
    assert "Child Task" in out

def test_context_with_files(db_path, tmp_path, capsys):
    # Setup: Create a dummy file
    test_file = tmp_path / "main.py"
    test_file.write_text("print('hello')")
    
    cli.add("File Task", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    # Link the file
    cli.link_issue(task_id, worktree=str(tmp_path), files=[str(test_file)], db_path=db_path)
    
    # Clear buffer
    capsys.readouterr()
    
    # Capture context with files
    cli.show_context(task_id, include_files=True, db_path=db_path)
    out, _ = capsys.readouterr()
    
    assert "Linked Files" in out
    assert str(test_file) in out
    assert "print('hello')" in out

def test_context_file_missing(db_path, capsys):
    cli.add("Missing File Task", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    # Link a non-existent file
    db = cli.load_db(db_path=db_path)
    task = next(i for i in db["issues"] if i["id"] == task_id)
    task["linked_files"] = ["/tmp/does_not_exist_12345.txt"]
    cli.save_db(db, db_path=db_path)
    
    capsys.readouterr()
    cli.show_context(task_id, include_files=True, db_path=db_path)
    out, _ = capsys.readouterr()
    assert "(File not found)" in out

def test_context_file_unreadable(db_path, tmp_path, capsys):
    unreadable = tmp_path / "secret.txt"
    unreadable.write_text("shhh")
    os.chmod(str(unreadable), 0) # No permissions
    
    cli.add("Secret Task", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    db = cli.load_db(db_path=db_path)
    task = next(i for i in db["issues"] if i["id"] == task_id)
    task["linked_files"] = [str(unreadable)]
    cli.save_db(db, db_path=db_path)
    
    capsys.readouterr()
    cli.show_context(task_id, include_files=True, db_path=db_path)
    out, _ = capsys.readouterr()
    assert "(Error reading file:" in out
    
    os.chmod(str(unreadable), 0o644) # restore for cleanup

def test_context_no_events(db_path, capsys):
    cli.add("No Event Task", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    cli.show_context(task_id, db_path=db_path)
    out, _ = capsys.readouterr()
    assert "--- Last Verification ---" not in out

def test_context_no_description(db_path, capsys):
    cli.add("No Desc Task", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    capsys.readouterr()
    cli.show_context(task_id, db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Description:" not in out

def test_context_deep_nested(db_path, capsys):
    cli.add("Root", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    rid = db["issues"][0]["id"]
    cli.add("Child", parent_id=rid, db_path=db_path)
    db = cli.load_db(db_path=db_path)
    cid = next(i["id"] for i in db["issues"] if i["title"] == "Child")
    cli.add("Grandchild", parent_id=cid, db_path=db_path)
    
    capsys.readouterr()
    cli.show_context(rid, db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Child" in out
    
    cli.show_context(cid, db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Grandchild" in out

def test_context_issue_not_found(db_path, capsys):
    cli.show_context("missing", db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Error: Issue missing not found" in out

def test_context_file_truncation(db_path, tmp_path, capsys):
    large_file = tmp_path / "large.txt"
    large_file.write_text("A" * 5000)
    
    cli.add("Large File Task", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    db = cli.load_db(db_path=db_path)
    task = next(i for i in db["issues"] if i["id"] == task_id)
    task["linked_files"] = [str(large_file)]
    cli.save_db(db, db_path=db_path)
    
    capsys.readouterr()
    cli.show_context(task_id, include_files=True, db_path=db_path)
    out, _ = capsys.readouterr()
    assert "A" * 4000 in out
    assert len(out) < 6000 # Should be truncated
