from __future__ import annotations

import datetime
from flask import Blueprint, current_app, request, jsonify

from .model import predict_churn

from backend.database.db import (
    CustomerBehaviorCreate,
    RetentionActionCreate,
    insert_customer_behavior,
    get_customer_behavior,
    log_retention_action,
    get_retention_actions,
    get_user_by_id,
)
from backend.utils.validators import validate_user_id
from backend.utils.logger import get_logger
from backend.utils.helpers import build_response

logger = get_logger(__name__)
churn_bp = Blueprint('churn_bp', __name__)


def _now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _get_db_path():
    return current_app.config.get("DATABASE_URL") or None


def format_response(status="success", data=None, message=""):
    return build_response(status=status, data=data, message=message)


def format_error(message: str):
    return build_response(status="error", data={}, message=message)


def get_risk_level(churn_score: float) -> str:
    if churn_score >= 0.75:
        return "high"
    elif churn_score >= 0.50:
        return "medium"
    else:
        return "low"


def get_action_type(churn_score: float) -> str:
    if churn_score >= 0.85:
        return "personal_outreach"
    elif churn_score >= 0.70:
        return "discount_offer"
    else:
        return "loyalty_reward"


# ---------------------------------------------------------------------------
# POST /api/churn/predict
# ---------------------------------------------------------------------------

@churn_bp.route('/predict', methods=['POST'])
def handle_predict():
    try:
        req_data = request.get_json(silent=True)
        if not isinstance(req_data, dict):
            return jsonify(format_error("Request body must be JSON")), 400

        valid_user, user_error = validate_user_id(req_data.get('user_id'))
        if not valid_user:
            return jsonify(format_error(user_error)), 400

        user_id = int(req_data['user_id'])
        db_path = _get_db_path()

        # Step 1 — verify user exists
        user_result = get_user_by_id(user_id, db_path=db_path)
        if user_result["status"] != "success":
            msg = user_result.get("message", "").lower()
            if "not found" in msg:
                return jsonify(format_error(f"User {user_id} not found")), 404
            return jsonify(format_error("Service temporarily unavailable")), 503

        # Step 2 — fetch latest behavior row
        behavior_result = get_customer_behavior(user_id, db_path=db_path, limit=1)
        if behavior_result["status"] != "success":
            return jsonify(format_error("Failed to fetch customer behavior")), 500

        behavior_rows = behavior_result["data"].get("behavior", [])
        if not behavior_rows:
            return jsonify(format_error(f"No behavior data found for user {user_id}")), 404

        latest_behavior = behavior_rows[0]

        # Step 3 — run prediction
        try:
            churn_score = predict_churn(latest_behavior)
        except FileNotFoundError as e:
            logger.error("Model file missing: %s", e)
            return jsonify(format_error("Churn model not available. Run train.py first.")), 500

        risk_level = get_risk_level(churn_score)
        action_type = get_action_type(churn_score)

        # Step 4 — save updated behavior snapshot with new churn_score
        behavior_create = CustomerBehaviorCreate(
            user_id=user_id,
            login_frequency=latest_behavior.get('login_frequency', 0),
            purchase_frequency=latest_behavior.get('purchase_frequency', 0),
            cart_abandonment_count=latest_behavior.get('cart_abandonment_count', 0),
            refund_count=latest_behavior.get('refund_count', 0),
            complaint_count=latest_behavior.get('complaint_count', 0),
            inactivity_days=latest_behavior.get('inactivity_days', 0),
            churn_score=churn_score,
            created_at=_now_utc(),
        )
        insert_result = insert_customer_behavior(behavior_create, db_path=db_path)
        if insert_result["status"] != "success":
            logger.error("insert_customer_behavior failed: %s", insert_result["message"])
            return jsonify(format_error("Failed to record prediction result")), 500

        # Step 5 — log retention action automatically if high risk
        action_taken = None
        if churn_score >= 0.70:
            action_message = (
                f"Automated retention action triggered. "
                f"User {user_id} scored {churn_score:.4f} churn probability."
            )
            retention_create = RetentionActionCreate(
                user_id=user_id,
                churn_score=churn_score,
                action_type=action_type,
                action_message=action_message,
                created_at=_now_utc(),
            )
            retention_result = log_retention_action(retention_create, db_path=db_path)
            if retention_result["status"] != "success":
                logger.error("log_retention_action failed: %s", retention_result["message"])
                # Non-fatal — prediction succeeded, log the warning and continue
            else:
                action_taken = action_type

        return jsonify(format_response(
            status="success",
            data={
                "user_id": user_id,
                "churn_score": churn_score,
                "risk_level": risk_level,
                "action_taken": action_taken,
            },
            message="",
        )), 200

    except Exception:
        logger.exception("Error handling /predict request")
        return jsonify(format_error("An internal error occurred")), 500


# ---------------------------------------------------------------------------
# GET /api/churn/report?user_id=1
# ---------------------------------------------------------------------------

@churn_bp.route('/report', methods=['GET'])
def handle_report():
    try:
        raw_user_id = request.args.get('user_id')
        valid_user, user_error = validate_user_id(raw_user_id)
        if not valid_user:
            return jsonify(format_error(user_error)), 400

        user_id = int(raw_user_id)
        db_path = _get_db_path()

        # Step 1 — verify user exists
        user_result = get_user_by_id(user_id, db_path=db_path)
        if user_result["status"] != "success":
            msg = user_result.get("message", "").lower()
            if "not found" in msg:
                return jsonify(format_error(f"User {user_id} not found")), 404
            return jsonify(format_error("Service temporarily unavailable")), 503

        # Step 2 — fetch behavior
        behavior_result = get_customer_behavior(user_id, db_path=db_path, limit=1)
        if behavior_result["status"] != "success":
            return jsonify(format_error("Failed to fetch customer behavior")), 500

        behavior_rows = behavior_result["data"].get("behavior", [])
        latest_behavior = behavior_rows[0] if behavior_rows else {}
        churn_score = latest_behavior.get("churn_score", 0.0)
        risk_level = get_risk_level(churn_score) if behavior_rows else "unknown"

        # Step 3 — fetch retention actions
        retention_result = get_retention_actions(user_id, db_path=db_path)
        if retention_result["status"] != "success":
            return jsonify(format_error("Failed to fetch retention actions")), 500

        retention_actions = retention_result["data"].get("retention_actions", [])

        return jsonify(format_response(
            status="success",
            data={
                "user_id": user_id,
                "churn_score": churn_score,
                "risk_level": risk_level,
                "behavior": latest_behavior,
                "retention_actions": retention_actions,
            },
            message="",
        )), 200

    except Exception:
        logger.exception("Error handling /report request")
        return jsonify(format_error("An internal error occurred")), 500
