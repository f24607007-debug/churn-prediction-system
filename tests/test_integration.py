from __future__ import annotations

import os
import pytest
from unittest.mock import patch

from backend.app import create_app
from backend.config import Config
from backend.database.db import insert_user, UserCreate
from uuid import uuid4

_INTEGRATION_DB = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'instance', 'integration_churn_system.db')
)


class IntegrationTestConfig(Config):
    TESTING = True
    DATABASE_URL = _INTEGRATION_DB


def _seed_user(name="integration_user"):
    """Insert a user via Member 4's DB layer and return its id."""
    tag = uuid4().hex[:8]
    result = insert_user(
        UserCreate(
            name=f"{name}_{tag}",
            email=f"{name}_{tag}@example.com",
            password="testPass99",
            join_date="2024-01-01T00:00:00+00:00",
            total_orders=0,
            total_spent=0.0,
        ),
        db_path=_INTEGRATION_DB,
    )
    assert result["status"] == "success", f"seed_user failed: {result['message']}"
    return result["data"]["user_id"]


@pytest.fixture
def client():
    if os.path.exists(_INTEGRATION_DB):
        try:
            os.remove(_INTEGRATION_DB)
        except Exception:
            pass

    app = create_app(IntegrationTestConfig)

    with app.app_context():
        _seed_user("alice")
        _seed_user("bob")

    with app.test_client() as c:
        yield c

    if os.path.exists(_INTEGRATION_DB):
        try:
            os.remove(_INTEGRATION_DB)
        except Exception:
            pass


@patch('backend.chatbot.routes.is_model_loaded')
@patch('backend.chatbot.routes._verify_db_connection')
def test_integration_health_and_churn_status(mock_verify_db, mock_is_model_loaded, client):
    """Health check and churn blueprint both respond correctly."""
    mock_verify_db.return_value = True
    mock_is_model_loaded.return_value = True

    # 1. Chatbot health
    res = client.get('/api/chatbot/health')
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["data"]["db_reachable"] is True
    assert data["data"]["nlp_loaded"] is True

    # 2. Churn predict — bad user returns 404 (churn blueprint reachable at /api/churn)
    res = client.post('/api/churn/predict', json={"user_id": 99999})
    assert res.status_code == 404
    data = res.get_json()
    assert data["status"] == "error"
