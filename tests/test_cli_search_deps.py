import pytest
import os
from sb_tracker import cli

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite"
    os.environ["SB_DB_PATH"] = str(path)
    cli.init()
    return str(path)

def test_dependencies(db_path, capsys):
    cli.add("Task 1", db_path=db_path)
    cli.add("Task 2", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    id1 = db["issues"][0]["id"]
    id2 = db["issues"][1]["id"]
    
    cli.add_dependency(id2, id1, db_path=db_path)
    out, _ = capsys.readouterr()
    assert f"Linked {id2} -> depends on -> {id1}" in out
    
    db = cli.load_db(db_path=db_path)
    task2 = next(i for i in db["issues"] if i["id"] == id2)
    assert id1 in task2["depends_on"]

def test_add_dependency_not_found(db_path, capsys):
    cli.add("Task", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    tid = db["issues"][0]["id"]
    
    cli.add_dependency(tid, "missing", db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Error: Parent issue missing not found" in out

def test_add_dependency_child_not_found(db_path, capsys):
    cli.add("Task", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    tid = db["issues"][0]["id"]
    
    cli.add_dependency("missing", tid, db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Error: Child issue missing not found" in out

def test_search(db_path, capsys):
    cli.add("Find Me", description="Hidden treasure here.", db_path=db_path)
    cli.add("Ignore Me", db_path=db_path)
    
    capsys.readouterr() # Clear buffer
    
    cli.search_issues("treasure", db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Find Me" in out
    assert "Ignore Me" not in out
