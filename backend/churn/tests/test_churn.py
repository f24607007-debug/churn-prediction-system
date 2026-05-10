import pytest
from flask import Flask
from unittest.mock import patch
from backend.churn.routes import churn_bp

@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(churn_bp)
    app.config['TESTING'] = True
    return app

@pytest.fixture
def client(app):
    return app.test_client()

@patch('backend.churn.routes.predict_churn_probability')
@patch('backend.churn.routes._get_customer_behavior')
@patch('backend.churn.routes._insert_retention_action')
def test_predict_endpoint_feature_extraction(mock_insert, mock_get_behavior, mock_predict, client):
    """Test that features are merged properly and probability is within range."""
    # DB features
    mock_get_behavior.return_value = {
        "login_frequency": 10,
        "complaint_count": 1
    }
    mock_predict.return_value = 0.82
    mock_insert.return_value = 1

    response = client.post('/predict', json={
        "user_id": 1,
        "purchase_count": 2,
        "days_inactive": 25,
        "cart_abandonments": 4,
        "refund_count": 1
    })

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "success"
    
    data = json_data["data"]
    assert data["user_id"] == 1
    assert data["churn_score"] == 0.82
    assert data["risk_level"] == "high"
    assert data["retention_triggered"] is True

    # Assert model was called with merged features
    called_features = mock_predict.call_args[0][0]
    assert called_features["login_frequency"] == 10
    assert called_features["purchase_count"] == 2
    
    # Assert DB insert was called
    mock_insert.assert_called_once()

@patch('backend.churn.routes._get_high_risk_customers')
def test_report_endpoint_shape(mock_get_customers, client):
    """Test the /report endpoint response shape."""
    mock_get_customers.return_value = [
        {"user_id": 1, "churn_score": 0.82, "risk_level": "high"},
        {"user_id": 7, "churn_score": 0.76, "risk_level": "high"}
    ]

    response = client.get('/report')

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "success"
    
    data = json_data["data"]
    assert "high_risk_customers" in data
    assert "generated_at" in data
    assert len(data["high_risk_customers"]) == 2
    assert data["high_risk_customers"][0]["user_id"] == 1

def test_model_probability_range():
    """Test that model.py predict_churn_probability always outputs [0, 1]."""
    from backend.churn.model import predict_churn_probability
    import numpy as np
    
    # Mock model
    class MockModel:
        def predict_proba(self, X):
            return np.array([[0.1, 0.9]])
            
    with patch('backend.churn.model.load_model', return_value=MockModel()):
        prob = predict_churn_probability({})
        assert 0.0 <= prob <= 1.0
        assert prob == 0.9

    # Test fallback
    with patch('backend.churn.model.load_model', return_value=None):
        prob = predict_churn_probability({})
        assert prob == 0.0
