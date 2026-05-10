import os
import logging
from transformers import pipeline

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration
HUGGINGFACE_MODEL = os.environ.get('HUGGINGFACE_MODEL', 'typeform/distilbert-base-uncased-mnli')
CONFIDENCE_THRESHOLD = float(os.environ.get('CONFIDENCE_THRESHOLD', '0.75'))

# Load zero-shot classification pipeline globally to avoid reloading on every request
try:
    # using a distilbert-based zero-shot model for speed and efficiency
    classifier = pipeline("zero-shot-classification", model=HUGGINGFACE_MODEL)
    logger.info("distilBERT zero-shot pipeline loaded successfully.")
except Exception as e:
    logger.error(f"Failed to load HuggingFace pipeline: {e}")
    classifier = None

# Pre-defined intents for zero-shot classification
CANDIDATE_INTENTS = [
    "refund_policy",
    "order_status",
    "shipping_issue",
    "product_inquiry",
    "complaint",
    "general_support"
]

def analyze_intent(user_query: str) -> dict:
    """
    Analyzes the user's query using zero-shot intent classification.
    Returns a dictionary with intent, confidence score, and a default response.
    """
    if not classifier:
        # Fallback if model fails to load
        return {
            "intent": "unknown",
            "confidence": 0.0,
            "response": "Model unavailable.",
            "escalated": True
        }

    # Perform zero-shot classification
    result = classifier(user_query, CANDIDATE_INTENTS)
    
    # The first label has the highest score
    best_intent = result["labels"][0]
    best_score = result["scores"][0]
    
    # Determine branching logic based strictly on threshold
    escalated = best_score < CONFIDENCE_THRESHOLD
    
    if escalated:
        response_text = "I'm not entirely sure how to help with that. Let me connect you to an agent."
    else:
        # Simple rule-based mapping for responses based on intent
        response_text = get_response_for_intent(best_intent)
        
    return {
        "intent": best_intent,
        "confidence": round(best_score, 4),
        "response": response_text,
        "escalated": escalated
    }

def get_response_for_intent(intent: str) -> str:
    """Returns a canned response for a given intent."""
    responses = {
        "refund_policy": "You can request a refund within 30 days.",
        "order_status": "You can track your order in the 'My Orders' section.",
        "shipping_issue": "Shipping usually takes 3-5 business days. We apologize for any delays.",
        "product_inquiry": "You can find more product details on our store pages.",
        "complaint": "We are sorry you had a bad experience. Please provide more details.",
        "general_support": "How can I help you today?"
    }
    return responses.get(intent, "I can help you with your inquiry.")
