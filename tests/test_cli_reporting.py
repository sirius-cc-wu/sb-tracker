import pytest
import os
from sb_tracker import cli

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite"
    os.environ["SB_DB_PATH"] = str(path)
    cli.init()
    return str(path)

def test_promote_issue(db_path, capsys):
    cli.add("Main Feature", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    cli.add("Subtask 1", parent_id=task_id, db_path=db_path)
    
    cli.promote_issue(task_id, db_path=db_path)
    out, _ = capsys.readouterr()
    
    assert f"### [{task_id}] Main Feature" in out
    assert "Sub-tasks" in out
    assert "Subtask 1" in out

def test_show_stats(db_path, capsys):
    cli.add("Task 1", db_path=db_path)
    cli.set_status(db["issues"][0]["id"] if "db" in locals() else cli.load_db(db_path=db_path)["issues"][0]["id"], "Done", db_path=db_path)
    
    cli.show_stats(db_path=db_path)
    out, _ = capsys.readouterr()
    assert "SB Tracker Statistics" in out
    assert "Total Issues:" in out
    assert "1" in out

def test_show_stats_empty(db_path, capsys):
    # Empty DB
    import os
    os.remove(db_path)
    cli.init()
    
    capsys.readouterr()
    cli.show_stats(db_path=db_path)
    out, _ = capsys.readouterr()
    assert "SB Tracker Statistics" in out
    assert "Total Issues:   0" in out
