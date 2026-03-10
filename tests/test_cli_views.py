import pytest
import os
import json
from sb_tracker import cli

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite"
    os.environ["SB_DB_PATH"] = str(path)
    cli.init()
    return str(path)

def test_board_view(db_path, capsys):
    cli.add("Board Task", db_path=db_path)
    capsys.readouterr()
    
    cli.board_view(db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Backlog" in out
    assert "Board Task" in out

def test_board_filters(db_path, capsys):
    cli.add("Repo Task", repo="/repo/A", db_path=db_path)
    cli.add("Other Task", repo="/repo/B", db_path=db_path)
    
    capsys.readouterr()
    cli.board_view(repo_filter="/repo/A", db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Repo Task" in out
    assert "Other Task" not in out

def test_board_json(db_path, capsys):
    cli.add("JSON Board Task", db_path=db_path)
    capsys.readouterr()
    
    cli.board_view(as_json=True, db_path=db_path)
    out, _ = capsys.readouterr()
    data = json.loads(out)
    assert "columns" in data
    # data["columns"] is a list of {"name": ..., "issues": [...]}
    assert any(task["title"] == "JSON Board Task" for col in data["columns"] for task in col["issues"])

def test_list_json(db_path, capsys):
    cli.add("JSON Task", db_path=db_path)
    capsys.readouterr()
    
    cli.list_issues(as_json=True, db_path=db_path)
    out, _ = capsys.readouterr()
    data = json.loads(out)
    assert any(i["title"] == "JSON Task" for i in data["issues"])

def test_list_json_filters(db_path, capsys):
    cli.add("Filtered JSON", repo="/repo/F", db_path=db_path)
    capsys.readouterr()
    
    cli.list_issues(as_json=True, repo_filter="/repo/F", db_path=db_path)
    out, _ = capsys.readouterr()
    data = json.loads(out)
    assert any(i["title"] == "Filtered JSON" for i in data["issues"])

def test_list_json_compaction(db_path, capsys):
    db = cli.load_db(db_path=db_path)
    db["compaction_log"] = [{"summary": "Archived 10 tasks"}]
    cli.save_db(db, db_path=db_path)
    
    capsys.readouterr()
    cli.list_issues(as_json=True, db_path=db_path)
    out, _ = capsys.readouterr()
    data = json.loads(out)
    assert "compaction_log" in data
    assert data["compaction_log"][0]["summary"] == "Archived 10 tasks"

def test_search_json(db_path, capsys):
    cli.add("Search JSON", db_path=db_path)
    capsys.readouterr()
    
    cli.search_issues("Search", as_json=True, db_path=db_path)
    out, _ = capsys.readouterr()
    data = json.loads(out)
    assert any(i["title"] == "Search JSON" for i in data)
