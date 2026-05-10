import pytest
from app import app, db
from models import ChatbotLogs, Escalations
from unittest.mock import patch

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()

@patch('app.analyze_intent')
def test_ask_high_confidence(mock_analyze_intent, client):
    """Test when confidence is >= 0.75, it should not escalate."""
    # Mocking NLP response
    mock_analyze_intent.return_value = {
        "intent": "refund_policy",
        "confidence": 0.85,
        "response": "You can request a refund within 30 days.",
        "escalated": False
    }

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

    # Verify db logs
    with app.app_context():
        log = ChatbotLogs.query.first()
        assert log is not None
        assert log.escalated is False
        assert log.confidence_score == 0.85

        escalation = Escalations.query.first()
        assert escalation is None

@patch('app.analyze_intent')
def test_ask_low_confidence(mock_analyze_intent, client):
    """Test when confidence is < 0.75, it should escalate automatically."""
    # Mocking NLP response
    mock_analyze_intent.return_value = {
        "intent": "unknown",
        "confidence": 0.42,
        "response": "I'm not entirely sure how to help with that. Let me connect you to an agent.",
        "escalated": True
    }

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
    assert "ticket_id" in data or "escalation_ticket_id" in data

    # Verify db logs
    with app.app_context():
        log = ChatbotLogs.query.first()
        assert log is not None
        assert log.escalated is True

        escalation = Escalations.query.first()
        assert escalation is not None
        assert escalation.log_id == log.id

def test_escalate_endpoint(client):
    """Test manual escalation endpoint."""
    response = client.post('/escalate', json={
        "user_id": 2,
        "query": "Agent please",
        "confidence": 0.50
    })

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "success"
    assert json_data["data"]["status"] == "escalated"
    assert json_data["data"]["ticket_id"] is not None

def test_log_endpoint(client):
    """Test raw logging endpoint."""
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
    assert json_data["data"]["log_id"] is not None
