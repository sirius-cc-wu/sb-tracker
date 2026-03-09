import pytest
import os
import sqlite3
from sb_tracker import cli

@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.sqlite"

@pytest.fixture
def plan_file(tmp_path):
    path = tmp_path / "plan.md"
    path.write_text("""
- [ ] Task A
  - [ ] Task A.1
- [x] Task B
""")
    return path

def _run_import(db_path, args, capsys):
    # Helper to run import command
    # Assuming cli.main() parses sys.argv
    import sys
    original_argv = sys.argv
    sys.argv = ["sb", "import"] + args
    try:
        cli.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
    return capsys.readouterr()

def test_import_dry_run(db_path, plan_file, capsys):
    # Initialize DB first
    cli.init() # This uses default path, we need to override
    # Actually, let's just use the cli functions directly or mock load_db
    # But cli.main uses sys.argv. Let's try to invoke cli.import_tasks directly if possible,
    # or mock the db path in cli.
    
    # Better: set SB_DB_PATH env var
    # os.environ["SB_DB_PATH"] = str(db_path)
    # cli.init() # Initialize the test DB
    
    # out, err = _run_import(db_path, [str(plan_file), "--dry-run"], capsys)
    # assert "Task A" in out
    
    # Actually, we should use monkeypatch fixture
    pass

def test_import_dry_run_fixed(db_path, plan_file, capsys, monkeypatch):
    monkeypatch.setenv("SB_DB_PATH", str(db_path))
    cli.init() 
    
    out, err = _run_import(db_path, [str(plan_file), "--dry-run"], capsys)
    assert "Task A" in out
    assert "Task A.1" in out
    assert "Task B" in out
    assert "(dry run)" in out
    
    # Verify no tasks added to DB
    db = cli.load_db(str(db_path))
    assert len(db["issues"]) == 0

def test_import_execution(db_path, plan_file, capsys, monkeypatch):
    monkeypatch.setenv("SB_DB_PATH", str(db_path))
    cli.init()
    
    out, err = _run_import(db_path, [str(plan_file)], capsys)
    assert "Imported 3 tasks" in out
    
    db = cli.load_db(str(db_path))
    assert len(db["issues"]) == 3
    
    task_a = next(t for t in db["issues"] if t["title"] == "Task A")
    task_a1 = next(t for t in db["issues"] if t["title"] == "Task A.1")
    task_b = next(t for t in db["issues"] if t["title"] == "Task B")
    
    assert task_a1["parent"] == task_a["id"]
    # Task B might be done or closed depending on config, default is Done
    # cli.add logic handles created_at etc, import_tasks does it manually
    assert task_b["status"] == "Done"
    
    # Check that task_a is NOT done
    assert task_a["status"] != "Done"

def test_import_with_parent(db_path, plan_file, capsys, monkeypatch):
    monkeypatch.setenv("SB_DB_PATH", str(db_path))
    cli.init()
    
    # Create a parent task first
    cli.add("Root Task", db_path=str(db_path))
    db = cli.load_db(str(db_path))
    root_id = db["issues"][0]["id"]
    
    out, err = _run_import(db_path, [str(plan_file), "--parent", root_id], capsys)
    
    db = cli.load_db(str(db_path))
    # 1 root + 3 imported
    assert len(db["issues"]) == 4
    
    task_a = next(t for t in db["issues"] if t["title"] == "Task A")
    assert task_a["parent"] == root_id

def test_import_idempotency(db_path, plan_file, capsys, monkeypatch):
    monkeypatch.setenv("SB_DB_PATH", str(db_path))
    cli.init()
    
    # Run twice
    _run_import(db_path, [str(plan_file)], capsys)
    out, err = _run_import(db_path, [str(plan_file)], capsys)
    
    assert "Skipped 3 tasks" in out
    db = cli.load_db(str(db_path))
    assert len(db["issues"]) == 3
