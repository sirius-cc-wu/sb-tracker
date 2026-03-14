import pytest
import subprocess
from sb_tracker import cli

@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite"
    monkeypatch.setenv("SB_DB_PATH", str(path))
    cli.init()
    return str(path)

def test_verify_success(db_path, capsys):
    cli.add("Task 1", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    # Run verify with a successful command
    cli.run_verification(task_id, "echo 'hello world'", db_path=db_path)
    out, _ = capsys.readouterr()
    
    assert "Verification SUCCESS" in out
    
    db = cli.load_db(db_path=db_path)
    task = db["issues"][0]
    # Default behavior for success is Done
    assert task["status"] == "Done"
    
    # Check audit log
    events = [e for e in task["events"] if e["type"] == "verification_result"]
    assert len(events) == 1
    assert events[0]["exit_code"] == 0
    assert "hello world" in events[0]["output"]

def test_verify_failure(db_path, capsys):
    cli.add("Task 2", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    # Run verify with a failing command
    cli.run_verification(task_id, "exit 1", db_path=db_path)
    out, _ = capsys.readouterr()
    
    assert "Verification FAILED" in out
    
    db = cli.load_db(db_path=db_path)
    task = db["issues"][0]
    # Should NOT be Done
    assert task["status"] != "Done"
    
    # Check audit log
    events = [e for e in task["events"] if e["type"] == "verification_result"]
    assert len(events) == 1
    assert events[0]["exit_code"] != 0

def test_verify_with_needs_review(db_path, capsys):
    cli.add("Task 3", needs_review=True, db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task_id = db["issues"][0]["id"]
    
    # Run verify with success
    cli.run_verification(task_id, "echo 'ready'", db_path=db_path)
    
    db = cli.load_db(db_path=db_path)
    task = db["issues"][0]
    # Should be Review, not Done
    assert task["status"] == "Review"


def test_verify_timeout_zero_disables_timeout(db_path, capsys, monkeypatch):
    cli.add("Task 4", db_path=db_path)
    task_id = cli.load_db(db_path=db_path)["issues"][0]["id"]
    seen = {}

    def fake_run(*args, **kwargs):
        seen["timeout"] = kwargs["timeout"]
        return subprocess.CompletedProcess(args[0], 0, stdout="all good")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    exit_code = cli.run_verification(
        task_id,
        "echo 'all good'",
        timeout_seconds=0,
        db_path=db_path,
    )
    out, _ = capsys.readouterr()

    assert exit_code == 0
    assert seen["timeout"] is None
    assert "Timeout: no timeout" in out


def test_verify_uses_repo_verify_timeout_config(db_path, monkeypatch):
    cli.add("Task 5", db_path=db_path)
    db = cli.load_db(db_path=db_path)
    task = db["issues"][0]
    task["repo"] = "/tmp/repo"
    db["meta"]["verify_timeout_by_repo"] = {"/tmp/repo": 42}
    cli.save_db(db, db_path=db_path)
    seen = {}

    def fake_run(*args, **kwargs):
        seen["timeout"] = kwargs["timeout"]
        return subprocess.CompletedProcess(args[0], 0, stdout="ok")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    exit_code = cli.run_verification(task["id"], "echo ok", db_path=db_path)

    assert exit_code == 0
    assert seen["timeout"] == 42


def test_verify_main_returns_command_exit_code_on_failure(db_path, monkeypatch, capsys):
    cli.add("Task 6", db_path=db_path)
    task_id = cli.load_db(db_path=db_path)["issues"][0]["id"]

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 3, stdout="boom")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["sb", "verify", task_id, "--cmd", "fake command"],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    out, _ = capsys.readouterr()
    assert exc.value.code == 3
    assert "Verification FAILED (Exit 3)" in out


def test_verify_main_returns_timeout_exit_code(db_path, monkeypatch, capsys):
    cli.add("Task 7", db_path=db_path)
    task_id = cli.load_db(db_path=db_path)["issues"][0]["id"]

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["sb", "verify", task_id, "--cmd", "slow command", "--timeout", "7"],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    out, _ = capsys.readouterr()
    assert exc.value.code == cli.VERIFY_TIMEOUT_EXIT_CODE
    assert "Verification timed out after 7 seconds." in out


def test_verify_missing_issue_returns_error(db_path, capsys):
    exit_code = cli.run_verification("sb-missing", "echo nope", db_path=db_path)
    out, _ = capsys.readouterr()

    assert exit_code == 2
    assert "Error: Issue sb-missing not found." in out


def test_verify_execution_error_records_failure(db_path, monkeypatch):
    cli.add("Task 8", db_path=db_path)
    task_id = cli.load_db(db_path=db_path)["issues"][0]["id"]

    def fake_run(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    exit_code = cli.run_verification(task_id, "bad command", db_path=db_path)
    task = cli.load_db(db_path=db_path)["issues"][0]
    event = [e for e in task["events"] if e["type"] == "verification_result"][-1]

    assert exit_code == -2
    assert event["exit_code"] == -2
    assert "kaboom" in event["output"]


def test_verify_truncates_long_output(db_path, monkeypatch):
    cli.add("Task 9", db_path=db_path)
    task_id = cli.load_db(db_path=db_path)["issues"][0]["id"]

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout="x" * 3000)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    cli.run_verification(task_id, "long output", db_path=db_path)
    task = cli.load_db(db_path=db_path)["issues"][0]
    event = [e for e in task["events"] if e["type"] == "verification_result"][-1]

    assert event["output"].endswith("... (output truncated)")


def test_verify_failure_does_not_reopen_done_task(db_path, monkeypatch):
    cli.add("Task 10", db_path=db_path)
    task_id = cli.load_db(db_path=db_path)["issues"][0]["id"]
    cli.set_status(task_id, "Done", db_path=db_path)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, stdout="fail")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    cli.run_verification(task_id, "still fail", db_path=db_path)
    task = cli.load_db(db_path=db_path)["issues"][0]

    assert task["status"] == "Done"


def test_verify_main_rejects_invalid_timeout_value(db_path, monkeypatch, capsys):
    cli.add("Task 11", db_path=db_path)
    task_id = cli.load_db(db_path=db_path)["issues"][0]["id"]
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["sb", "verify", task_id, "--cmd", "fake command", "--timeout", "abc"],
    )

    cli.main()
    out, _ = capsys.readouterr()

    assert "verify timeout must be a non-negative integer" in out
    assert "Usage: sb verify" in out


def test_verify_main_without_command_prints_help(db_path, monkeypatch, capsys):
    cli.add("Task 12", db_path=db_path)
    task_id = cli.load_db(db_path=db_path)["issues"][0]["id"]
    monkeypatch.setattr(cli.sys, "argv", ["sb", "verify", task_id])

    cli.main()
    out, _ = capsys.readouterr()

    assert "Usage: sb verify" in out
