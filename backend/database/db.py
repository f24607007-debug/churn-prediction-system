import sqlite3
import os
import bcrypt
from contextlib import contextmanager

DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'instance'))
DB_PATH = os.path.join(DB_DIR, 'churn_system.db')
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema.sql')

def _create_response(status="success", data=None, message=""):
    return {
        "status": status,
        "data": data if data is not None else {},
        "message": message
    }

@contextmanager
def get_connection(db_path=None):
    if db_path is None:
        db_path = DB_PATH
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_db(db_path=None):
    try:
        with get_connection(db_path) as conn:
            with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
                conn.executescript(f.read())
        return _create_response(data={"initialized": True}, message="Database initialized successfully.")
    except Exception as e:
        return _create_response(status="error", message=str(e))

def hash_password(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def insert_user(name, email, password, join_date, total_orders=0, total_spent=0.0, db_path=None):
    try:
        password_hash = hash_password(password)
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO users (name, email, password_hash, join_date, total_orders, total_spent)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (name, email, password_hash, join_date, total_orders, total_spent)
            )
            user_id = cursor.lastrowid
            return _create_response(data={"user_id": user_id}, message="User inserted successfully.")
    except Exception as e:
        return _create_response(status="error", message=str(e))

def get_customer_behavior(user_id, db_path=None):
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''SELECT * FROM customer_behavior WHERE user_id = ? ORDER BY created_at DESC''', (user_id,))
            rows = [dict(row) for row in cursor.fetchall()]
            return _create_response(data={"behavior": rows}, message="Customer behavior retrieved.")
    except Exception as e:
        return _create_response(status="error", message=str(e))

def add_chatbot_log(user_id, user_query, detected_intent, chatbot_response, confidence_score, escalated, created_at, db_path=None):
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO chatbot_logs (user_id, user_query, detected_intent, chatbot_response, confidence_score, escalated, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (user_id, user_query, detected_intent, chatbot_response, confidence_score, escalated, created_at)
            )
            log_id = cursor.lastrowid
            return _create_response(data={"log_id": log_id}, message="Chatbot log added successfully.")
    except Exception as e:
        return _create_response(status="error", message=str(e))

def log_retention_action(user_id, churn_score, action_type, action_message, created_at, db_path=None):
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO retention_actions (user_id, churn_score, action_type, action_message, created_at)
                   VALUES (?, ?, ?, ?, ?)''',
                (user_id, churn_score, action_type, action_message, created_at)
            )
            action_id = cursor.lastrowid
            return _create_response(data={"action_id": action_id}, message="Retention action logged successfully.")
    except Exception as e:
        return _create_response(status="error", message=str(e))
