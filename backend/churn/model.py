import os
import pickle
import logging
import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(__file__)
MODEL_PATH = os.path.join(BASE_DIR, 'models', 'churn_model.pkl')

_model = None

def load_model():
    global _model
    if _model is None:
        if os.path.exists(MODEL_PATH):
            with open(MODEL_PATH, 'rb') as f:
                _model = pickle.load(f)
            logger.info("Churn model loaded successfully.")
        else:
            logger.warning(f"Model file not found at {MODEL_PATH}")
    return _model

def predict_churn_probability(features: dict) -> float:
    """
    Runs inference on the provided features and returns a probability between 0.0 and 1.0.
    """
    model = load_model()
    if not model:
        # Fallback if model isn't trained yet
        return 0.0
        
    feature_order = [
        'purchase_frequency',
        'inactivity_days',
        'cart_abandonment_count',
        'refund_count',
        'complaint_count',
        'login_frequency'
    ]
    
    # Extract features in exact order
    input_data = []
    for col in feature_order:
        input_data.append(features.get(col, 0))
        
    df = pd.DataFrame([input_data], columns=feature_order)
    
    # Return probability of the positive class (Churn = 1)
    # predict_proba returns array of shape (n_samples, n_classes)
    prob = model.predict_proba(df)[0][1]
    
    # Guarantee [0.0, 1.0] range
    return max(0.0, min(1.0, float(prob)))
