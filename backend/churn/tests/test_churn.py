from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from flask import Flask

from backend.churn.routes import churn_bp, get_risk_level, get_action_type


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(churn_bp, url_prefix='/api/churn')
    app.config['TESTING'] = True
    app.config['DATABASE_URL'] = None
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _behavior_row(inactivity_days=10, churn_score=0.2):
    return {
        "id": 1,
        "user_id": 1,
        "login_frequency": 15,
        "purchase_frequency": 5,
        "cart_abandonment_count": 2,
        "refund_count": 0,
        "complaint_count": 0,
        "inactivity_days": inactivity_days,
        "churn_score": churn_score,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def _db_success(key, rows):
    return {"status": "success", "data": {"behavior": rows}, "message": ""}


def _db_fail(msg="not found"):
    return {"status": "error", "data": {}, "message": msg}


def _db_down(msg="operational error"):
    """Simulates a DB connection failure â€” message does NOT contain 'not found'."""
    return {"status": "error", "data": {}, "message": msg}


# ---------------------------------------------------------------------------
# 1. High churn score â†’ personal_outreach
# ---------------------------------------------------------------------------

@patch('backend.churn.routes.log_retention_action')
@patch('backend.churn.routes.insert_customer_behavior')
@patch('backend.churn.routes.get_customer_behavior')
@patch('backend.churn.routes.get_user_by_id')
@patch('backend.churn.routes.predict_churn')
def test_predict_high_churn_score(
    mock_predict, mock_get_user, mock_get_behavior,
    mock_insert_behavior, mock_log_retention, client
):
    mock_get_user.return_value = {"status": "success", "data": {"user": {}}, "message": ""}
    mock_get_behavior.return_value = _db_success("behavior", [_behavior_row(inactivity_days=60)])
    mock_predict.return_value = 0.91
    mock_insert_behavior.return_value = {"status": "success", "data": {"behavior_id": 1}, "message": ""}
    mock_log_retention.return_value = {"status": "success", "data": {"action_id": 1}, "message": ""}

    resp = client.post('/api/churn/predict', json={"user_id": 1})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["data"]["churn_score"] == 0.91
    assert data["data"]["risk_level"] == "high"
    assert data["data"]["action_taken"] == "personal_outreach"
    mock_log_retention.assert_called_once()


# ---------------------------------------------------------------------------
# 2. Low churn score â†’ no retention action
# ---------------------------------------------------------------------------

@patch('backend.churn.routes.insert_customer_behavior')
@patch('backend.churn.routes.get_customer_behavior')
@patch('backend.churn.routes.get_user_by_id')
@patch('backend.churn.routes.predict_churn')
def test_predict_low_churn_score(
    mock_predict, mock_get_user, mock_get_behavior,
    mock_insert_behavior, client
):
    mock_get_user.return_value = {"status": "success", "data": {}, "message": ""}
    mock_get_behavior.return_value = _db_success("behavior", [_behavior_row(inactivity_days=5)])
    mock_predict.return_value = 0.12
    mock_insert_behavior.return_value = {"status": "success", "data": {"behavior_id": 2}, "message": ""}

    resp = client.post('/api/churn/predict', json={"user_id": 1})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["data"]["churn_score"] == 0.12
    assert data["data"]["risk_level"] == "low"
    assert data["data"]["action_taken"] is None


# ---------------------------------------------------------------------------
# 3. User not found â†’ 404
# ---------------------------------------------------------------------------

@patch('backend.churn.routes.get_user_by_id')
def test_predict_missing_user_returns_404(mock_get_user, client):
    mock_get_user.return_value = _db_fail("User not found")
    resp = client.post('/api/churn/predict', json={"user_id": 9999})
    assert resp.status_code == 404
    assert resp.get_json()["status"] == "error"


# ---------------------------------------------------------------------------
# 4. DB down on user lookup â†’ 503 (not 404)
# ---------------------------------------------------------------------------

@patch('backend.churn.routes.get_user_by_id')
def test_predict_db_down_returns_503(mock_get_user, client):
    mock_get_user.return_value = _db_down("sqlite3.OperationalError: unable to open database")
    resp = client.post('/api/churn/predict', json={"user_id": 1})
    assert resp.status_code == 503
    data = resp.get_json()
    assert data["status"] == "error"
    assert "unavailable" in data["message"].lower()


# ---------------------------------------------------------------------------
# 5. No behavior rows â†’ 404
# ---------------------------------------------------------------------------

@patch('backend.churn.routes.get_customer_behavior')
@patch('backend.churn.routes.get_user_by_id')
def test_predict_no_behavior_returns_404(mock_get_user, mock_get_behavior, client):
    mock_get_user.return_value = {"status": "success", "data": {}, "message": ""}
    mock_get_behavior.return_value = _db_success("behavior", [])
    resp = client.post('/api/churn/predict', json={"user_id": 1})
    assert resp.status_code == 404
    assert resp.get_json()["status"] == "error"


# ---------------------------------------------------------------------------
# 6. Invalid user_id â€” negative and string
# ---------------------------------------------------------------------------

def test_predict_invalid_user_id_negative(client):
    resp = client.post('/api/churn/predict', json={"user_id": -1})
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error"


def test_predict_invalid_user_id_string(client):
    resp = client.post('/api/churn/predict', json={"user_id": "abc"})
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error"


# ---------------------------------------------------------------------------
# 7. Retention action logged when churn_score >= 0.70
# ---------------------------------------------------------------------------

@patch('backend.churn.routes.log_retention_action')
@patch('backend.churn.routes.insert_customer_behavior')
@patch('backend.churn.routes.get_customer_behavior')
@patch('backend.churn.routes.get_user_by_id')
@patch('backend.churn.routes.predict_churn')
def test_predict_retention_action_logged(
    mock_predict, mock_get_user, mock_get_behavior,
    mock_insert_behavior, mock_log_retention, client
):
    mock_get_user.return_value = {"status": "success", "data": {}, "message": ""}
    mock_get_behavior.return_value = _db_success("behavior", [_behavior_row(inactivity_days=45)])
    mock_predict.return_value = 0.78
    mock_insert_behavior.return_value = {"status": "success", "data": {"behavior_id": 3}, "message": ""}
    mock_log_retention.return_value = {"status": "success", "data": {"action_id": 5}, "message": ""}

    resp = client.post('/api/churn/predict', json={"user_id": 1})
    assert resp.status_code == 200
    mock_log_retention.assert_called_once()
    call_args = mock_log_retention.call_args[0][0]
    assert call_args.user_id == 1
    assert call_args.churn_score == 0.78


# ---------------------------------------------------------------------------
# 8. Retention action failure is non-fatal â€” 200 still returned
# ---------------------------------------------------------------------------

@patch('backend.churn.routes.log_retention_action')
@patch('backend.churn.routes.insert_customer_behavior')
@patch('backend.churn.routes.get_customer_behavior')
@patch('backend.churn.routes.get_user_by_id')
@patch('backend.churn.routes.predict_churn')
def test_predict_retention_failure_is_nonfatal(
    mock_predict, mock_get_user, mock_get_behavior,
    mock_insert_behavior, mock_log_retention, client
):
    mock_get_user.return_value = {"status": "success", "data": {}, "message": ""}
    mock_get_behavior.return_value = _db_success("behavior", [_behavior_row(inactivity_days=45)])
    mock_predict.return_value = 0.82
    mock_insert_behavior.return_value = {"status": "success", "data": {"behavior_id": 4}, "message": ""}
    mock_log_retention.return_value = _db_fail("insert error")

    resp = client.post('/api/churn/predict', json={"user_id": 1})
    # Prediction succeeded even though retention logging failed
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["data"]["action_taken"] is None  # action_taken is None when log failed


# ---------------------------------------------------------------------------
# 9. Report: full data returned
# ---------------------------------------------------------------------------

@patch('backend.churn.routes.get_retention_actions')
@patch('backend.churn.routes.get_customer_behavior')
@patch('backend.churn.routes.get_user_by_id')
def test_report_returns_full_data(mock_get_user, mock_get_behavior, mock_get_retention, client):
    mock_get_user.return_value = {"status": "success", "data": {}, "message": ""}
    mock_get_behavior.return_value = _db_success("behavior", [_behavior_row(churn_score=0.82)])
    mock_get_retention.return_value = _db_success("retention_actions", [
        {"id": 1, "user_id": 1, "action_type": "personal_outreach", "churn_score": 0.82}
    ])

    resp = client.get('/api/churn/report?user_id=1')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["data"]["churn_score"] == 0.82
    assert data["data"]["risk_level"] == "high"
    assert isinstance(data["data"]["retention_actions"], list)
    assert "behavior" in data["data"]


# ---------------------------------------------------------------------------
# 10. Report: user not found â†’ 404
# ---------------------------------------------------------------------------

@patch('backend.churn.routes.get_user_by_id')
def test_report_missing_user_returns_404(mock_get_user, client):
    mock_get_user.return_value = _db_fail("User not found")
    resp = client.get('/api/churn/report?user_id=9999')
    assert resp.status_code == 404
    assert resp.get_json()["status"] == "error"


# ---------------------------------------------------------------------------
# 11. Report: DB down on user lookup â†’ 503
# ---------------------------------------------------------------------------

@patch('backend.churn.routes.get_user_by_id')
def test_report_db_down_returns_503(mock_get_user, client):
    mock_get_user.return_value = _db_down("unable to open database")
    resp = client.get('/api/churn/report?user_id=1')
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# 12. Report: empty retention actions
# ---------------------------------------------------------------------------

@patch('backend.churn.routes.get_retention_actions')
@patch('backend.churn.routes.get_customer_behavior')
@patch('backend.churn.routes.get_user_by_id')
def test_report_empty_retention_actions(mock_get_user, mock_get_behavior, mock_get_retention, client):
    mock_get_user.return_value = {"status": "success", "data": {}, "message": ""}
    mock_get_behavior.return_value = _db_success("behavior", [_behavior_row()])
    mock_get_retention.return_value = _db_success("retention_actions", [])

    resp = client.get('/api/churn/report?user_id=1')
    assert resp.status_code == 200
    assert resp.get_json()["data"]["retention_actions"] == []


# ---------------------------------------------------------------------------
# 13. Model not found â†’ clean 500 with helpful message
# ---------------------------------------------------------------------------

@patch('backend.churn.routes.insert_customer_behavior')
@patch('backend.churn.routes.get_customer_behavior')
@patch('backend.churn.routes.get_user_by_id')
@patch('backend.churn.routes.predict_churn')
def test_model_not_found_handled_cleanly(
    mock_predict, mock_get_user, mock_get_behavior, mock_insert_behavior, client
):
    mock_get_user.return_value = {"status": "success", "data": {}, "message": ""}
    mock_get_behavior.return_value = _db_success("behavior", [_behavior_row()])
    mock_predict.side_effect = FileNotFoundError("Model not found. Run train.py first.")

    resp = client.post('/api/churn/predict', json={"user_id": 1})
    assert resp.status_code == 500
    data = resp.get_json()
    assert data["status"] == "error"
    assert "model" in data["message"].lower() or "train" in data["message"].lower()


# ---------------------------------------------------------------------------
# 14. predict_churn: missing behavior key â†’ imputer fills NaN, no crash
# ---------------------------------------------------------------------------

@patch('backend.churn.routes.log_retention_action')
@patch('backend.churn.routes.insert_customer_behavior')
@patch('backend.churn.routes.get_customer_behavior')
@patch('backend.churn.routes.get_user_by_id')
@patch('backend.churn.routes.predict_churn')
def test_predict_with_partial_behavior_row(
    mock_predict, mock_get_user, mock_get_behavior,
    mock_insert_behavior, mock_log_retention, client
):
    """Behavior row missing several keys â€” imputer in pipeline handles NaN."""
    sparse_row = {"id": 1, "user_id": 1, "inactivity_days": 40, "churn_score": 0.0,
                  "created_at": "2026-01-01T00:00:00+00:00"}
    mock_get_user.return_value = {"status": "success", "data": {}, "message": ""}
    mock_get_behavior.return_value = _db_success("behavior", [sparse_row])
    mock_predict.return_value = 0.55
    mock_insert_behavior.return_value = {"status": "success", "data": {"behavior_id": 5}, "message": ""}
    mock_log_retention.return_value = {"status": "success", "data": {"action_id": 6}, "message": ""}

    resp = client.post('/api/churn/predict', json={"user_id": 1})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["data"]["churn_score"] == 0.55
    assert data["data"]["risk_level"] == "medium"


# ---------------------------------------------------------------------------
# 15-17. get_risk_level thresholds
# ---------------------------------------------------------------------------

def test_get_risk_level_high():
    assert get_risk_level(0.75) == "high"
    assert get_risk_level(0.99) == "high"
    assert get_risk_level(1.0) == "high"


def test_get_risk_level_medium():
    assert get_risk_level(0.50) == "medium"
    assert get_risk_level(0.74) == "medium"


def test_get_risk_level_low():
    assert get_risk_level(0.0) == "low"
    assert get_risk_level(0.49) == "low"
