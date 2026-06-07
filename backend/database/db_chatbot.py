from __future__ import annotations

import sqlite3

from .db_audit import _record_audit_event
from .db_core import (
    AuditEventCreate,
    ChatbotLogCreate,
    EscalationCreate,
    MAX_SUMMARY_LEN,
    MAX_TEXT_LEN,
    _coerce_payload,
    _coerce_timestamp_utc,
    _connection_scope,
    _handle_db_error,
    _normalize_optional_text,
    _normalize_text,
    _validate_escalation_log,
    _validate_max_length,
    _validate_non_empty_str,
    _validate_positive_int,
    _validate_score,
    get_user_records,
)


# ---------------------------------------------------------------------------
# chatbot_logs
# ---------------------------------------------------------------------------


def add_chatbot_log(log=None, db_path=None, conn=None, **kwargs):
    """
    Persist one chatbot interaction.
    *escalated* should be 1 if confidence_score < 0.75, else 0.
    """
    try:
        log = _coerce_payload(log, ChatbotLogCreate, kwargs=kwargs)
        _validate_positive_int("user_id", log.user_id)
        user_query = _normalize_text(log.user_query)
        _validate_non_empty_str("user_query", user_query)
        _validate_max_length("user_query", user_query, MAX_TEXT_LEN)
        detected_intent = _normalize_optional_text(log.detected_intent)
        if detected_intent is not None:
            _validate_max_length("detected_intent", detected_intent, MAX_TEXT_LEN)
        chatbot_response = _normalize_optional_text(log.chatbot_response)
        if chatbot_response is not None:
            _validate_max_length("chatbot_response", chatbot_response, MAX_TEXT_LEN)
        _validate_score("confidence_score", log.confidence_score)
        if log.escalated not in (0, 1):
            raise ValueError("escalated must be 0 or 1.")
        _validate_non_empty_str("created_at", log.created_at)
        created_at = _coerce_timestamp_utc("created_at", log.created_at)
        with _connection_scope(conn, db_path) as active_conn:
            cursor = active_conn.cursor()
            cursor.execute(
                """INSERT INTO chatbot_logs
                       (user_id, user_query, detected_intent, chatbot_response,
                        confidence_score, escalated, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (log.user_id, user_query, detected_intent, chatbot_response,
                 log.confidence_score, log.escalated, created_at),
            )
            _record_audit_event(
                active_conn,
                AuditEventCreate(
                    event_type="chatbot_log_added",
                    entity="chatbot_logs",
                    entity_id=cursor.lastrowid,
                    payload=f"user_id={log.user_id};escalated={log.escalated}",
                ),
            )
            return {
                "status": "success",
                "data": {"log_id": cursor.lastrowid},
                "message": "Chatbot log added successfully.",
            }
    except ValueError as e:
        return _handle_db_error(e)
    except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
        return _handle_db_error(e)


def get_chatbot_logs(user_id, db_path=None, limit=100, offset=0, after=None):
    """Return all chatbot log rows for *user_id*, newest first."""
    return get_user_records("chatbot_logs", user_id, limit, offset, after=after, db_path=db_path)


# ---------------------------------------------------------------------------
# escalations
# ---------------------------------------------------------------------------


def insert_escalation(escalation=None, db_path=None, conn=None, **kwargs):
    """
    Create an escalation record linked to a chatbot_log row.
    Called by Member 2's chatbot module when confidence_score < 0.75.
    """
    try:
        escalation = _coerce_payload(escalation, EscalationCreate, kwargs=kwargs)
        _validate_positive_int("user_id", escalation.user_id)
        if escalation.log_id is not None:
            _validate_positive_int("log_id", escalation.log_id)
        issue_summary = _normalize_text(escalation.issue_summary)
        escalation_reason = _normalize_text(escalation.escalation_reason)
        _validate_non_empty_str("issue_summary", issue_summary)
        _validate_non_empty_str("escalation_reason", escalation_reason)
        _validate_max_length("issue_summary", issue_summary, MAX_SUMMARY_LEN)
        _validate_max_length("escalation_reason", escalation_reason, MAX_TEXT_LEN)
        _validate_non_empty_str("created_at", escalation.created_at)
        created_at = _coerce_timestamp_utc("created_at", escalation.created_at)
        if escalation.status not in ("open", "in_progress", "resolved"):
            raise ValueError("status must be one of: open, in_progress, resolved.")
        with _connection_scope(conn, db_path) as active_conn:
            cursor = active_conn.cursor()
            _validate_escalation_log(cursor, escalation.user_id, escalation.log_id)
            cursor.execute(
                """INSERT INTO escalations
                       (user_id, log_id, issue_summary,
                        escalation_reason, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (escalation.user_id, escalation.log_id, issue_summary,
                 escalation_reason, escalation.status,
                 created_at, created_at),
            )
            _record_audit_event(
                active_conn,
                AuditEventCreate(
                    event_type="escalation_created",
                    entity="escalations",
                    entity_id=cursor.lastrowid,
                    payload=f"user_id={escalation.user_id};status={escalation.status}",
                ),
            )
            return {
                "status": "success",
                "data": {"escalation_id": cursor.lastrowid},
                "message": "Escalation created successfully.",
            }
    except ValueError as e:
        return _handle_db_error(e)
    except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
        return _handle_db_error(e)


def get_escalations(user_id, db_path=None, limit=100, offset=0, after=None):
    """Return all escalation rows for *user_id*, newest first."""
    return get_user_records("escalations", user_id, limit, offset, after=after, db_path=db_path)
