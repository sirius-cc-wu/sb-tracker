import pytest
import os
from sb_tracker import cli

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite"
    os.environ["SB_DB_PATH"] = str(path)
    cli.init()
    return str(path)

def test_list_ready_only(db_path, capsys):
    cli.add("Blocked", db_path=db_path)
    cli.add("Blocker", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    id_blocked = db["issues"][0]["id"]
    id_blocker = db["issues"][1]["id"]
    
    cli.add_dependency(id_blocked, id_blocker, db_path=db_path)
    
    capsys.readouterr()
    cli.list_issues(ready_only=True, db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Blocker" in out
    assert "Blocked" not in out

def test_list_ready_none(db_path, capsys):
    # Setup: cyclic dependency or just everything blocked
    cli.add("A", db_path=db_path)
    cli.add("B", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    id_a = db["issues"][0]["id"]
    id_b = db["issues"][1]["id"]
    cli.add_dependency(id_a, id_b, db_path=db_path)
    cli.add_dependency(id_b, id_a, db_path=db_path)
    
    capsys.readouterr()
    cli.list_issues(ready_only=True, db_path=db_path)
    out, _ = capsys.readouterr()
    assert "No issues found matching criteria" in out

def test_list_all_includes_done(db_path, capsys):
    cli.add("Done Task", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    cli.set_status(task_id, "Done", db_path=db_path)
    
    capsys.readouterr()
    cli.list_issues(show_all=False, db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Done Task" not in out
    
    cli.list_issues(show_all=True, db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Done Task" in out

def test_list_repo_filter(db_path, capsys):
    cli.add("Repo Task", repo="/repo/A", db_path=db_path)
    cli.add("Other Task", repo="/repo/B", db_path=db_path)
    
    capsys.readouterr()
    cli.list_issues(repo_filter="/repo/A", db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Repo Task" in out
    assert "Other Task" not in out

def test_list_branch_filter(db_path, capsys):
    cli.add("Branch Task", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    tid = db["issues"][0]["id"]
    cli.link_issue(tid, branch="feat/X", db_path=db_path)
    
    capsys.readouterr()
    cli.list_issues(branch_filter="feat/X", db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Branch Task" in out

def test_list_legacy_ids(db_path, capsys):
    # Add legacy style ID
    cli.add("Parent", custom_id="P1", db_path=db_path)
    cli.add("Child", custom_id="P1.1", db_path=db_path)
    
    capsys.readouterr()
    cli.list_issues(db_path=db_path)
    out, _ = capsys.readouterr()
    # Tree view should show them nested
    assert "P1" in out
    assert "P1.1" in out

def test_list_unmapped_status(db_path, capsys):
    cli.add("Unmapped Task", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    tid = db["issues"][0]["id"]
    
    # Manually set an unmapped status
    db = cli.load_db(db_path=db_path)
    task = next(i for i in db["issues"] if i["id"] == tid)
    task["status"] = "AlienStatus"
    cli.save_db(db, db_path=db_path)
    
    capsys.readouterr()
    cli.list_issues(db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Unmapped Task" in out
    assert "Unmapped" in out

def test_list_global_only(db_path, capsys):
    cli.add("Local Task", repo="/repo/L", db_path=db_path)
    cli.add("Global Task", repo=None, db_path=db_path)
    
    capsys.readouterr()
    cli.list_issues(global_only=True, db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Global Task" in out
    assert "Local Task" not in out

def test_list_branch_worktree_filters(db_path, capsys):
    cli.add("Target Task", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    tid = db["issues"][0]["id"]
    cli.link_issue(tid, branch="feat/B", worktree="/tmp/W", db_path=db_path)
    
    capsys.readouterr()
    cli.list_issues(branch_filter="feat/B", worktree_filter="/tmp/W", db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Target Task" in out

def test_list_explicit_repo_path(db_path, tmp_path, capsys):
    repo_path = str(tmp_path / "explicit_repo")
    os.mkdir(repo_path)
    cli.add("Explicit Repo Task", repo=repo_path, db_path=db_path)
    
    capsys.readouterr()
    cli.list_issues(repo_filter=repo_path, db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Explicit Repo Task" in out
