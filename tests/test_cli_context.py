import pytest

from sb_tracker import cli

@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite"
    monkeypatch.setenv("SB_DB_PATH", str(path))
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
