from __future__ import annotations

import datetime
from flask import Blueprint, current_app, request, jsonify

from .services.nlp_engine import run_inference, init_model, is_model_loaded
from .services.escalation import should_escalate, get_escalation_message
from .services.faq_matcher import get_response_for_intent

from backend.database.db import (
    add_chatbot_log,
    insert_escalation,
    ChatbotLogCreate,
    EscalationCreate,
    get_connection,
    get_user_by_id,
    log_audit_event,
    AuditEventCreate,
    MAX_SUMMARY_LEN,
)
from backend.utils.validators import validate_user_id, validate_query, validate_confidence
from backend.utils.logger import get_logger
from backend.utils.helpers import build_response

logger = get_logger(__name__)
chatbot_bp = Blueprint('chatbot_bp', __name__)


def _now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _get_db_path():
    return current_app.config.get("DATABASE_URL") or None


def _user_exists(user_id: int) -> tuple[bool, bool]:
    """Check that a user exists.

    Returns (exists, db_error):
      (True,  False) → user found
      (False, False) → user not found (genuine 404)
      (False, True)  → DB unreachable (caller should return 503, not 400)
    """
    result = get_user_by_id(user_id, db_path=_get_db_path())
    if result["status"] == "success":
        return True, False
    # Distinguish "not found" from "db error" by message content
    msg = result.get("message", "").lower()
    db_error = "not found" not in msg
    return False, db_error


def _verify_db_connection() -> bool:
    """Return True if the database is reachable."""
    db_path = _get_db_path()
    try:
        with get_connection(db_path) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def _rollback_chatbot_log(log_id: int) -> None:
    """
    Delete the chatbot_log row created during a failed /ask transaction,
    but preserve the audit trail — mark it as ROLLBACK instead of erasing it.
    The audit entry in audit_log stays so production incidents are traceable.
    """
    db_path = _get_db_path()
    try:
        with get_connection(db_path) as conn:
            conn.execute("DELETE FROM chatbot_logs WHERE id = ?", (log_id,))
            # Record the rollback in the audit trail — do NOT delete the original audit row
            log_audit_event(
                AuditEventCreate(
                    event_type="chatbot_log_rolled_back",
                    entity="chatbot_logs",
                    entity_id=log_id,
                    payload="escalation insert failed; chatbot_log deleted, audit trail preserved",
                    created_at=_now_utc(),
                ),
                conn=conn,
            )
    except Exception:
        logger.exception("Failed to rollback chatbot log %s", log_id)


def format_response(status="success", data=None, message=""):
    return build_response(status=status, data=data, message=message)


def format_error(message: str):
    return build_response(status="error", data={}, message=message)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

@chatbot_bp.route('/health', methods=['GET'])
def handle_health():
    try:
        db_reachable = _verify_db_connection()
        nlp_loaded = is_model_loaded()

        # FIX: The endpoint is healthy as long as the DB is reachable.
        # NLP lazy-loads on the first /ask request, so nlp_loaded=False is normal on boot.
        status = "success" if db_reachable else "error"
        code = 200 if db_reachable else 503
        
        return jsonify(format_response(
            status=status,
            data={"nlp_loaded": nlp_loaded, "db_reachable": db_reachable},
            message="Chatbot service health check.",
        )), code
    except Exception:
        logger.exception("Health check failed")
        return jsonify(format_error("Health check failed")), 500


# ---------------------------------------------------------------------------
# /ask
# ---------------------------------------------------------------------------

@chatbot_bp.route('/ask', methods=['POST'])
def handle_ask():
    try:
        req_data = request.get_json(silent=True)
        if not isinstance(req_data, dict):
            return jsonify(format_error("Request body must be JSON")), 400

        valid_user, user_error = validate_user_id(req_data.get('user_id'))
        if not valid_user:
            return jsonify(format_error(user_error)), 400

        valid_query, query_error = validate_query(req_data.get('query'))
        if not valid_query:
            return jsonify(format_error(query_error)), 400

        user_id = int(req_data['user_id'])
        query = req_data['query'].strip()

        _exists, _db_err = _user_exists(user_id)
        if _db_err:
            return jsonify(format_error("Service temporarily unavailable")), 503
        if not _exists:
            return jsonify(format_error(f"User with id {user_id} does not exist")), 404

        try:
            nlp_result = run_inference(query)
        except RuntimeError:
            logger.exception("NLP engine unavailable")
            return jsonify(format_error("NLP engine is temporarily unavailable.")), 503
        except Exception:
            logger.exception("NLP inference failed")
            return jsonify(format_error("NLP engine failed to process query")), 500

        confidence = float(nlp_result['confidence'])
        intent = str(nlp_result['intent'])
        threshold = current_app.config.get("CONFIDENCE_THRESHOLD", 0.75)
        escalated = should_escalate(confidence, threshold)

        response_text = get_escalation_message() if escalated else get_response_for_intent(intent)

        log_create = ChatbotLogCreate(
            user_id=user_id,
            user_query=query,
            detected_intent=intent,
            chatbot_response=response_text,
            confidence_score=confidence,
            escalated=1 if escalated else 0,
            created_at=_now_utc(),
        )
        log_result = add_chatbot_log(log_create, db_path=_get_db_path())
        if log_result["status"] != "success":
            logger.error("add_chatbot_log failed: %s", log_result["message"])
            return jsonify(format_error("Failed to record chatbot interaction")), 500

        log_id = log_result["data"]["log_id"]

        contract_data = {
            "intent": intent,
            "confidence": confidence,
            "response": response_text,
            "escalated": escalated,
        }

        if escalated:
            esc_create = EscalationCreate(
                user_id=user_id,
                log_id=log_id,
                issue_summary=query[:MAX_SUMMARY_LEN],
                escalation_reason=f"Low confidence: {confidence}",
                created_at=_now_utc(),
            )
            esc_result = insert_escalation(esc_create, db_path=_get_db_path())
            if esc_result["status"] != "success":
                _rollback_chatbot_log(log_id)
                logger.error("insert_escalation failed: %s", esc_result["message"])
                return jsonify(format_error("An internal error occurred")), 500

            contract_data["ticket_id"] = esc_result["data"]["escalation_id"]

        return jsonify(format_response(status="success", data=contract_data)), 200

    except Exception:
        logger.exception("Error handling /ask request")
        return jsonify(format_error("An internal error occurred")), 500


# ---------------------------------------------------------------------------
# /escalate
# ---------------------------------------------------------------------------

@chatbot_bp.route('/escalate', methods=['POST'])
def handle_escalate():
    try:
        req_data = request.get_json(silent=True)
        if not isinstance(req_data, dict):
            return jsonify(format_error("Request body must be JSON")), 400

        valid_user, user_error = validate_user_id(req_data.get('user_id'))
        if not valid_user:
            return jsonify(format_error(user_error)), 400

        valid_query, query_error = validate_query(req_data.get('query'))
        if not valid_query:
            return jsonify(format_error(query_error)), 400

        valid_conf, conf_error = validate_confidence(req_data.get('confidence'))
        if not valid_conf:
            return jsonify(format_error(conf_error)), 400

        user_id = int(req_data['user_id'])
        query = req_data['query'].strip()
        confidence = float(req_data['confidence'])

        _exists, _db_err = _user_exists(user_id)
        if _db_err:
            return jsonify(format_error("Service temporarily unavailable")), 503
        if not _exists:
            return jsonify(format_error(f"User with id {user_id} does not exist")), 404

        esc_create = EscalationCreate(
            user_id=user_id,
            log_id=None,
            issue_summary=query[:MAX_SUMMARY_LEN],
            escalation_reason=f"Manual escalation via API. Confidence: {confidence}",
            created_at=_now_utc(),
        )
        esc_result = insert_escalation(esc_create, db_path=_get_db_path())
        if esc_result["status"] != "success":
            logger.error("insert_escalation failed: %s", esc_result["message"])
            return jsonify(format_error("An internal error occurred")), 500

        contract_data = {
            "ticket_id": esc_result["data"]["escalation_id"],
            "status": "open",
            "message": "Agent will contact you shortly.",
        }
        return jsonify(format_response(status="success", data=contract_data)), 200

    except Exception:
        logger.exception("Error handling /escalate request")
        return jsonify(format_error("An internal error occurred")), 500


# ---------------------------------------------------------------------------
# /log
# ---------------------------------------------------------------------------

@chatbot_bp.route('/log', methods=['POST'])
def handle_log():
    try:
        req_data = request.get_json(silent=True)
        if not isinstance(req_data, dict):
            return jsonify(format_error("Request body must be JSON")), 400

        required_fields = ('user_id', 'query', 'intent', 'response', 'confidence', 'escalated')
        missing_fields = [f for f in required_fields if f not in req_data]
        if missing_fields:
            return jsonify(format_error(f"Missing required fields: {', '.join(missing_fields)}")), 400

        valid_user, user_error = validate_user_id(req_data.get('user_id'))
        if not valid_user:
            return jsonify(format_error(user_error)), 400

        valid_query, query_error = validate_query(req_data.get('query'))
        if not valid_query:
            return jsonify(format_error(query_error)), 400

        valid_conf, conf_error = validate_confidence(req_data.get('confidence'))
        if not valid_conf:
            return jsonify(format_error(conf_error)), 400

        if not isinstance(req_data.get('escalated'), bool):
            return jsonify(format_error("escalated must be a boolean.")), 400

        user_id = int(req_data['user_id'])
        query = req_data['query'].strip()
        intent = str(req_data['intent']).strip()
        response_text = str(req_data['response']).strip()
        confidence = float(req_data['confidence'])
        escalated = req_data['escalated']

        _exists, _db_err = _user_exists(user_id)
        if _db_err:
            return jsonify(format_error("Service temporarily unavailable")), 503
        if not _exists:
            return jsonify(format_error(f"User with id {user_id} does not exist")), 404

        log_create = ChatbotLogCreate(
            user_id=user_id,
            user_query=query,
            detected_intent=intent,
            chatbot_response=response_text,
            confidence_score=confidence,
            escalated=1 if escalated else 0,
            created_at=_now_utc(),
        )
        log_result = add_chatbot_log(log_create, db_path=_get_db_path())
        if log_result["status"] != "success":
            logger.error("add_chatbot_log failed: %s", log_result["message"])
            return jsonify(format_error("Failed to save chatbot log")), 500

        contract_data = {
            "log_id": log_result["data"]["log_id"],
            "status": "saved",
        }
        return jsonify(format_response(status="success", data=contract_data)), 200

    except Exception:
        logger.exception("Error handling /log request")
        return jsonify(format_error("An internal error occurred")), 500
