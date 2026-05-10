import os
import json
import logging
from transformers import pipeline

logger = logging.getLogger(__name__)

HUGGINGFACE_MODEL = os.environ.get('HUGGINGFACE_MODEL', 'typeform/distilbert-base-uncased-mnli')

# Load pipeline globally
try:
    classifier = pipeline("zero-shot-classification", model=HUGGINGFACE_MODEL)
    logger.info("distilBERT zero-shot pipeline loaded successfully.")
except Exception as e:
    logger.error(f"Failed to load HuggingFace pipeline: {e}")
    classifier = None

def get_candidate_intents() -> list:
    """Read intents dynamically from FAQ data."""
    faq_path = os.path.join(os.path.dirname(__file__), '..', 'faq_data.json')
    try:
        with open(faq_path, 'r', encoding='utf-8') as f:
            responses = json.load(f)
            return list(responses.keys())
    except Exception:
        return [
            "refund_policy",
            "order_status",
            "shipping_issue",
            "product_inquiry",
            "complaint",
            "general_support"
        ]

def run_inference(user_query: str) -> dict:
    """
    Runs zero-shot intent classification.
    Returns the top intent and its confidence score.
    """
    if not classifier:
        return {"intent": "unknown", "confidence": 0.0}

    candidates = get_candidate_intents()
    result = classifier(user_query, candidates)
    
    return {
        "intent": result["labels"][0],
        "confidence": round(result["scores"][0], 4)
    }
