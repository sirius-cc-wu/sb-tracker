import json
import sqlite3
from sb_tracker import cli

def test_meta_helpers(tmp_path):
    db_path = str(tmp_path / "meta.sqlite")
    conn = cli._connect_sqlite(db_path)
    cli._create_v2_schema(conn)
    
    cli._upsert_meta(conn, "key1", "val1")
    row = conn.execute("SELECT value FROM meta WHERE key = 'key1'").fetchone()
    assert row[0] == "val1"
    
    cli._delete_meta(conn, "key1")
    row = conn.execute("SELECT value FROM meta WHERE key = 'key1'").fetchone()
    assert row is None
    conn.close()

def test_serialize_event_payload():
    event = {"type": "t", "timestamp": "ts", "data": "val"}
    payload = cli._serialize_event_payload(event)
    assert json.loads(payload) == {"data": "val"}
    
    event_empty = {"type": "t", "timestamp": "ts"}
    assert cli._serialize_event_payload(event_empty) is None

def test_touch_lifecycle():
    issue = {}
    cli._touch_lifecycle(issue, "test_event", started=True)
    assert "lifecycle" in issue
    assert issue["lifecycle"]["last_event_type"] == "test_event"
    assert "started_at" in issue["lifecycle"]
    assert "last_event_at" in issue["lifecycle"]
