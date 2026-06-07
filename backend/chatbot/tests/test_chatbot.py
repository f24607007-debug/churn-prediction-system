from __future__ import annotations

import os
import pytest
from unittest.mock import patch
from uuid import uuid4

from backend.app import create_app
from backend.config import Config
from backend.database.db import (
    get_connection,
    init_db,
    insert_user,
    add_chatbot_log,
    ChatbotLogCreate,
    UserCreate,
)


# ---------------------------------------------------------------------------
# Test configuration
# ---------------------------------------------------------------------------

_TEST_DB = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', 'instance', 'test_churn_system.db')
)


class TestConfig(Config):
    TESTING = True
    DATABASE_URL = _TEST_DB


class WarmupConfig(TestConfig):
    WARMUP_NLP_ON_STARTUP = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(name="test_user", suffix=None):
    """Insert a fresh user via Member 4's insert_user and return its id."""
    tag = suffix or uuid4().hex[:8]
    result = insert_user(
        UserCreate(
            name=f"{name}_{tag}",
            email=f"{name}_{tag}@example.com",
            password="testPass99",
            join_date="2024-01-01T00:00:00+00:00",
            total_orders=0,
            total_spent=0.0,
        ),
        db_path=_TEST_DB,
    )
    assert result["status"] == "success", f"insert_user failed: {result['message']}"
    return result["data"]["user_id"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    if os.path.exists(_TEST_DB):
        try:
            os.remove(_TEST_DB)
        except Exception:
            pass

    application = create_app(TestConfig)

    # Pre-seed three users that test IDs 1,2,3 target
    with application.app_context():
        _make_user("alice")
        _make_user("bob")
        _make_user("charlie")

    yield application

    if os.path.exists(_TEST_DB):
        try:
            os.remove(_TEST_DB)
        except Exception:
            pass


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# App-factory tests
# ---------------------------------------------------------------------------

@patch('backend.app.init_db')
@patch('backend.app.is_model_loaded')
@patch('backend.app.init_model')
def test_create_app_warms_nlp_on_startup(mock_init_model, mock_is_model_loaded, mock_init_db):
    mock_is_model_loaded.return_value = True
    mock_init_db.return_value = {"status": "success", "data": {}, "message": "ok"}

    application = create_app(WarmupConfig)

    assert application is not None
    mock_init_db.assert_called_once()
    mock_init_model.assert_called_once()


API_PREFIX = '/api/chatbot'


# ---------------------------------------------------------------------------
# /ask tests
# ---------------------------------------------------------------------------

@patch('backend.chatbot.routes.run_inference')
def test_ask_high_confidence(mock_inference, client):
    mock_inference.return_value = {"intent": "refund_policy", "confidence": 0.85}

    response = client.post(f'{API_PREFIX}/ask', json={"user_id": 1, "query": "What is your refund policy?"})

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "success"
    assert json_data["data"]["intent"] == "refund_policy"
    assert json_data["data"]["confidence"] == 0.85
    assert json_data["data"]["escalated"] is False
    assert "ticket_id" not in json_data["data"]

    with get_connection(_TEST_DB) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chatbot_logs ORDER BY id DESC LIMIT 1")
        log = cursor.fetchone()
        assert log is not None
        assert log["user_id"] == 1
        assert log["detected_intent"] == "refund_policy"
        assert log["escalated"] == 0

        cursor.execute(
            "SELECT * FROM audit_log WHERE entity='chatbot_logs' ORDER BY id DESC LIMIT 1"
        )
        audit = cursor.fetchone()
        assert audit is not None
        assert audit["event_type"] == "chatbot_log_added"


@patch('backend.chatbot.routes.run_inference')
def test_ask_low_confidence_escalates(mock_inference, client):
    mock_inference.return_value = {"intent": "unknown", "confidence": 0.42}

    response = client.post(f'{API_PREFIX}/ask', json={"user_id": 1, "query": "I am having a complicated billing issue."})

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "success"
    assert json_data["data"]["escalated"] is True
    assert "ticket_id" in json_data["data"]
    ticket_id = json_data["data"]["ticket_id"]

    with get_connection(_TEST_DB) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM escalations WHERE id = ?", (ticket_id,))
        escalation = cursor.fetchone()
        assert escalation is not None
        assert escalation["user_id"] == 1
        assert escalation["status"] == "open"
        assert escalation["created_at"] is not None
        assert escalation["updated_at"] is not None

        cursor.execute("SELECT COUNT(*) FROM audit_log")
        audit_count = cursor.fetchone()[0]
        assert audit_count >= 2


def test_manual_escalate(client):
    response = client.post(f'{API_PREFIX}/escalate', json={
        "user_id": 2,
        "query": "Please connect me to an agent.",
        "confidence": 0.55,
    })

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "success"
    assert json_data["data"]["status"] == "open"

    ticket_id = json_data["data"]["ticket_id"]

    with get_connection(_TEST_DB) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM escalations WHERE id = ?", (ticket_id,))
        esc = cursor.fetchone()
        assert esc is not None
        assert esc["status"] == "open"
        assert esc["user_id"] == 2
        assert esc["updated_at"] is not None


def test_log_endpoint(client):
    response = client.post(f'{API_PREFIX}/log', json={
        "user_id": 3,
        "query": "Check reward points balance",
        "intent": "loyalty_points",
        "confidence": 0.95,
        "response": "Earn points on every purchase!",
        "escalated": False,
    })

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "success"
    assert json_data["data"]["status"] == "saved"

    log_id = json_data["data"]["log_id"]

    with get_connection(_TEST_DB) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chatbot_logs WHERE id = ?", (log_id,))
        log = cursor.fetchone()
        assert log is not None
        assert log["user_id"] == 3
        assert log["detected_intent"] == "loyalty_points"


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

def test_empty_query_rejected(client):
    response = client.post(f'{API_PREFIX}/ask', json={"user_id": 1, "query": ""})
    assert response.status_code == 400
    json_data = response.get_json()
    assert json_data["status"] == "error"
    assert "query" in json_data["message"].lower()


def test_long_query_rejected(client):
    long_query = "a" * 2001
    response = client.post(f'{API_PREFIX}/ask', json={"user_id": 1, "query": long_query})
    assert response.status_code == 400
    json_data = response.get_json()
    assert json_data["status"] == "error"
    assert "2000 characters" in json_data["message"]


def test_invalid_user_id_rejected(client):
    response = client.post(f'{API_PREFIX}/ask', json={"user_id": "abc", "query": "Hello"})
    assert response.status_code == 400
    json_data = response.get_json()
    assert json_data["status"] == "error"
    assert "integer" in json_data["message"]


def test_negative_user_id_rejected(client):
    response = client.post(f'{API_PREFIX}/ask', json={"user_id": -5, "query": "Hello"})
    assert response.status_code == 400
    json_data = response.get_json()
    assert json_data["status"] == "error"
    assert "user_id" in json_data["message"]


def test_non_existent_user_id_fails(client):
    response = client.post(f'{API_PREFIX}/ask', json={"user_id": 9999, "query": "Hello"})
    assert response.status_code == 400
    json_data = response.get_json()
    assert json_data["status"] == "error"
    assert "does not exist" in json_data["message"]


def test_invalid_confidence_fields_rejected(client):
    response = client.post(f'{API_PREFIX}/escalate', json={
        "user_id": 1, "query": "Connect to human", "confidence": "banana"
    })
    assert response.status_code == 400
    assert response.get_json()["status"] == "error"

    response = client.post(f'{API_PREFIX}/escalate', json={
        "user_id": 1, "query": "Connect to human", "confidence": 1.25
    })
    assert response.status_code == 400
    assert response.get_json()["status"] == "error"


def test_ask_missing_json_body(client):
    response = client.post(f'{API_PREFIX}/ask', data='plain text', content_type='text/plain')
    assert response.status_code == 400
    json_data = response.get_json()
    assert json_data["status"] == "error"
    assert "JSON" in json_data["message"]


def test_ask_invalid_json_body_rejected(client):
    response = client.post(
        f'{API_PREFIX}/ask',
        data='{"user_id": 1,',
        content_type='application/json',
    )
    assert response.status_code == 400
    json_data = response.get_json()
    assert json_data["status"] == "error"
    assert "JSON" in json_data["message"]


# ---------------------------------------------------------------------------
# NLP / health tests
# ---------------------------------------------------------------------------

@patch('backend.chatbot.routes.run_inference')
def test_ask_nlp_offline_rejected(mock_inference, client):
    mock_inference.side_effect = RuntimeError("Model download failed")

    response = client.post(f'{API_PREFIX}/ask', json={
        "user_id": 1, "query": "What is the status of my refund?"
    })

    assert response.status_code == 503
    json_data = response.get_json()
    assert json_data["status"] == "error"
    assert "temporarily unavailable" in json_data["message"]


@patch('backend.chatbot.routes.is_model_loaded')
@patch('backend.chatbot.routes._verify_db_connection')
def test_health_check_endpoint(mock_verify_db, mock_is_model_loaded, client):
    mock_verify_db.return_value = True
    mock_is_model_loaded.return_value = True

    response = client.get(f'{API_PREFIX}/health')
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "success"
    assert json_data["data"]["db_reachable"] is True
    assert json_data["data"]["nlp_loaded"] is True


@patch('backend.chatbot.routes.init_model')
@patch('backend.chatbot.routes.is_model_loaded')
@patch('backend.chatbot.routes._verify_db_connection')
def test_health_check_does_not_trigger_model_load(mock_verify_db, mock_is_model_loaded, mock_init_model, client):
    mock_verify_db.return_value = True
    mock_is_model_loaded.return_value = False

    response = client.get(f'{API_PREFIX}/health')

    assert response.status_code == 503
    json_data = response.get_json()
    assert json_data["status"] == "error"
    assert json_data["data"]["db_reachable"] is True
    assert json_data["data"]["nlp_loaded"] is False
    mock_init_model.assert_not_called()


@patch('backend.chatbot.routes.is_model_loaded')
@patch('backend.chatbot.routes._verify_db_connection')
def test_health_check_not_ready_when_nlp_unloaded(mock_verify_db, mock_is_model_loaded, client):
    mock_verify_db.return_value = True
    mock_is_model_loaded.return_value = False

    response = client.get(f'{API_PREFIX}/health')
    assert response.status_code == 503
    json_data = response.get_json()
    assert json_data["status"] == "error"


@patch('backend.chatbot.routes.is_model_loaded')
@patch('backend.chatbot.routes._verify_db_connection')
def test_health_check_database_offline(mock_verify_db, mock_is_model_loaded, client):
    mock_verify_db.return_value = False
    mock_is_model_loaded.return_value = True

    response = client.get(f'{API_PREFIX}/health')
    assert response.status_code == 503
    assert response.get_json()["status"] == "error"


@patch('backend.chatbot.routes.run_inference')
def test_ask_unknown_intent_fallback(mock_inference, client):
    mock_inference.return_value = {"intent": "unmapped_intent", "confidence": 0.95}

    response = client.post(f'{API_PREFIX}/ask', json={
        "user_id": 1, "query": "Tell me something random."
    })

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "success"
    assert json_data["data"]["response"] == "I can help you with your inquiry."


def test_log_missing_fields(client):
    response = client.post(f'{API_PREFIX}/log', json={
        "user_id": 3, "query": "Check reward points balance"
    })
    assert response.status_code == 400
    json_data = response.get_json()
    assert json_data["status"] == "error"
    assert "Missing required fields" in json_data["message"]


# ---------------------------------------------------------------------------
# DB contract / rollback tests
# ---------------------------------------------------------------------------

@patch('backend.chatbot.routes.run_inference')
@patch('backend.chatbot.routes.add_chatbot_log')
@patch('backend.chatbot.routes.insert_escalation')
def test_ask_db_insert_called_with_correct_args(mock_insert_escalation, mock_add_log, mock_inference, client):
    mock_inference.return_value = {"intent": "order_status", "confidence": 0.92}
    mock_add_log.return_value = {"status": "success", "data": {"log_id": 321}, "message": "ok"}
    mock_insert_escalation.return_value = {"status": "success", "data": {"escalation_id": 654}, "message": "ok"}

    response = client.post(f'{API_PREFIX}/ask', json={"user_id": 1, "query": "Where is my order?"})

    assert response.status_code == 200
    assert mock_add_log.call_count == 1
    log_arg = mock_add_log.call_args.args[0]
    assert log_arg.user_id == 1
    assert log_arg.user_query == "Where is my order?"
    assert log_arg.detected_intent == "order_status"
    assert log_arg.escalated == 0
    assert mock_insert_escalation.call_count == 0


@patch('backend.chatbot.routes.insert_escalation')
@patch('backend.chatbot.routes.run_inference')
def test_ask_escalation_failure_rolls_back_log(mock_inference, mock_insert_escalation, client):
    """When escalation insert fails, the chatbot_log is deleted but audit trail is preserved."""
    user_id = _make_user("rollback")

    mock_inference.return_value = {"intent": "unknown", "confidence": 0.12}
    mock_insert_escalation.return_value = {"status": "error", "data": {}, "message": "ticket service down"}

    query = f"Refund escalation rollback test {uuid4().hex}"
    response = client.post(f'{API_PREFIX}/ask', json={"user_id": user_id, "query": query})

    assert response.status_code == 500
    assert response.get_json()["status"] == "error"

    with get_connection(_TEST_DB) as conn:
        cursor = conn.cursor()
        # Chatbot log should be gone
        cursor.execute(
            "SELECT COUNT(*) FROM chatbot_logs WHERE user_id = ? AND user_query = ?",
            (user_id, query),
        )
        assert cursor.fetchone()[0] == 0

        # But the ROLLBACK audit entry must exist — audit trail preserved
        cursor.execute(
            "SELECT COUNT(*) FROM audit_log WHERE event_type = 'chatbot_log_rolled_back' AND entity = 'chatbot_logs'",
        )
        assert cursor.fetchone()[0] >= 1


# ---------------------------------------------------------------------------
# helpers / config unit tests
# ---------------------------------------------------------------------------

def test_build_response_preserves_falsy_data():
    """build_response must not coerce falsy-but-valid data ([], 0, False) to {}."""
    from backend.utils.helpers import build_response
    assert build_response(data=[])["data"] == []
    assert build_response(data=0)["data"] == 0
    assert build_response(data=False)["data"] is False
    assert build_response(data=None)["data"] == {}


def test_validate_production_raises_on_insecure_secret():
    """validate_production() must raise when APP_ENV=production and SECRET_KEY is default."""
    import pytest
    from backend.config import Config

    class ProdConfig(Config):
        APP_ENV = "production"
        SECRET_KEY = "dev-secret-change-me"

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        ProdConfig.validate_production()


def test_validate_production_passes_with_secure_secret():
    from backend.config import Config

    class ProdConfig(Config):
        APP_ENV = "production"
        SECRET_KEY = "a-proper-random-secret-value-here"

    ProdConfig.validate_production()  # must not raise
