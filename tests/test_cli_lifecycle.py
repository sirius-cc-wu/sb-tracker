import pytest

from sb_tracker import cli


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite"
    monkeypatch.setenv("SB_DB_PATH", str(path))
    cli.init()
    return str(path)


def test_finish_from_backlog_prints_guidance_and_keeps_status(db_path, capsys):
    cli.add("Task 1", db_path=db_path)
    task_id = cli.load_db(db_path=db_path)["issues"][0]["id"]

    cli.lifecycle_action(task_id, "finish", db_path=db_path)
    out, _ = capsys.readouterr()

    assert f"Error: cannot finish task {task_id} from status Backlog." in out
    assert f"sb begin {task_id}" in out

    task = cli.load_db(db_path=db_path)["issues"][0]
    assert task["status"] == "Backlog"
    finish_events = [e for e in task["events"] if e["type"] == "lifecycle_finish"]
    assert finish_events[-1]["result"] == "blocked"


def test_finish_help_flag_prints_lifecycle_preconditions(capsys, monkeypatch):
    monkeypatch.setattr(cli.sys, "argv", ["sb", "finish", "--help"])

    cli.main()
    out, _ = capsys.readouterr()

    assert "Usage: sb finish <id>" in out
    assert "Expected source states:" in out
    assert "If the task is still Backlog or Ready, run `sb begin <id>` first." in out


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("begin", "Move a task into Doing and capture current repo context."),
        ("pause", "Move a Doing task back to Ready."),
        ("verify", "Run a verification command and record its result on the task."),
        ("update", "Update task metadata such as title, desc, priority, parent, or status."),
        ("show", "Show task details, lifecycle state, dependencies, and event history."),
    ],
)
def test_command_help_variants_print_expected_guidance(command, expected, capsys):
    cli.print_command_help(command)
    out, _ = capsys.readouterr()

    assert f"Usage: sb {command}" in out
    assert expected in out


def test_unknown_command_help_falls_back_to_general_help(capsys):
    cli.print_command_help("list")
    out, _ = capsys.readouterr()

    assert "Usage: sb <command> [args]" in out
    assert "Lifecycle workflow:" in out


def test_finish_from_done_prints_noop_guidance_and_records_blocked_event(db_path, capsys):
    cli.add("Task 1", db_path=db_path)
    task_id = cli.load_db(db_path=db_path)["issues"][0]["id"]
    cli.set_status(task_id, "Done", db_path=db_path)
    capsys.readouterr()

    cli.lifecycle_action(task_id, "finish", db_path=db_path)
    out, _ = capsys.readouterr()

    assert f"No changes for {task_id}: task is already Done" in out
    task = cli.load_db(db_path=db_path)["issues"][0]
    finish_events = [e for e in task["events"] if e["type"] == "lifecycle_finish"]
    assert finish_events[-1]["result"] == "blocked"


def test_begin_force_reopen_moves_done_task_back_to_doing(db_path, capsys):
    cli.add("Task 1", db_path=db_path)
    task_id = cli.load_db(db_path=db_path)["issues"][0]["id"]
    cli.set_status(task_id, "Done", db_path=db_path)
    capsys.readouterr()

    cli.lifecycle_action(task_id, "begin", force_reopen=True, db_path=db_path)
    out, _ = capsys.readouterr()

    assert f"Updated {task_id} status to Doing" in out
    task = cli.load_db(db_path=db_path)["issues"][0]
    assert task["status"] == "Doing"
    begin_events = [e for e in task["events"] if e["type"] == "lifecycle_begin"]
    assert begin_events[-1]["result"] == "updated"


def test_pause_from_ready_prints_guidance_and_keeps_status(db_path, capsys):
    cli.add("Task 1", db_path=db_path)
    task_id = cli.load_db(db_path=db_path)["issues"][0]["id"]
    cli.lifecycle_action(task_id, "begin", db_path=db_path)
    cli.lifecycle_action(task_id, "pause", db_path=db_path)
    capsys.readouterr()

    cli.lifecycle_action(task_id, "pause", db_path=db_path)
    out, _ = capsys.readouterr()

    assert f"Error: cannot pause task {task_id} from status Ready." in out
    assert "only tasks in Doing can be paused" in out

    task = cli.load_db(db_path=db_path)["issues"][0]
    assert task["status"] == "Ready"
    pause_events = [e for e in task["events"] if e["type"] == "lifecycle_pause"]
    assert pause_events[-1]["result"] == "blocked"


def test_finish_from_unmapped_status_points_to_show(db_path, capsys):
    cli.add("Task 1", db_path=db_path)
    task_id = cli.load_db(db_path=db_path)["issues"][0]["id"]

    cli._print_lifecycle_guidance(task_id, "finish", "Blocked", "Done")
    out, _ = capsys.readouterr()

    assert f"Error: cannot finish task {task_id} from status Blocked." in out
    assert f"Hint: run `sb show {task_id}` to inspect lifecycle state." in out


def test_lifecycle_action_missing_issue_prints_not_found(db_path, capsys):
    cli.lifecycle_action("sb-missing", "finish", db_path=db_path)
    out, _ = capsys.readouterr()

    assert "Error: Issue sb-missing not found." in out


def test_link_issue_reports_missing_issue_and_usage(db_path, capsys):
    cli.link_issue("sb-missing", branch="feature-x", db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Error: Issue sb-missing not found." in out

    cli.add("Task 1", db_path=db_path)
    task_id = cli.load_db(db_path=db_path)["issues"][0]["id"]
    cli.link_issue(task_id, db_path=db_path)
    out, _ = capsys.readouterr()
    assert "Usage: sb link <id>" in out
