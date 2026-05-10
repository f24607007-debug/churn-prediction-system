import os
import sqlite3
import traceback
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify

from .services.nlp_engine import run_inference
from .services.escalation import should_escalate, get_escalation_message
from .services.faq_matcher import get_response_for_intent

chatbot_bp = Blueprint('chatbot_bp', __name__)

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

def _insert_log(user_id, query, intent, response_text, confidence, escalated):
    """Raw SQLite insert for chatbot logs."""
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO chatbot_logs 
               (user_id, user_query, detected_intent, chatbot_response, confidence_score, escalated, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (user_id, query, intent, response_text, confidence, 1 if escalated else 0, get_current_time())
        )
        return cursor.lastrowid

def _insert_escalation(user_id, log_id, query, reason):
    """Raw SQLite insert for escalations."""
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO escalations 
               (user_id, log_id, issue_summary, escalation_reason, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (user_id, log_id, query, reason, 'escalated', get_current_time())
        )
        return cursor.lastrowid

@chatbot_bp.route('/ask', methods=['POST'])
def handle_ask():
    try:
        req_data = request.get_json()
        if not req_data or 'user_id' not in req_data or 'query' not in req_data:
            return jsonify(format_error("Missing user_id or query")), 400
            
        user_id = int(req_data['user_id'])
        query = req_data['query']
        
        # 1. Inference
        nlp_result = run_inference(query)
        confidence = nlp_result['confidence']
        intent = nlp_result['intent']
        
        # 2. Escalation check
        escalated = should_escalate(confidence)
        
        # 3. Lookup Response
        if escalated:
            response_text = get_escalation_message()
        else:
            response_text = get_response_for_intent(intent)
            
        # 4. Save to DB
        log_id = _insert_log(user_id, query, intent, response_text, confidence, escalated)
        
        contract_data = {
            "intent": intent,
            "confidence": confidence,
            "response": response_text,
            "escalated": escalated
        }
        
        # 5. Auto-escalate in DB if needed
        if escalated:
            ticket_id = _insert_escalation(user_id, log_id, query, f"Low confidence: {confidence}")
            contract_data["escalation_ticket_id"] = ticket_id

        return jsonify(format_response(status="success", data=contract_data)), 200

    except ValueError:
        return jsonify(format_error("user_id must be an integer")), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify(format_error(str(e))), 500

@chatbot_bp.route('/escalate', methods=['POST'])
def handle_escalate():
    try:
        req_data = request.get_json()
        if not req_data or 'user_id' not in req_data or 'query' not in req_data:
            return jsonify(format_error("Missing user_id or query")), 400
            
        user_id = int(req_data['user_id'])
        query = req_data['query']
        confidence = req_data.get('confidence', 0.0)
        
        ticket_id = _insert_escalation(user_id, None, query, f"Manual escalation via API. Confidence: {confidence}")
        
        contract_data = {
            "ticket_id": ticket_id,
            "status": "escalated",
            "message": "Agent will contact you shortly."
        }
        
        return jsonify(format_response(status="success", data=contract_data)), 200
        
    except ValueError:
        return jsonify(format_error("user_id must be an integer")), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify(format_error(str(e))), 500

@chatbot_bp.route('/log', methods=['POST'])
def handle_log():
    try:
        req_data = request.get_json()
        if not req_data or 'user_id' not in req_data or 'query' not in req_data:
            return jsonify(format_error("Missing required fields")), 400
            
        user_id = int(req_data['user_id'])
        
        log_id = _insert_log(
            user_id=user_id,
            query=req_data['query'],
            intent=req_data.get('intent', 'unknown'),
            response_text=req_data.get('response', ''),
            confidence=req_data.get('confidence', 0.0),
            escalated=req_data.get('escalated', False)
        )
        
        contract_data = {
            "log_id": log_id,
            "status": "saved"
        }
        
        return jsonify(format_response(status="success", data=contract_data)), 200
        
    except ValueError:
        return jsonify(format_error("user_id must be an integer")), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify(format_error(str(e))), 500
