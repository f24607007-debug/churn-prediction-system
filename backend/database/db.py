from __future__ import annotations

"""
backend/database/db.py
======================
Facade module that re-exports database APIs from split submodules.
"""

from .db_audit import log_audit_event
from .db_chatbot import add_chatbot_log, get_chatbot_logs, get_escalations, insert_escalation
from .db_churn import (
    get_customer_behavior,
    get_retention_actions,
    insert_customer_behavior,
    log_retention_action,
)
from .db_core import (
    AuditEventCreate,
    ChatbotLogCreate,
    CustomerBehaviorCreate,
    DB_DIR,
    DB_PATH,
    DESTRUCTIVE_MIGRATIONS,
    EscalationCreate,
    MAX_EMAIL_LEN,
    MAX_NAME_LEN,
    MAX_PAGE_SIZE,
    MAX_SUMMARY_LEN,
    MAX_TEXT_LEN,
    MIGRATIONS,
    RetentionActionCreate,
    SCHEMA_PATH,
    UserCreate,
    UserPageRequest,
    UserQuery,
    apply_destructive_migrations,
    apply_migrations,
    get_connection,
    get_user_records,
    init_db,
    transaction,
)
from .db_users import get_user_by_email, get_user_by_id, hash_password, insert_user, verify_password

__all__ = [
    "AuditEventCreate",
    "ChatbotLogCreate",
    "CustomerBehaviorCreate",
    "DB_DIR",
    "DB_PATH",
    "DESTRUCTIVE_MIGRATIONS",
    "EscalationCreate",
    "MAX_EMAIL_LEN",
    "MAX_NAME_LEN",
    "MAX_PAGE_SIZE",
    "MAX_SUMMARY_LEN",
    "MAX_TEXT_LEN",
    "MIGRATIONS",
    "RetentionActionCreate",
    "SCHEMA_PATH",
    "UserCreate",
    "UserPageRequest",
    "UserQuery",
    "add_chatbot_log",
    "apply_destructive_migrations",
    "apply_migrations",
    "get_chatbot_logs",
    "get_connection",
    "get_customer_behavior",
    "get_escalations",
    "get_retention_actions",
    "get_user_by_email",
    "get_user_by_id",
    "get_user_records",
    "hash_password",
    "init_db",
    "insert_customer_behavior",
    "insert_escalation",
    "insert_user",
    "log_audit_event",
    "log_retention_action",
    "transaction",
    "verify_password",
]
