import json
import sqlite3

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


def test_legacy_blob_storage_auto_migrates_to_v2(tmp_path):
    db_path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE storage (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    legacy_db = cli._default_db_state()
    legacy_db["issues"].append(_issue("sb-legacy", "legacy task"))
    conn.execute(
        "INSERT INTO storage (key, value) VALUES ('db_json', ?)",
        (json.dumps(legacy_db),),
    )
    conn.execute(
        "INSERT INTO storage (key, value) VALUES ('revision', '7')"
    )
    conn.commit()
    conn.close()

    migrated = cli.load_db(str(db_path))
    assert [i["id"] for i in migrated["issues"]] == ["sb-legacy"]
    assert migrated["_storage_revision"] == 7
    assert list(tmp_path.glob("legacy.sqlite.bak.*"))

    conn = sqlite3.connect(str(db_path))
    has_storage = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='storage'"
    ).fetchone()
    assert has_storage is None
    schema_row = conn.execute(
        "SELECT value FROM schema_info WHERE key = 'version'"
    ).fetchone()
    assert schema_row[0] == "2"
    conn.close()


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
