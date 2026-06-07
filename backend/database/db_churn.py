from __future__ import annotations

import sqlite3

from .db_audit import _record_audit_event
from .db_core import (
    AuditEventCreate,
    CustomerBehaviorCreate,
    MAX_TEXT_LEN,
    RetentionActionCreate,
    _coerce_payload,
    _coerce_timestamp_utc,
    _connection_scope,
    _handle_db_error,
    _normalize_text,
    _validate_max_length,
    _validate_non_empty_str,
    _validate_non_negative_int,
    _validate_positive_int,
    _validate_score,
    get_user_records,
)


# ---------------------------------------------------------------------------
# customer_behavior
# ---------------------------------------------------------------------------


def insert_customer_behavior(behavior=None, db_path=None, conn=None, **kwargs):
    """
    Write one behavior snapshot for a user.
    Called by the churn module after each prediction run.
    """
    try:
        behavior = _coerce_payload(behavior, CustomerBehaviorCreate, kwargs=kwargs)
        _validate_positive_int("user_id", behavior.user_id)
        _validate_non_negative_int("login_frequency", behavior.login_frequency)
        _validate_non_negative_int("purchase_frequency", behavior.purchase_frequency)
        _validate_non_negative_int("cart_abandonment_count", behavior.cart_abandonment_count)
        _validate_non_negative_int("refund_count", behavior.refund_count)
        _validate_non_negative_int("complaint_count", behavior.complaint_count)
        _validate_non_negative_int("inactivity_days", behavior.inactivity_days)
        _validate_score("churn_score", behavior.churn_score)
        _validate_non_empty_str("created_at", behavior.created_at)
        created_at = _coerce_timestamp_utc("created_at", behavior.created_at)
        with _connection_scope(conn, db_path) as active_conn:
            cursor = active_conn.cursor()
            cursor.execute(
                """INSERT INTO customer_behavior
                       (user_id, login_frequency, purchase_frequency,
                        cart_abandonment_count, refund_count, complaint_count,
                        inactivity_days, churn_score, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (behavior.user_id, behavior.login_frequency, behavior.purchase_frequency,
                 behavior.cart_abandonment_count, behavior.refund_count, behavior.complaint_count,
                 behavior.inactivity_days, behavior.churn_score, created_at),
            )
            _record_audit_event(
                active_conn,
                AuditEventCreate(
                    event_type="behavior_recorded",
                    entity="customer_behavior",
                    entity_id=cursor.lastrowid,
                    payload=f"user_id={behavior.user_id}",
                ),
            )
            return {
                "status": "success",
                "data": {"behavior_id": cursor.lastrowid},
                "message": "Customer behavior recorded.",
            }
    except ValueError as e:
        return _handle_db_error(e)
    except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
        return _handle_db_error(e)


def get_customer_behavior(user_id, db_path=None, limit=100, offset=0, after=None):
    """Return all behavior rows for *user_id*, newest first."""
    return get_user_records("customer_behavior", user_id, limit, offset, after=after, db_path=db_path)


# ---------------------------------------------------------------------------
# retention_actions
# ---------------------------------------------------------------------------


def log_retention_action(action=None, db_path=None, conn=None, **kwargs):
    """
    Record an automated retention action triggered by the churn module.
    Called by Member 3's pipeline after a high-risk prediction.
    """
    try:
        action = _coerce_payload(action, RetentionActionCreate, kwargs=kwargs)
        _validate_positive_int("user_id", action.user_id)
        _validate_score("churn_score", action.churn_score)
        action_type = _normalize_text(action.action_type)
        action_message = _normalize_text(action.action_message)
        _validate_non_empty_str("action_type", action_type)
        _validate_non_empty_str("action_message", action_message)
        _validate_max_length("action_type", action_type, MAX_TEXT_LEN)
        _validate_max_length("action_message", action_message, MAX_TEXT_LEN)
        _validate_non_empty_str("created_at", action.created_at)
        created_at = _coerce_timestamp_utc("created_at", action.created_at)
        with _connection_scope(conn, db_path) as active_conn:
            cursor = active_conn.cursor()
            cursor.execute(
                """INSERT INTO retention_actions
                       (user_id, churn_score, action_type,
                        action_message, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (action.user_id, action.churn_score, action_type,
                 action_message, created_at),
            )
            _record_audit_event(
                active_conn,
                AuditEventCreate(
                    event_type="retention_action_logged",
                    entity="retention_actions",
                    entity_id=cursor.lastrowid,
                    payload=f"user_id={action.user_id}",
                ),
            )
            return {
                "status": "success",
                "data": {"action_id": cursor.lastrowid},
                "message": "Retention action logged successfully.",
            }
    except ValueError as e:
        return _handle_db_error(e)
    except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
        return _handle_db_error(e)


def get_retention_actions(user_id, db_path=None, limit=100, offset=0, after=None):
    """
    Return all retention action rows for *user_id*, newest first.
    Used by the /api/churn/report endpoint.
    """
    return get_user_records("retention_actions", user_id, limit, offset, after=after, db_path=db_path)
