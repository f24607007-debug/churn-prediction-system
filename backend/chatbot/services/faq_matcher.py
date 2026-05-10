import json
import os

FAQ_FILE_PATH = os.path.join(os.path.dirname(__file__), '..', 'faq_data.json')

def get_response_for_intent(intent: str) -> str:
    """Returns a canned response for a given intent from the FAQ data."""
    try:
        with open(FAQ_FILE_PATH, 'r', encoding='utf-8') as f:
            responses = json.load(f)
    except Exception:
        responses = {}
        
    return responses.get(intent, "I can help you with your inquiry.")
