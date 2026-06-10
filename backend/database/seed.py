"""
backend/database/seed.py
========================
Development-only seed script.

Usage:
    APP_ENV=development python backend/database/seed.py

WARNING: This script DROPS and recreates the database.
         It will refuse to run unless APP_ENV=development is set.
"""

import datetime
import os
import sys

# ---------------------------------------------------------------------------
# Safety guard — must be explicitly running in development
# ---------------------------------------------------------------------------
from dotenv import load_dotenv
load_dotenv()

if os.getenv("APP_ENV") != "development":
    print("ERROR: Seed script refused to run.")
    print("       Set APP_ENV=development to allow seeding.")
    print("       Example:  APP_ENV=development python backend/database/seed.py")
    sys.exit(1)

# Add project root so we can import backend package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.database.db import (
    DB_PATH, get_connection, init_db, hash_password
)


def _seed_users(cursor, base_now):
    users_data = [
        ("Alice Smith",   "alice@example.com",   hash_password("pass1234"), (base_now - datetime.timedelta(days=120)).isoformat(), 10,  500.50),
        ("Bob Jones",     "bob@example.com",     hash_password("pass1234"), (base_now - datetime.timedelta(days=90)).isoformat(),  1,   20.00),
        ("Charlie Brown", "charlie@example.com", hash_password("pass1234"), (base_now - datetime.timedelta(days=75)).isoformat(),  0,    0.00),
        ("Diana Prince",  "diana@example.com",   hash_password("pass1234"), (base_now - datetime.timedelta(days=45)).isoformat(), 50, 3000.00),
        ("Eve Adams",     "eve@example.com",     hash_password("pass1234"), (base_now - datetime.timedelta(days=30)).isoformat(),  5,  100.00),
    ]
    cursor.executemany(
        '''INSERT INTO users
               (name, email, password_hash, join_date, total_orders, total_spent)
           VALUES (?, ?, ?, ?, ?, ?)''',
        users_data
    )
    print("[seed] Inserted 5 users.")


def _seed_customer_behavior(cursor, base_now):
    behavior_data = [
        (1,  1,  0, 2, 0, 1, 45, 0.95, (base_now - datetime.timedelta(days=60)).isoformat()),  # high risk — >30 days inactive
        (2,  5,  2, 0, 0, 0,  2, 0.10, (base_now - datetime.timedelta(days=14)).isoformat()),  # healthy
        (3,  0,  0, 3, 1, 2, 60, 0.99, (base_now - datetime.timedelta(days=75)).isoformat()),  # high risk — >30 days inactive
        (4, 20, 15, 0, 0, 0,  1, 0.05, (base_now - datetime.timedelta(days=10)).isoformat()),  # very healthy
        (5,  2,  1, 1, 0, 1, 35, 0.85, (base_now - datetime.timedelta(days=40)).isoformat()),  # high risk — >30 days inactive
        (1,  2,  0, 2, 0, 1, 46, 0.95, (base_now - datetime.timedelta(days=30)).isoformat()),  # Alice second snapshot
        (2,  6,  2, 0, 0, 0,  3, 0.10, (base_now - datetime.timedelta(days=7)).isoformat()),
        (3,  0,  0, 3, 1, 2, 61, 0.99, (base_now - datetime.timedelta(days=45)).isoformat()),  # Charlie second snapshot
        (4, 21, 16, 0, 0, 0,  2, 0.05, (base_now - datetime.timedelta(days=3)).isoformat()),
        (5,  3,  1, 1, 0, 1, 36, 0.85, (base_now - datetime.timedelta(days=25)).isoformat()),  # Eve second snapshot
    ]
    cursor.executemany(
        '''INSERT INTO customer_behavior
               (user_id, login_frequency, purchase_frequency,
                cart_abandonment_count, refund_count, complaint_count,
                inactivity_days, churn_score, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        behavior_data
    )
    print("[seed] Inserted 10 customer_behavior rows.")


def _seed_chatbot_logs(cursor, base_now):
    chatbot_data = [
        (1, "Where is my order?",
         "order_status", "Your order is on the way!", 0.92, 0, (base_now - datetime.timedelta(days=12)).isoformat()),
        (2, "I want a refund",
         "refund_request", "I have raised a refund request.", 0.88, 0, (base_now - datetime.timedelta(days=8)).isoformat()),
        (3, "This product is broken and I am very unhappy",
         "complaint", "I'm sorry to hear that, let me escalate.", 0.55, 1, (base_now - datetime.timedelta(days=6)).isoformat()),
        (4, "What are your working hours?",
         "general_inquiry", "We are available 9am-6pm Mon-Fri.", 0.95, 0, (base_now - datetime.timedelta(days=4)).isoformat()),
        (5, "Cancel my subscription immediately",
         "cancellation", "Let me connect you to a specialist.", 0.60, 1, (base_now - datetime.timedelta(days=2)).isoformat()),
    ]
    escalated_logs_by_user = {}
    for row in chatbot_data:
        cursor.execute(
            '''INSERT INTO chatbot_logs
                   (user_id, user_query, detected_intent, chatbot_response,
                    confidence_score, escalated, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            row
        )
        if row[5] == 1:
            escalated_logs_by_user[row[0]] = cursor.lastrowid
    print("[seed] Inserted 5 chatbot_logs rows.")
    return escalated_logs_by_user


def _seed_escalations(cursor, base_now, escalated_logs_by_user):
    escalation_data = [
        (3, escalated_logs_by_user.get(3), "Customer reported broken product",
         "Confidence below threshold (0.55)", "open",
         (base_now - datetime.timedelta(days=5)).isoformat(),
         (base_now - datetime.timedelta(days=5)).isoformat()),
        (5, escalated_logs_by_user.get(5), "Customer requesting immediate cancellation",
         "Confidence below threshold (0.60)", "in_progress",
         (base_now - datetime.timedelta(days=1)).isoformat(),
         (base_now - datetime.timedelta(days=1)).isoformat()),
        (1, None, "Follow-up on delayed order",
         "Customer marked high-risk churn score", "resolved",
         (base_now - datetime.timedelta(days=3)).isoformat(),
         (base_now - datetime.timedelta(days=3)).isoformat()),
    ]
    cursor.executemany(
        '''INSERT INTO escalations
               (user_id, log_id, issue_summary,
                escalation_reason, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        escalation_data
    )
    print("[seed] Inserted 3 escalations rows.")


def _seed_retention_actions(cursor, base_now):
    retention_data = [
        (1, 0.95, "discount_offer",
         "Exclusive 20% discount on your next order - we miss you!", (base_now - datetime.timedelta(days=20)).isoformat()),
        (3, 0.99, "personal_outreach",
         "A customer success agent will contact you within 24 hours.", (base_now - datetime.timedelta(days=18)).isoformat()),
        (5, 0.85, "discount_offer",
         "Here is a special 15% loyalty discount just for you.", (base_now - datetime.timedelta(days=16)).isoformat()),
        (1, 0.95, "loyalty_reward",
         "You have been enrolled in our VIP rewards programme.", (base_now - datetime.timedelta(days=12)).isoformat()),
    ]
    cursor.executemany(
        '''INSERT INTO retention_actions
               (user_id, churn_score, action_type,
                action_message, created_at)
           VALUES (?, ?, ?, ?, ?)''',
        retention_data
    )
    print("[seed] Inserted 4 retention_actions rows.")


from backend.database.db_core import _resolve_db_path

def seed_data():
    # -----------------------------------------------------------------------
    # Drop existing dev DB so seed is always reproducible
    # -----------------------------------------------------------------------
    actual_db_path = _resolve_db_path()
    if os.path.exists(actual_db_path):
        try:
            os.remove(actual_db_path)
            print(f"[seed] Removed existing database at {actual_db_path}")
        except Exception as e:
            print(f"[seed] ERROR removing database: {e}")
            return

    res = init_db()
    if res["status"] != "success":
        print("[seed] ERROR — could not initialise DB:", res["message"])
        return

    base_now = datetime.datetime.now(datetime.timezone.utc)

    with get_connection() as conn:
        cursor = conn.cursor()
        _seed_users(cursor, base_now)
        _seed_customer_behavior(cursor, base_now)
        escalated_logs_by_user = _seed_chatbot_logs(cursor, base_now)
        _seed_escalations(cursor, base_now, escalated_logs_by_user)
        _seed_retention_actions(cursor, base_now)


if __name__ == "__main__":
    seed_data()
    from backend.database.db_core import _resolve_db_path
    print("\n[seed] Database seeded successfully.")
    print(f"[seed] DB location: {_resolve_db_path()}")
