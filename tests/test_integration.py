import pytest
import sqlite3
import os
import sys
import datetime
from unittest.mock import patch
from contextlib import contextmanager

# Add project root to sys.path so we can import from backend natively
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.database.db import insert_user

@pytest.fixture
def mock_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row

    @contextmanager
    def mock_get_connection(db_path=None):
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    with patch('database.db.get_connection', new=mock_get_connection):
        schema_path = os.path.join(os.path.dirname(__file__), '..', 'backend', 'database', 'schema.sql')
        with open(schema_path, 'r', encoding='utf-8') as f:
            conn.executescript(f.read())
        yield conn
        
    conn.close()

def test_insert_user_hashing_and_response(mock_db):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # Ensure insert_user returns standard JSON success format
    res = insert_user("John Doe", "john@example.com", "securepass", now, 5, 250.0)
    
    assert res["status"] == "success"
    assert "data" in res
    assert "user_id" in res["data"]
    assert res["message"] == "User inserted successfully."
    
    user_id = res["data"]["user_id"]
    
    # Verify the stored password is hashed and not plaintext
    cursor = mock_db.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    
    stored_hash = row["password_hash"]
    assert stored_hash != "securepass"
    assert stored_hash.startswith("$2b$") # bcrypt identifier prefix
