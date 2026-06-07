import json
import os

FAQ_FILE_PATH = os.path.join(os.path.dirname(__file__), '..', 'faq_data.json')


def _load_faq() -> dict:
    try:
        with open(FAQ_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


_FAQ_DATA = _load_faq()

def load_faq_data() -> dict:
    return _FAQ_DATA.copy()

def get_response_for_intent(intent: str) -> str:
    faq = load_faq_data()
    return faq.get(intent, "I can help you with your inquiry.")
