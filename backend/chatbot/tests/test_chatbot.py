import pytest
from flask import Flask
from unittest.mock import patch
from backend.chatbot.routes import chatbot_bp

@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(chatbot_bp)
    app.config['TESTING'] = True
    return app

@pytest.fixture
def client(app):
    return app.test_client()

@patch('backend.chatbot.routes.run_inference')
@patch('backend.chatbot.routes._insert_log')
@patch('backend.chatbot.routes._insert_escalation')
def test_ask_high_confidence(mock_insert_escalation, mock_insert_log, mock_inference, client):
    """Test when confidence is >= 0.75, it should not escalate."""
    mock_inference.return_value = {
        "intent": "refund_policy",
        "confidence": 0.85
    }
    mock_insert_log.return_value = 1

    response = client.post('/ask', json={
        "user_id": 1,
        "query": "What is your refund policy?"
    })

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "success"
    
    data = json_data["data"]
    assert data["intent"] == "refund_policy"
    assert data["confidence"] == 0.85
    assert data["escalated"] is False
    assert data["response"] == "You can request a refund within 30 days."

    mock_insert_log.assert_called_once()
    mock_insert_escalation.assert_not_called()

@patch('backend.chatbot.routes.run_inference')
@patch('backend.chatbot.routes._insert_log')
@patch('backend.chatbot.routes._insert_escalation')
def test_ask_low_confidence(mock_insert_escalation, mock_insert_log, mock_inference, client):
    """Test when confidence is < 0.75, it should escalate automatically."""
    mock_inference.return_value = {
        "intent": "unknown",
        "confidence": 0.42
    }
    mock_insert_log.return_value = 2
    mock_insert_escalation.return_value = 101

    response = client.post('/ask', json={
        "user_id": 1,
        "query": "My order is completely wrong and I am angry"
    })

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "success"
    
    data = json_data["data"]
    assert data["intent"] == "unknown"
    assert data["confidence"] == 0.42
    assert data["escalated"] is True
    assert "escalation_ticket_id" in data
    assert data["escalation_ticket_id"] == 101

    mock_insert_log.assert_called_once()
    mock_insert_escalation.assert_called_once()

@patch('backend.chatbot.routes._insert_escalation')
def test_escalate_endpoint(mock_insert_escalation, client):
    """Test manual escalation endpoint."""
    mock_insert_escalation.return_value = 999

    response = client.post('/escalate', json={
        "user_id": 2,
        "query": "Agent please",
        "confidence": 0.50
    })

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "success"
    assert json_data["data"]["status"] == "escalated"
    assert json_data["data"]["ticket_id"] == 999

@patch('backend.chatbot.routes._insert_log')
def test_log_endpoint(mock_insert_log, client):
    """Test raw logging endpoint."""
    mock_insert_log.return_value = 55

    response = client.post('/log', json={
        "user_id": 3,
        "query": "Test query",
        "intent": "general_support",
        "confidence": 0.99,
        "response": "Test response",
        "escalated": False
    })

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "success"
    assert json_data["data"]["status"] == "saved"
    assert json_data["data"]["log_id"] == 55
