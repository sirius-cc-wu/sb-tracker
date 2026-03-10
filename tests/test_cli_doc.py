import pytest
import os
from sb_tracker import cli

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite"
    os.environ["SB_DB_PATH"] = str(path)
    cli.init()
    return str(path)

def test_generate_doc_content(db_path):
    repo = "/mock/repo"
    cli.add("Task 1", repo=repo, db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    cli.run_verification(task_id, "echo 'test'", db_path=db_path)
    
    db = cli.load_db(db_path=db_path)
    content = cli.generate_doc_content(db, repo_filter=repo)
    
    assert "# Project Task Log" in content
    assert f"### [{task_id}] Task 1" in content
    assert "**Status:** Done" in content
    assert "Verification History" in content
    assert "**PASS** (cmd: `echo 'test'`)" in content

def test_sync_doc_execution(db_path, tmp_path, monkeypatch):
    repo = str(tmp_path)
    monkeypatch.chdir(repo)
    cli.add("Local Task", repo=repo, db_path=db_path)
    
    output_file = tmp_path / "CUSTOM_LOG.md"
    cli.sync_doc(output_file=str(output_file), db_path=db_path)
    
    assert output_file.exists()
    content = output_file.read_text()
    assert "Local Task" in content

def test_sync_doc_error(db_path, capsys):
    # Use a path that is likely to fail (e.g., directory where file expected)
    import os
    cli.sync_doc(output_file="/", db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Error writing project log" in out

def test_sync_doc_no_repo(db_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "get_repo_root", lambda: None)
    cli.sync_doc(db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Error: No repo root found" in out

def test_generate_doc_empty_repo(db_path):
    db = cli.load_db(db_path=db_path)
    content = cli.generate_doc_content(db, repo_filter="/non/existent")
    assert "No tasks recorded for this repository" in content

def test_generate_doc_with_description(db_path):
    cli.add("Task with Desc", description="This is a detailed description.", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    content = cli.generate_doc_content(db)
    assert "This is a detailed description." in content
