import pytest
import os
from sb_tracker import cli

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite"
    os.environ["SB_DB_PATH"] = str(path)
    cli.init()
    return str(path)

def test_config_get_prefix(db_path, capsys):
    cli.show_stats(db_path=db_path) # Warm up
    
    capsys.readouterr()
    # Mock main behavior for config get prefix
    db = cli.load_db(db_path=db_path)
    prefix = cli._resolve_prefix(db)
    print(f"ID prefix: {prefix}")
    out, _ = capsys.readouterr()
    assert "ID prefix: sb" in out

def test_init_explicit_path(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "explicit.sqlite"
    monkeypatch.setenv("SB_DB_PATH", str(db_path))
    cli.init()
    out, _ = capsys.readouterr()
    assert "Initialized Simple Beads in" in out
    assert str(db_path) in out
    assert db_path.exists()

def test_parse_common_flags():
    args = ["task", "--global", "--branch", "feat/X"]
    cleaned, opts = cli.parse_common_flags(args)
    assert cleaned == ["task"]
    assert opts["global_only"] is True
    assert opts["branch"] == "feat/X"

def test_config_set_prefix_global(db_path, capsys):
    # We call main to test dispatch
    import sys
    orig_argv = sys.argv
    sys.argv = ["sb", "config", "prefix", "TEST", "--global"]
    try:
        cli.main()
    finally:
        sys.argv = orig_argv
    
    out, _ = capsys.readouterr()
    assert "Global prefix set to: TEST" in out
    
    db = cli.load_db(db_path=db_path)
    assert db["meta"]["id_prefix"] == "TEST"

def test_config_set_prefix_repo(db_path, capsys, monkeypatch):
    repo = "/repo/X"
    monkeypatch.setattr(cli, "get_repo_root", lambda **kwargs: repo)
    
    import sys
    orig_argv = sys.argv
    sys.argv = ["sb", "config", "prefix", "REPO"]
    try:
        cli.main()
    finally:
        sys.argv = orig_argv
    
    out, _ = capsys.readouterr()
    assert "Prefix for /repo/X set to: REPO" in out
    
    db = cli.load_db(db_path=db_path)
    assert db["meta"]["prefix_by_repo"][repo] == "REPO"

def test_config_get_prefix_main(db_path, capsys):
    import sys
    orig_argv = sys.argv
    sys.argv = ["sb", "config", "get", "prefix"]
    try:
        cli.main()
    finally:
        sys.argv = orig_argv
    
    out, _ = capsys.readouterr()
    assert "sb" in out or "SB" in out # default is sb
