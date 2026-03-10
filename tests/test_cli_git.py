import pytest
import os
import subprocess
from sb_tracker import cli

def test_git_helpers(tmp_path):
    repo = tmp_path / "git-repo"
    repo.mkdir()
    
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), capture_output=True)
    
    # Create a commit
    (repo / "file.txt").write_text("hello")
    subprocess.run(["git", "add", "file.txt"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=str(repo), capture_output=True)
    
    assert cli.get_repo_root(cwd=str(repo)) == str(repo)
    assert len(cli.get_repo_commit(cwd=str(repo))) == 40
    assert cli.get_repo_branch(cwd=str(repo)) in ["main", "master"]

def test_run_git_error():
    # Calling git in a non-repo should return None
    assert cli._run_git(["rev-parse", "HEAD"], cwd="/tmp") is None
    assert cli.get_repo_root(cwd="/tmp") is None
    assert cli.get_repo_commit(cwd="/tmp") is None
    assert cli.get_repo_branch(cwd="/tmp") is None
    assert cli.get_worktree_path(cwd="/tmp") is None
