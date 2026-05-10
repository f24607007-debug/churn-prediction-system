CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    join_date TEXT NOT NULL,
    total_orders INTEGER DEFAULT 0,
    total_spent REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS customer_behavior (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    login_frequency INTEGER DEFAULT 0,
    purchase_frequency INTEGER DEFAULT 0,
    cart_abandonment_count INTEGER DEFAULT 0,
    refund_count INTEGER DEFAULT 0,
    complaint_count INTEGER DEFAULT 0,
    inactivity_days INTEGER DEFAULT 0,
    churn_score REAL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS chatbot_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    user_query TEXT NOT NULL,
    detected_intent TEXT,
    chatbot_response TEXT,
    confidence_score REAL,
    escalated INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS escalations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    log_id INTEGER,
    issue_summary TEXT NOT NULL,
    escalation_reason TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(log_id) REFERENCES chatbot_logs(id)
);

CREATE TABLE IF NOT EXISTS retention_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    churn_score REAL,
    action_type TEXT NOT NULL,
    action_message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
