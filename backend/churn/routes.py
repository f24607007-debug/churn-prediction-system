import os
import sqlite3
import traceback
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify

from .model import predict_churn_probability

churn_bp = Blueprint('churn_bp', __name__)

def get_db_path():
    db_uri = os.environ.get('DATABASE_URL', 'sqlite:///instance/churn_system.db')
    return db_uri.replace('sqlite:///', '')

def get_current_time():
    return datetime.now(timezone.utc).isoformat()

def format_response(status="success", data=None, message=""):
    return {
        "status": status,
        "data": data or {},
        "message": message
    }

def format_error(message: str):
    return {"error": message}

def _get_customer_behavior(user_id: int) -> dict:
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return {}
        
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT * FROM customer_behavior WHERE user_id = ? ORDER BY created_at DESC LIMIT 1''',
            (user_id,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
    return {}

def _insert_retention_action(user_id, churn_score, action_type, action_message):
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO retention_actions 
               (user_id, churn_score, action_type, action_message, created_at)
               VALUES (?, ?, ?, ?, ?)''',
            (user_id, churn_score, action_type, action_message, get_current_time())
        )
        return cursor.lastrowid

def _get_high_risk_customers():
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return []
        
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # Find latest retention actions indicating high risk
        cursor.execute(
            '''SELECT user_id, churn_score 
               FROM retention_actions 
               WHERE churn_score > 0.7 
               ORDER BY created_at DESC LIMIT 100'''
        )
        rows = cursor.fetchall()
        
        # Deduplicate to show only unique users
        seen = set()
        results = []
        for row in rows:
            uid = row['user_id']
            if uid not in seen:
                seen.add(uid)
                results.append({
                    "user_id": uid,
                    "churn_score": row['churn_score'],
                    "risk_level": "high"
                })
        return results

@churn_bp.route('/predict', methods=['POST'])
def handle_predict():
    try:
        req_data = request.get_json()
        if not req_data or 'user_id' not in req_data:
            return jsonify(format_error("Missing user_id")), 400
            
        user_id = int(req_data['user_id'])
        
        # Merge request features with database features
        db_features = _get_customer_behavior(user_id)
        features = {**db_features, **req_data}
        
        # Run inference
        churn_score = predict_churn_probability(features)
        
        risk_level = "high" if churn_score >= 0.70 else "low"
        retention_triggered = risk_level == "high"
        
        # Write to retention_actions
        action_type = "high_risk_alert" if retention_triggered else "routine_check"
        action_message = f"User scored {churn_score:.2f} probability of churn."
        _insert_retention_action(user_id, churn_score, action_type, action_message)
        
        contract_data = {
            "user_id": user_id,
            "churn_score": round(churn_score, 4),
            "risk_level": risk_level,
            "retention_triggered": retention_triggered
        }
        
        return jsonify(format_response(status="success", data=contract_data)), 200

    except ValueError:
        return jsonify(format_error("user_id must be an integer")), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify(format_error(str(e))), 500

@churn_bp.route('/report', methods=['GET'])
def handle_report():
    try:
        customers = _get_high_risk_customers()
        
        contract_data = {
            "high_risk_customers": customers,
            "generated_at": get_current_time()
        }
        
        return jsonify(format_response(status="success", data=contract_data)), 200
        
    except Exception as e:
        traceback.print_exc()
        return jsonify(format_error(str(e))), 500
