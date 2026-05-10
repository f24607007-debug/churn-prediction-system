import datetime
import os
import sys

# Add project root to sys.path so we can import from backend natively
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from backend.database.db import DB_PATH, get_connection, init_db, hash_password

def seed_data():
    # Remove existing database to prevent IntegrityError
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print(f"Removed existing database at {DB_PATH}")
        except Exception as e:
            print(f"Error removing existing database: {e}")
            return
            
    res = init_db()
    if res["status"] != "success":
        print("Failed to initialize DB:", res["message"])
        return
        
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    users_data = [
        ("Alice Smith", "alice@example.com", hash_password("pass123"), now, 10, 500.50),
        ("Bob Jones", "bob@example.com", hash_password("pass123"), now, 1, 20.00),
        ("Charlie Brown", "charlie@example.com", hash_password("pass123"), now, 0, 0.00),
        ("Diana Prince", "diana@example.com", hash_password("pass123"), now, 50, 3000.00),
        ("Eve Adams", "eve@example.com", hash_password("pass123"), now, 5, 100.00)
    ]
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany(
            '''INSERT INTO users (name, email, password_hash, join_date, total_orders, total_spent)
               VALUES (?, ?, ?, ?, ?, ?)''',
            users_data
        )
        
        # We need 10 behavior records. 
        # Critical Requirement: At least 3 rows have inactivity_days > 30 and high churn_score
        behavior_data = [
            (1, 1, 0, 2, 0, 1, 45, 0.95, now), # User 1: >30 inactivity, high score
            (2, 5, 2, 0, 0, 0, 2, 0.10, now),
            (3, 0, 0, 3, 1, 2, 60, 0.99, now), # User 3: >30 inactivity, high score
            (4, 20, 15, 0, 0, 0, 1, 0.05, now),
            (5, 2, 1, 1, 0, 1, 35, 0.85, now), # User 5: >30 inactivity, high score
            (1, 2, 0, 2, 0, 1, 46, 0.95, now), # User 1 
            (2, 6, 2, 0, 0, 0, 3, 0.10, now),
            (3, 0, 0, 3, 1, 2, 61, 0.99, now), # User 3
            (4, 21, 16, 0, 0, 0, 2, 0.05, now),
            (5, 3, 1, 1, 0, 1, 36, 0.85, now), # User 5
        ]
        
        cursor.executemany(
            '''INSERT INTO customer_behavior (user_id, login_frequency, purchase_frequency, cart_abandonment_count, refund_count, complaint_count, inactivity_days, churn_score, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            behavior_data
        )

if __name__ == "__main__":
    seed_data()
    print("Database seeded successfully with 5 users and 10 behavior rows.")
