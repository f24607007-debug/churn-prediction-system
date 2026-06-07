from __future__ import annotations

import datetime
import os
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "instance"))
DB_PATH = os.path.join(DB_DIR, "churn_system.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
MAX_PAGE_SIZE = 500
MAX_NAME_LEN = 200
MAX_EMAIL_LEN = 254
MAX_TEXT_LEN = 2000
MAX_SUMMARY_LEN = 500


@dataclass(frozen=True)
class UserCreate:
    name: str
    email: str
    password: str
    join_date: str
    total_orders: int = 0
    total_spent: float = 0.0


@dataclass(frozen=True)
class CustomerBehaviorCreate:
    user_id: int
    login_frequency: int
    purchase_frequency: int
    cart_abandonment_count: int
    refund_count: int
    complaint_count: int
    inactivity_days: int
    churn_score: float
    created_at: str


@dataclass(frozen=True)
class ChatbotLogCreate:
    user_id: int
    user_query: str
    detected_intent: str | None
    chatbot_response: str | None
    confidence_score: float
    escalated: int
    created_at: str


@dataclass(frozen=True)
class EscalationCreate:
    user_id: int
    log_id: int | None
    issue_summary: str
    escalation_reason: str
    created_at: str
    status: str = "open"


@dataclass(frozen=True)
class RetentionActionCreate:
    user_id: int
    churn_score: float
    action_type: str
    action_message: str
    created_at: str


@dataclass(frozen=True)
class AuditEventCreate:
    event_type: str
    entity: str
    entity_id: int | None = None
    payload: str | None = None
    created_at: str | None = None


@dataclass(frozen=True)
class UserQuery:
    table: str
    data_key: str
    message: str


@dataclass(frozen=True)
class UserPageRequest:
    user_id: int
    limit: int = 100
    offset: int = 0
    after: str | None = None

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _create_response(status="success", data=None, message=""):
    """Standard JSON-serialisable response envelope used by all public functions."""
    return {
        "status": status,
        "data": data if data is not None else {},
        "message": message,
    }


def _is_str(value):
    return isinstance(value, str)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _normalize_text(value):
    if not _is_str(value):
        raise ValueError("Text fields must be strings.")
    return unicodedata.normalize("NFC", value)


def _normalize_email(email):
    """Return a normalized email string (lowercase, trimmed)."""
    if not _is_str(email):
        raise ValueError("Email must be a string.")
    normalized = _normalize_text(email).strip().lower()
    if not normalized:
        raise ValueError("Email cannot be empty.")
    return normalized


def _validate_non_empty_str(field, value):
    if not _is_str(value):
        raise ValueError(f"{field} must be a non-empty string.")
    if not value.strip():
        raise ValueError(f"{field} must be a non-empty string.")


def _validate_max_length(field, value, max_len):
    if len(value) > max_len:
        raise ValueError(f"{field} must be at most {max_len} characters.")


def _validate_positive_int(field, value):
    if not _is_int(value):
        raise ValueError(f"{field} must be a positive integer.")
    if value <= 0:
        raise ValueError(f"{field} must be a positive integer.")


def _validate_non_negative_int(field, value):
    if not _is_int(value):
        raise ValueError(f"{field} must be a non-negative integer.")
    if value < 0:
        raise ValueError(f"{field} must be a non-negative integer.")


def _validate_score(field, value):
    if value is None:
        raise ValueError(f"{field} must be a number between 0.0 and 1.0.")
    if not _is_number(value):
        raise ValueError(f"{field} must be a number between 0.0 and 1.0.")
    if value < 0.0 or value > 1.0:
        raise ValueError(f"{field} must be between 0.0 and 1.0.")


def _validate_pagination(limit, offset):
    _validate_non_negative_int("offset", offset)
    if not _is_int(limit):
        raise ValueError("limit must be a positive integer.")
    if limit <= 0:
        raise ValueError("limit must be a positive integer.")
    if limit > MAX_PAGE_SIZE:
        raise ValueError(f"limit cannot exceed {MAX_PAGE_SIZE}.")


def _validate_email_format(email):
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ValueError("Email format is invalid.")


def _normalize_optional_text(value):
    if value is None:
        return None
    if not _is_str(value):
        raise ValueError("Text fields must be strings.")
    if not value.strip():
        raise ValueError("Text fields cannot be empty or whitespace.")
    return _normalize_text(value)


def _coerce_timestamp_utc(field, value, allow_naive=True):
    if not _is_str(value):
        raise ValueError(f"{field} must be an ISO-8601 string.")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(raw)
    except ValueError:
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp.")
    if parsed.tzinfo is None:
        if not allow_naive:
            raise ValueError(f"{field} must include a timezone offset.")
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    else:
        parsed = parsed.astimezone(datetime.timezone.utc)
    return parsed.isoformat()


def _normalize_db_path(db_path, label):
    if db_path is None:
        return None
    if _is_str(db_path) and db_path.startswith("sqlite:///"):
        return db_path[len("sqlite:///") :]
    if _is_str(db_path) and "://" in db_path:
        raise ValueError(f"Only sqlite:/// URLs are supported for {label}.")
    return db_path


def _resolve_db_path(db_path=None):
    normalized = _normalize_db_path(db_path, "database paths")
    if normalized is not None:
        return normalized
    env_path = os.getenv("DATABASE_URL")
    normalized_env = _normalize_db_path(env_path, "DATABASE_URL")
    if normalized_env is not None:
        return normalized_env
    return DB_PATH


def _coerce_payload(payload, cls, kwargs=None):
    if kwargs:
        if payload is not None:
            raise ValueError("Provide either payload or keyword arguments, not both.")
        return cls(**kwargs)
    if isinstance(payload, cls):
        return payload
    if isinstance(payload, dict):
        return cls(**payload)
    if payload is None:
        raise ValueError(f"{cls.__name__} payload is required.")
    raise ValueError(f"Expected {cls.__name__} or dict.")


# ---------------------------------------------------------------------------
# Connection manager
# ---------------------------------------------------------------------------


@contextmanager
def get_connection(db_path=None):
    """
    Yield an open, FK-enforced SQLite connection.
    Commits on clean exit, rolls back on exception, always closes.
    """
    db_path = _resolve_db_path(db_path)
    if db_path != ":memory:" and "://" not in db_path:
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row

    # MUST be set per-connection — SQLite disables FK enforcement by default
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def transaction(db_path=None):
    """Run multiple operations inside a single transaction."""
    with get_connection(db_path) as conn:
        yield conn


@contextmanager
def _connection_scope(existing_conn, db_path=None):
    if existing_conn is not None:
        yield existing_conn
    else:
        with get_connection(db_path) as conn:
            yield conn


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------


MIGRATIONS = [
    {
        "id": "2025-01-01-add-audit-log",
        "sql": """
            CREATE TABLE IF NOT EXISTS audit_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT    NOT NULL,
                entity     TEXT    NOT NULL,
                entity_id  INTEGER,
                payload    TEXT,
                created_at TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_log_entity
                ON audit_log(entity, entity_id);
        """,
    },
    {
        "id": "2025-01-01-add-user-created-indexes",
        "sql": """
            CREATE INDEX IF NOT EXISTS idx_behavior_user_id_created_at
                ON customer_behavior(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_chatbot_logs_user_id_created_at
                ON chatbot_logs(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_escalations_user_id_created_at
                ON escalations(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_retention_user_id_created_at
                ON retention_actions(user_id, created_at);
        """,
    },
]


DESTRUCTIVE_MIGRATIONS = [
    {
        "id": "2025-01-01-rebuild-fk-cascades",
        "runner": "_migrate_fk_cascades",
    },
]


def init_db(db_path=None):
    """Create all tables and indexes from schema.sql (idempotent — IF NOT EXISTS)."""
    try:
        resolved_path = _resolve_db_path(db_path)
        if resolved_path != ":memory:" and "://" not in resolved_path:
            resolved_dir = os.path.dirname(resolved_path)
            if resolved_dir:
                os.makedirs(resolved_dir, exist_ok=True)
        raw_conn = sqlite3.connect(resolved_path, timeout=10)
        try:
            with open(SCHEMA_PATH, "r", encoding="utf-8") as handle:
                raw_conn.executescript(handle.read())
            raw_conn.execute("PRAGMA journal_mode = WAL")
            raw_conn.commit()
        finally:
            raw_conn.close()
        with get_connection(db_path) as conn:
            apply_migrations(conn=conn)
            if os.getenv("APPLY_DESTRUCTIVE_MIGRATIONS") == "1":
                apply_destructive_migrations(conn=conn)
        return _create_response(data={"initialized": True},
                                message="Database initialized successfully.")
    except (ValueError, sqlite3.Error) as e:
        return _handle_db_error(e)


def apply_migrations(db_path=None, conn=None):
    """Apply additive SQLite migrations in a deterministic order."""
    with _connection_scope(conn, db_path) as active_conn:
        _ensure_migrations_table(active_conn)
        applied = _fetch_applied_migrations(active_conn)
        applied_now = 0
        for migration in MIGRATIONS:
            if migration["id"] in applied:
                continue
            active_conn.executescript(migration["sql"])
            _record_migration(active_conn, migration["id"])
            applied_now += 1
    return _create_response(data={"applied": applied_now},
                            message="Migrations applied.")


def apply_destructive_migrations(db_path=None, conn=None):
    """Apply destructive migrations only when explicitly enabled."""
    with _connection_scope(conn, db_path) as active_conn:
        _ensure_migrations_table(active_conn)
        applied = _fetch_applied_migrations(active_conn)
        applied_now = 0
        for migration in DESTRUCTIVE_MIGRATIONS:
            if migration["id"] in applied:
                continue
            runner = globals().get(migration["runner"])
            if runner is None:
                raise ValueError(f"Missing migration runner: {migration['runner']}")
            runner(active_conn)
            _record_migration(active_conn, migration["id"])
            applied_now += 1
    return _create_response(data={"applied": applied_now},
                            message="Destructive migrations applied.")


def _ensure_migrations_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def _fetch_applied_migrations(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM schema_migrations")
    return {row[0] for row in cursor.fetchall()}


def _record_migration(conn, migration_id):
    conn.execute(
        "INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?)",
        (migration_id, datetime.datetime.now(datetime.timezone.utc).isoformat()),
    )


def _migrate_fk_cascades(conn):
    """Rebuild tables to attach ON DELETE behavior for existing databases."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name IN (
            'customer_behavior', 'chatbot_logs', 'escalations', 'retention_actions'
        )
        """
    )
    existing = {row[0] for row in cursor.fetchall()}
    required = {"customer_behavior", "chatbot_logs", "escalations", "retention_actions"}
    if not required.issubset(existing):
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    _rebuild_customer_behavior(conn)
    _rebuild_chatbot_logs(conn)
    _rebuild_escalations(conn)
    _rebuild_retention_actions(conn)
    _rebuild_indexes(conn)
    conn.execute("PRAGMA foreign_keys = ON")


def _rebuild_customer_behavior(conn):
    conn.executescript(
        """
        ALTER TABLE customer_behavior RENAME TO customer_behavior_old;
        CREATE TABLE customer_behavior (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id                INTEGER NOT NULL,
            login_frequency        INTEGER NOT NULL DEFAULT 0 CHECK(login_frequency        >= 0),
            purchase_frequency     INTEGER NOT NULL DEFAULT 0 CHECK(purchase_frequency     >= 0),
            cart_abandonment_count INTEGER NOT NULL DEFAULT 0 CHECK(cart_abandonment_count >= 0),
            refund_count           INTEGER NOT NULL DEFAULT 0 CHECK(refund_count           >= 0),
            complaint_count        INTEGER NOT NULL DEFAULT 0 CHECK(complaint_count        >= 0),
            inactivity_days        INTEGER NOT NULL DEFAULT 0 CHECK(inactivity_days        >= 0),
            churn_score            REAL    NOT NULL DEFAULT 0.0
                                   CHECK(churn_score >= 0.0 AND churn_score <= 1.0),
            created_at             TEXT    NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        INSERT INTO customer_behavior (
            id, user_id, login_frequency, purchase_frequency,
            cart_abandonment_count, refund_count, complaint_count,
            inactivity_days, churn_score, created_at
        )
        SELECT
            id, user_id, login_frequency, purchase_frequency,
            cart_abandonment_count, refund_count, complaint_count,
            inactivity_days, churn_score, created_at
        FROM customer_behavior_old;
        DROP TABLE customer_behavior_old;
        """
    )


def _rebuild_chatbot_logs(conn):
    conn.executescript(
        """
        ALTER TABLE chatbot_logs RENAME TO chatbot_logs_old;
        CREATE TABLE chatbot_logs (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          INTEGER NOT NULL,
            user_query       TEXT    NOT NULL,
            detected_intent  TEXT,
            chatbot_response TEXT,
            confidence_score REAL    CHECK(confidence_score >= 0.0 AND confidence_score <= 1.0),
            escalated        INTEGER NOT NULL DEFAULT 0 CHECK(escalated IN (0, 1)),
            created_at       TEXT    NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        INSERT INTO chatbot_logs (
            id, user_id, user_query, detected_intent, chatbot_response,
            confidence_score, escalated, created_at
        )
        SELECT
            id, user_id, user_query, detected_intent, chatbot_response,
            confidence_score, escalated, created_at
        FROM chatbot_logs_old;
        DROP TABLE chatbot_logs_old;
        """
    )


def _rebuild_escalations(conn):
    conn.executescript(
        """
        ALTER TABLE escalations RENAME TO escalations_old;
        CREATE TABLE escalations (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER NOT NULL,
            log_id            INTEGER,
            issue_summary     TEXT    NOT NULL,
            escalation_reason TEXT    NOT NULL,
            status            TEXT    NOT NULL DEFAULT 'open'
                              CHECK(status IN ('open', 'in_progress', 'resolved')),
            created_at        TEXT    NOT NULL,
            updated_at        TEXT    NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(log_id)  REFERENCES chatbot_logs(id) ON DELETE SET NULL
        );
        INSERT INTO escalations (
            id, user_id, log_id, issue_summary, escalation_reason,
            status, created_at, updated_at
        )
        SELECT
            id, user_id, log_id, issue_summary, escalation_reason,
            status, created_at, updated_at
        FROM escalations_old;
        DROP TABLE escalations_old;
        """
    )


def _rebuild_retention_actions(conn):
    conn.executescript(
        """
        ALTER TABLE retention_actions RENAME TO retention_actions_old;
        CREATE TABLE retention_actions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            churn_score    REAL    NOT NULL CHECK(churn_score >= 0.0 AND churn_score <= 1.0),
            action_type    TEXT    NOT NULL,
            action_message TEXT    NOT NULL,
            created_at     TEXT    NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        INSERT INTO retention_actions (
            id, user_id, churn_score, action_type, action_message, created_at
        )
        SELECT
            id, user_id, churn_score, action_type, action_message, created_at
        FROM retention_actions_old;
        DROP TABLE retention_actions_old;
        """
    )


def _rebuild_indexes(conn):
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_behavior_user_id
            ON customer_behavior(user_id);
        CREATE INDEX IF NOT EXISTS idx_behavior_user_id_created_at
            ON customer_behavior(user_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_chatbot_logs_user_id
            ON chatbot_logs(user_id);
        CREATE INDEX IF NOT EXISTS idx_chatbot_logs_user_id_created_at
            ON chatbot_logs(user_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_escalations_user_id
            ON escalations(user_id);
        CREATE INDEX IF NOT EXISTS idx_escalations_log_id
            ON escalations(log_id);
        CREATE INDEX IF NOT EXISTS idx_escalations_user_id_created_at
            ON escalations(user_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_retention_user_id
            ON retention_actions(user_id);
        CREATE INDEX IF NOT EXISTS idx_retention_user_id_created_at
            ON retention_actions(user_id, created_at);
        """
    )


# ---------------------------------------------------------------------------
# Generic query helpers
# ---------------------------------------------------------------------------


def _fetch_user_row(query, params, not_found_message, db_path=None):
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
    if row is None:
        return _create_response(status="error", message=not_found_message)
    user_data = dict(row)
    user_data.pop("password_hash", None)
    return _create_response(data={"user": user_data}, message="User retrieved.")


def _validate_escalation_log(cursor, user_id, log_id):
    if log_id is None:
        return
    cursor.execute("SELECT user_id FROM chatbot_logs WHERE id = ?", (log_id,))
    log_row = cursor.fetchone()
    if log_row is None:
        raise ValueError("log_id does not exist.")
    if log_row["user_id"] != user_id:
        raise ValueError("log_id does not belong to user_id.")


def _handle_db_error(error):
    return _create_response(status="error", message=str(error))


QUERY_DEFS = {
    "customer_behavior": UserQuery(
        table="customer_behavior",
        data_key="behavior",
        message="Customer behavior retrieved.",
    ),
    "chatbot_logs": UserQuery(
        table="chatbot_logs",
        data_key="logs",
        message="Chatbot logs retrieved.",
    ),
    "escalations": UserQuery(
        table="escalations",
        data_key="escalations",
        message="Escalations retrieved.",
    ),
    "retention_actions": UserQuery(
        table="retention_actions",
        data_key="retention_actions",
        message="Retention actions retrieved.",
    ),
}


def _fetch_by_user(query_def, page, db_path=None):
    _validate_positive_int("user_id", page.user_id)
    _validate_pagination(page.limit, page.offset)
    if query_def.table not in QUERY_DEFS:
        raise ValueError("Invalid table in query definition.")
    after = None
    if page.after is not None:
        after = _coerce_timestamp_utc("after", page.after)
    query = (
        f"SELECT * FROM {query_def.table} "
        "WHERE user_id = ? "
        "ORDER BY created_at DESC "
        "LIMIT ? OFFSET ?"
    )
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if after is None:
            cursor.execute(query, (page.user_id, page.limit, page.offset))
        else:
            cursor.execute(
                f"SELECT * FROM {query_def.table} WHERE user_id = ? AND created_at < ? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (page.user_id, after, page.limit, page.offset),
            )
        rows = [dict(row) for row in cursor.fetchall()]
    return _create_response(data={query_def.data_key: rows}, message=query_def.message)


def get_user_records(kind, user_id, limit=100, offset=0, after=None, db_path=None):
    query_def = QUERY_DEFS.get(kind)
    if query_def is None:
        return _handle_db_error(ValueError("Unknown query kind."))
    page = UserPageRequest(user_id=user_id, limit=limit, offset=offset, after=after)
    try:
        return _fetch_by_user(query_def, page, db_path=db_path)
    except (ValueError, sqlite3.Error) as e:
        return _handle_db_error(e)
