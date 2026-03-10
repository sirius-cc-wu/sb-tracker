import sqlite3
import pytest
from sb_tracker import cli

def test_schema_migration(tmp_path):
    db_path = str(tmp_path / "migrate.sqlite")
    conn = sqlite3.connect(db_path)
    # Create v2 schema without linked_files_json
    conn.execute("CREATE TABLE issues (id TEXT PRIMARY KEY, title TEXT)")
    conn.execute("CREATE TABLE schema_info (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO schema_info (key, value) VALUES ('version', '2')")
    conn.commit()
    
    # Run migration
    cli._migrate_schema_if_needed(conn)
    
    cursor = conn.execute("PRAGMA table_info(issues)")
    columns = [row[1] for row in cursor.fetchall()]
    assert "linked_files_json" in columns
    conn.close()

def test_is_v2_schema_missing():
    conn = sqlite3.connect(":memory:")
    assert cli._is_v2_schema(conn) is False
    conn.close()

def test_has_legacy_blob_storage_missing():
    conn = sqlite3.connect(":memory:")
    assert cli._has_legacy_blob_storage(conn) is False
    conn.close()
