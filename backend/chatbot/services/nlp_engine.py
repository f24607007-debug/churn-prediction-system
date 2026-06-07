from __future__ import annotations

from backend.utils.logger import get_logger
import os
from threading import Lock

try:
    from transformers import pipeline
except ImportError:  # pragma: no cover - exercised when optional dependency is unavailable
    pipeline = None

from .faq_matcher import load_faq_data

logger = get_logger(__name__)

_classifier = None
_classifier_lock = Lock()


class _MissingClassifier:
    def __call__(self, *_args, **_kwargs):
        raise RuntimeError("NLP model is unavailable.")


def init_model(model_name: str | None = None):
    global _classifier
    if _classifier is None:
        with _classifier_lock:
            if _classifier is None:
                resolved_model = (
                    model_name
                    or os.environ.get('HUGGINGFACE_MODEL', 'typeform/distilbert-base-uncased-mnli')
                )
                if pipeline is None:
                    logger.warning("transformers is not installed; NLP inference is unavailable.")
                    _classifier = _MissingClassifier()
                    return None
                try:
                    logger.info("Loading HuggingFace pipeline lazily with model: %s", resolved_model)
                    _classifier = pipeline("zero-shot-classification", model=resolved_model)
                    logger.info("distilBERT zero-shot pipeline loaded successfully.")
                except Exception:
                    logger.exception("Failed to load Hugging Face pipeline.")
                    _classifier = _MissingClassifier()
                    return None
    return _classifier


def is_model_loaded() -> bool:
    return _classifier is not None and not isinstance(_classifier, _MissingClassifier)


def get_candidate_intents() -> list:
    faq = load_faq_data()
    intents = list(faq.keys())
    if not intents:
        return [
            "refund_policy",
            "order_status",
            "shipping_issue",
            "product_inquiry",
            "complaint",
            "general_support",
            "account_issue",
            "payment_problem",
            "cancellation",
            "delivery_address",
            "loyalty_points",
            "out_of_stock",
        ]
    return intents


def run_inference(user_query: str) -> dict:
    if not user_query or not isinstance(user_query, str):
        raise ValueError("Invalid user query: query must be a non-empty string.")

    if len(user_query) > 2000:
        raise ValueError("Query exceeds maximum allowed length of 2000 characters.")

    classifier = init_model()
    if classifier is None:
        raise RuntimeError("NLP model is unavailable.")

    candidates = get_candidate_intents()
    result = classifier(user_query, candidates)

    return {
        "intent": result["labels"][0],
        "confidence": round(result["scores"][0], 4),
    }
