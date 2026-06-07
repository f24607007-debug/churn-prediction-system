-- =============================================================
-- Churn Prediction System — Database Schema
-- =============================================================
-- Convention : all timestamps stored as ISO-8601 UTC strings
--              e.g. datetime.now(timezone.utc).isoformat()
-- =============================================================

-- -------------------------------------------------------------
-- 1. users
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL,
    email          TEXT    UNIQUE NOT NULL COLLATE NOCASE,
    password_hash  TEXT    NOT NULL,
    join_date      TEXT    NOT NULL,
    total_orders   INTEGER NOT NULL DEFAULT 0 CHECK(total_orders   >= 0),
    total_spent    REAL    NOT NULL DEFAULT 0.0 CHECK(total_spent  >= 0.0)
);

-- -------------------------------------------------------------
-- 2. customer_behavior
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customer_behavior (
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

-- -------------------------------------------------------------
-- 3. chatbot_logs
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chatbot_logs (
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

-- -------------------------------------------------------------
-- 4. escalations
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS escalations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL,
    log_id            INTEGER, -- Nullable for manual escalations without a chatbot log
    issue_summary     TEXT    NOT NULL,
    escalation_reason TEXT    NOT NULL,
    status            TEXT    NOT NULL DEFAULT 'open'
                          CHECK(status IN ('open', 'in_progress', 'resolved')),
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(log_id)  REFERENCES chatbot_logs(id) ON DELETE SET NULL
);

-- -------------------------------------------------------------
-- 5. retention_actions
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS retention_actions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    churn_score    REAL    NOT NULL CHECK(churn_score >= 0.0 AND churn_score <= 1.0),
    action_type    TEXT    NOT NULL,
    action_message TEXT    NOT NULL,
    created_at     TEXT    NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- -------------------------------------------------------------
-- 6. audit_log
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT    NOT NULL,
    entity     TEXT    NOT NULL,
    entity_id  INTEGER,
    payload    TEXT,
    created_at TEXT    NOT NULL
);

-- =============================================================
-- Indexes — added for every high-traffic FK / lookup column
-- =============================================================
CREATE INDEX IF NOT EXISTS idx_users_email
    ON users(email);

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

CREATE INDEX IF NOT EXISTS idx_escalations_user_id_created_at
    ON escalations(user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_escalations_log_id
    ON escalations(log_id);

CREATE INDEX IF NOT EXISTS idx_retention_user_id
    ON retention_actions(user_id);

CREATE INDEX IF NOT EXISTS idx_retention_user_id_created_at
    ON retention_actions(user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_audit_log_entity
    ON audit_log(entity, entity_id);
