import os
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from models import db, ChatbotLogs, Escalations
from nlp_service import analyze_intent

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configure database
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///chatbot.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Ensure tables are created
with app.app_context():
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']
    if db_uri.startswith('sqlite:///'):
        db_path = db_uri.replace('sqlite:///', '')
        if os.path.dirname(db_path):
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db.create_all()

def format_response(status="success", data=None, message=""):
    """Helper to format all responses according to coding standards."""
    return {
        "status": status,
        "data": data or {},
        "message": message
    }

def format_error(message: str):
    """Helper to format error responses."""
    return {"error": message}

@app.errorhandler(500)
def internal_error(exception):
    return jsonify(format_error("Internal server error occurred.")), 500

@app.errorhandler(400)
def bad_request_error(exception):
    return jsonify(format_error("Bad request.")), 400

@app.route('/ask', methods=['POST'])
def handle_ask():
    try:
        req_data = request.get_json()
        if not req_data or 'user_id' not in req_data or 'query' not in req_data:
            return jsonify(format_error("Missing user_id or query")), 400
            
        user_id = int(req_data['user_id'])
        query = req_data['query']
        
        # Analyze intent using distilBERT
        nlp_result = analyze_intent(query)
        confidence = nlp_result['confidence']
        intent = nlp_result['intent']
        response_text = nlp_result['response']
        escalated = nlp_result['escalated']
        
        # Determine strict threshold
        # If < 0.75, it's escalated, but we still handle it in /ask and optionally call /escalate logic
        
        log_entry = ChatbotLogs(
            user_id=user_id,
            user_query=query,
            detected_intent=intent,
            chatbot_response=response_text,
            confidence_score=confidence,
            escalated=escalated
        )
        db.session.add(log_entry)
        db.session.commit()
        
        # Contract-specific response inside 'data'
        contract_data = {
            "intent": intent,
            "confidence": confidence,
            "response": response_text,
            "escalated": escalated
        }
        
        # Auto-trigger escalation logic internally if threshold not met
        if escalated:
            # Create an escalation record directly as per system design
            escalation_entry = Escalations(
                user_id=user_id,
                log_id=log_entry.id,
                issue_summary=query,
                escalation_reason=f"Low confidence score: {confidence}"
            )
            db.session.add(escalation_entry)
            db.session.commit()
            
            contract_data["escalation_ticket_id"] = escalation_entry.id
            contract_data["response"] = "I am not sure. I have created a ticket for a human agent."

        return jsonify(format_response(status="success", data=contract_data)), 200

    except ValueError:
        return jsonify(format_error("user_id must be an integer")), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify(format_error(str(e))), 500

@app.route('/escalate', methods=['POST'])
def handle_escalate():
    try:
        req_data = request.get_json()
        if not req_data or 'user_id' not in req_data or 'query' not in req_data:
            return jsonify(format_error("Missing user_id or query")), 400
            
        user_id = int(req_data['user_id'])
        query = req_data['query']
        confidence = req_data.get('confidence', 0.0)
        
        escalation_entry = Escalations(
            user_id=user_id,
            issue_summary=query,
            escalation_reason=f"Manual escalation via /escalate API. Confidence: {confidence}"
        )
        db.session.add(escalation_entry)
        db.session.commit()
        
        contract_data = {
            "ticket_id": escalation_entry.id,
            "status": "escalated",
            "message": "Agent will contact you shortly."
        }
        
        return jsonify(format_response(status="success", data=contract_data)), 200
        
    except ValueError:
        return jsonify(format_error("user_id must be an integer")), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify(format_error(str(e))), 500

@app.route('/log', methods=['POST'])
def handle_log():
    try:
        req_data = request.get_json()
        if not req_data or 'user_id' not in req_data or 'query' not in req_data:
            return jsonify(format_error("Missing required fields")), 400
            
        user_id = int(req_data['user_id'])
        
        log_entry = ChatbotLogs(
            user_id=user_id,
            user_query=req_data['query'],
            detected_intent=req_data.get('intent', 'unknown'),
            chatbot_response=req_data.get('response', ''),
            confidence_score=req_data.get('confidence', 0.0),
            escalated=req_data.get('escalated', False)
        )
        db.session.add(log_entry)
        db.session.commit()
        
        contract_data = {
            "log_id": log_entry.id,
            "status": "saved"
        }
        
        return jsonify(format_response(status="success", data=contract_data)), 200
        
    except ValueError:
        return jsonify(format_error("user_id must be an integer")), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify(format_error(str(e))), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
