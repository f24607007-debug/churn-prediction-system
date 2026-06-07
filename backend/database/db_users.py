from __future__ import annotations

import bcrypt
import sqlite3

from .db_audit import _record_audit_event
from .db_core import (
    AuditEventCreate,
    MAX_EMAIL_LEN,
    MAX_NAME_LEN,
    UserCreate,
    _coerce_payload,
    _coerce_timestamp_utc,
    _connection_scope,
    _create_response,
    _fetch_user_row,
    _handle_db_error,
    _is_number,
    _is_str,
    _normalize_email,
    _normalize_text,
    _validate_email_format,
    _validate_max_length,
    _validate_non_empty_str,
    _validate_non_negative_int,
    _validate_positive_int,
)


def hash_password(password):
    """Return a bcrypt hash of *password* (str -> str)."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password, hashed):
    """Return True if *password* matches *hashed* bcrypt string."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _require_string(value, message):
    if not _is_str(value):
        raise ValueError(message)


def _require_non_empty(value, message):
    if not value.strip():
        raise ValueError(message)


def _require_min_length(value, minimum, message):
    if len(value) < minimum:
        raise ValueError(message)


def _require_not_equal(value, other, message):
    if value == other:
        raise ValueError(message)


def _validate_password_strength(password, email=None):
    """Raise ValueError if password does not meet minimum requirements."""
    _require_string(password, "Password must be a string.")
    _require_non_empty(password, "Password cannot be empty or whitespace.")
    _require_min_length(password, 8, "Password must be at least 8 characters long.")
    if email:
        _require_not_equal(
            password.strip().lower(),
            email,
            "Password cannot match the email address.",
        )


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------


def insert_user(user=None, db_path=None, conn=None, **kwargs):
    """
    Hash *password* and insert a new user row.
    Returns error response (not exception) on duplicate email.
    """
    try:
        user = _coerce_payload(user, UserCreate, kwargs=kwargs)
        normalized_name = _normalize_text(user.name)
        _validate_non_empty_str("name", normalized_name)
        _validate_max_length("name", normalized_name, MAX_NAME_LEN)
        normalized_email = _normalize_email(user.email)
        _validate_max_length("email", normalized_email, MAX_EMAIL_LEN)
        _validate_email_format(normalized_email)
        _validate_password_strength(user.password, email=normalized_email)
        _validate_non_negative_int("total_orders", user.total_orders)
        if not _is_number(user.total_spent) or user.total_spent < 0:
            raise ValueError("total_spent must be a non-negative number.")
        _validate_non_empty_str("join_date", user.join_date)
        join_date = _coerce_timestamp_utc("join_date", user.join_date)
        password_hash = hash_password(user.password)
        with _connection_scope(conn, db_path) as active_conn:
            cursor = active_conn.cursor()
            cursor.execute(
                """INSERT INTO users
                       (name, email, password_hash, join_date, total_orders, total_spent)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (normalized_name, normalized_email, password_hash,
                 join_date, user.total_orders, user.total_spent),
            )
            _record_audit_event(
                active_conn,
                AuditEventCreate(
                    event_type="user_created",
                    entity="users",
                    entity_id=cursor.lastrowid,
                    payload=f"email={normalized_email}",
                ),
            )
            return _create_response(data={"user_id": cursor.lastrowid},
                                    message="User inserted successfully.")
    except ValueError as e:
        return _create_response(status="error", message=str(e))
    except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
        return _create_response(status="error", message=str(e))


def get_user_by_id(user_id, db_path=None):
    """Fetch a single user row by primary key."""
    try:
        _validate_positive_int("user_id", user_id)
        return _fetch_user_row(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
            f"User {user_id} not found.",
            db_path=db_path,
        )
    except (ValueError, sqlite3.Error) as e:
        return _handle_db_error(e)


def get_user_by_email(email, db_path=None):
    """
    Fetch a single user row by email address.
    Used by the auth module for login.
    """
    try:
        normalized_email = _normalize_email(email)
        _validate_max_length("email", normalized_email, MAX_EMAIL_LEN)
        _validate_email_format(normalized_email)
        return _fetch_user_row(
            "SELECT * FROM users WHERE email = ?",
            (normalized_email,),
            f"No user found with email '{normalized_email}'.",
            db_path=db_path,
        )
    except (ValueError, sqlite3.Error) as e:
        return _handle_db_error(e)
