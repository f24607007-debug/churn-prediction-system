from __future__ import annotations

import datetime
import sqlite3
import sys

from .db_core import (
    AuditEventCreate,
    MAX_TEXT_LEN,
    _coerce_payload,
    _coerce_timestamp_utc,
    _connection_scope,
    _handle_db_error,
    _normalize_optional_text,
    _normalize_text,
    _validate_max_length,
    _validate_non_empty_str,
    _validate_positive_int,
)


def log_audit_event(event=None, db_path=None, conn=None, **kwargs):
    """Record a lightweight audit event for observability and debugging."""
    try:
        event = _coerce_payload(event, AuditEventCreate, kwargs=kwargs)
        normalized_event = _normalize_text(event.event_type)
        normalized_entity = _normalize_text(event.entity)
        _validate_non_empty_str("event_type", normalized_event)
        _validate_non_empty_str("entity", normalized_entity)
        _validate_max_length("event_type", normalized_event, MAX_TEXT_LEN)
        _validate_max_length("entity", normalized_entity, MAX_TEXT_LEN)
        if event.entity_id is not None:
            _validate_positive_int("entity_id", event.entity_id)
        normalized_payload = _normalize_optional_text(event.payload)
        if normalized_payload is not None:
            _validate_max_length("payload", normalized_payload, MAX_TEXT_LEN)
        created_at = event.created_at
        if created_at is None:
            created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        created_at = _coerce_timestamp_utc("created_at", created_at)
        with _connection_scope(conn, db_path) as active_conn:
            cursor = active_conn.cursor()
            cursor.execute(
                """INSERT INTO audit_log
                       (event_type, entity, entity_id, payload, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (normalized_event, normalized_entity, event.entity_id, normalized_payload, created_at),
            )
            return {
                "status": "success",
                "data": {"audit_id": cursor.lastrowid},
                "message": "Audit event logged successfully.",
            }
    except ValueError as e:
        return _handle_db_error(e)
    except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
        return _handle_db_error(e)


def _record_audit_event(conn, event):
    """Record an audit event inside an existing transaction."""
    if conn is None:
        raise ValueError("Connection is required for audit logging.")
    try:
        result = log_audit_event(event, conn=conn)
        if result["status"] != "success":
            print(f"[audit] failed to log event: {result['message']}", file=sys.stderr)
    except Exception as exc:
        print(f"[audit] failed to log event: {exc}", file=sys.stderr)
