import pytest

from sb_tracker import cli


def _issue(issue_id, title="task"):
    return {
        "id": issue_id,
        "title": title,
        "description": "",
        "priority": 2,
        "status": "Backlog",
        "depends_on": [],
        "events": [],
        "created_at": "2026-01-01T00:00:00",
    }


def test_sqlite_round_trip(tmp_path):
    db_path = tmp_path / "sb.sqlite"
    db = cli.load_db(str(db_path))
    db["issues"].append(_issue("sb-1"))
    cli.save_db(db, str(db_path))

    loaded = cli.load_db(str(db_path))
    assert [i["id"] for i in loaded["issues"]] == ["sb-1"]


def test_legacy_json_file_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy_path = tmp_path / ".sb.json"
    legacy_path.write_text("{}", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        cli.load_db()
    assert exc.value.code == 1


def test_stale_write_is_rejected(tmp_path):
    db_path = tmp_path / "sb.sqlite"
    first = cli.load_db(str(db_path))
    second = cli.load_db(str(db_path))

    first["issues"].append(_issue("sb-1"))
    cli.save_db(first, str(db_path))

    second["issues"].append(_issue("sb-2"))
    with pytest.raises(SystemExit) as exc:
        cli.save_db(second, str(db_path))
    assert exc.value.code == 1


def test_json_path_is_rejected(tmp_path):
    db_path = tmp_path / "db.json"
    with pytest.raises(SystemExit) as exc:
        cli.load_db(str(db_path))
    assert exc.value.code == 1
