import pytest
import os
from sb_tracker import cli

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite"
    os.environ["SB_DB_PATH"] = str(path)
    cli.init()
    return str(path)

def test_show_issue_details(db_path, capsys):
    cli.add("Detailed Task", description="Detailed desc", priority=1, db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    # Link some context
    cli.link_issue(task_id, branch="feat/X", worktree="/tmp/worktree", db_path=db_path)
    
    # Run verification
    cli.run_verification(task_id, "echo verified", db_path=db_path)
    
    capsys.readouterr()
    cli.show_issue(task_id, db_path=db_path)
    out, _ = capsys.readouterr()
    
    assert "Detailed Task" in out
    assert "Detailed desc" in out
    assert "Repo Branch: feat/X" in out
    assert "Worktree:    /tmp/worktree" in out
    assert "Verified: PASS" in out

def test_show_issue_json(db_path, capsys):
    cli.add("JSON Task", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    capsys.readouterr()
    cli.show_issue(task_id, as_json=True, db_path=db_path)
    out, _ = capsys.readouterr()
    import json
    data = json.loads(out)
    assert data["title"] == "JSON Task"

def test_show_issue_with_hierarchy(db_path, capsys):
    cli.add("Parent", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    pid = db["issues"][0]["id"]
    cli.add("Child", parent_id=pid, db_path=db_path)
    db = cli.load_db(db_path=db_path)
    cid = next(i["id"] for i in db["issues"] if i["title"] == "Child")
    
    # cid depends on pid
    cli.add_dependency(cid, pid, db_path=db_path)
    
    capsys.readouterr()
    cli.show_issue(cid, db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Parent:      Parent" in out
    assert f"Depends On:  {pid}" in out
    
    cli.show_issue(pid, db_path=db_path)
    out, _ = capsys.readouterr()
    assert f"Blocking:    {cid}" in out

def test_link_issue_noop(db_path, capsys):
    cli.add("Link Noop", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    tid = db["issues"][0]["id"]
    
    cli.link_issue(tid, branch="main", db_path=db_path)
    capsys.readouterr()
    
    # Second link with same branch should be noop
    cli.link_issue(tid, branch="main", db_path=db_path)
    out, _ = capsys.readouterr()
    assert "No changes for" in out
