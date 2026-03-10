import pytest
import os
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

def test_import_tasks_dry_run(db_path, plan_file, capsys, monkeypatch):
    monkeypatch.setenv("SB_DB_PATH", str(db_path))
    cli.init()
    
    cli.import_tasks(str(plan_file), dry_run=True, db_path=str(db_path))
    out, _ = capsys.readouterr()
    
    assert "(dry run)" in out
    assert "[ ] Task A" in out
    assert "  [ ] Task A.1" in out
    assert "[x] Task B" in out
    
    db = cli.load_db(str(db_path))
    assert len(db["issues"]) == 0

def test_import_tasks_execution(db_path, plan_file, capsys, monkeypatch):
    monkeypatch.setenv("SB_DB_PATH", str(db_path))
    cli.init()
    
    cli.import_tasks(str(plan_file), db_path=str(db_path))
    out, _ = capsys.readouterr()
    
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
    assert task_b.get("closed_at") is not None

def test_import_tasks_with_parent(db_path, plan_file, monkeypatch):
    monkeypatch.setenv("SB_DB_PATH", str(db_path))
    cli.init()
    
    cli.add("Root", db_path=str(db_path))
    db = cli.load_db(str(db_path))
    root_id = db["issues"][0]["id"]
    
    cli.import_tasks(str(plan_file), parent_id=root_id, db_path=str(db_path))
    
    db = cli.load_db(str(db_path))
    assert len(db["issues"]) == 4
    
    task_a = next(t for t in db["issues"] if t["title"] == "Task A")
    assert task_a["parent"] == root_id
    
    task_a1 = next(t for t in db["issues"] if t["title"] == "Task A.1")
    assert task_a1["parent"] == task_a["id"]

def test_import_tasks_idempotency(db_path, plan_file, capsys, monkeypatch):
    monkeypatch.setenv("SB_DB_PATH", str(db_path))
    cli.init()
    
    cli.import_tasks(str(plan_file), db_path=str(db_path))
    cli.import_tasks(str(plan_file), db_path=str(db_path))
    
    out, _ = capsys.readouterr()
    assert "Skipped 3 tasks" in out
    
    db = cli.load_db(str(db_path))
    assert len(db["issues"]) == 3

def test_import_tasks_file_not_found(capsys):
    cli.import_tasks("non_existent.md")
    out, _ = capsys.readouterr()
    assert "Error: File 'non_existent.md' not found" in out

def test_import_tasks_empty_file(tmp_path, capsys):
    empty_file = tmp_path / "empty.md"
    empty_file.write_text("")
    cli.import_tasks(str(empty_file))
    out, _ = capsys.readouterr()
    assert "No tasks found in file" in out
