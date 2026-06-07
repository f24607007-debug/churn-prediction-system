from __future__ import annotations

import os
from threading import Lock

import joblib
import pandas as pd

from backend.utils.logger import get_logger

logger = get_logger(__name__)

MODEL_PATH = os.path.join(
    os.path.dirname(__file__), 'models', 'churn_model.pkl'
)

# Feature order must match train.py FEATURES list exactly
CHURN_FEATURES = [
    'purchase_frequency',
    'inactivity_days',
    'cart_abandonment_count',
    'refund_count',
    'complaint_count',
    'login_frequency',
]

_pipeline = None         # lazy load — same pattern as nlp_engine.py
_pipeline_lock = Lock()  # guards the check-then-set against concurrent first requests


def _get_pipeline():
    global _pipeline
    if _pipeline is None:              # fast path — no lock after warm-up
        with _pipeline_lock:
            if _pipeline is None:      # second check inside lock
                if not os.path.exists(MODEL_PATH):
                    raise FileNotFoundError(
                        f"Model not found at {MODEL_PATH}. Run train.py first."
                    )
                _pipeline = joblib.load(MODEL_PATH)
                logger.info("Churn pipeline loaded successfully.")
    return _pipeline


def predict_churn(behavior_row: dict) -> float:
    """
    Takes one customer_behavior row dict and returns churn probability
    as a float in [0.0, 1.0].

    Missing feature keys become NaN in the DataFrame; the pipeline's
    SimpleImputer replaces them with the training-set median — the same
    strategy used during training, guaranteeing consistency.

    The output is clamped to [0.0, 1.0] as a defensive guard against
    any floating-point edge cases from predict_proba.
    """
    pipeline = _get_pipeline()

    # Build a single-row DataFrame with named columns so the pipeline's
    # feature names are preserved end-to-end (avoids sklearn warnings and
    # ensures the imputer sees NaN for genuinely missing keys rather than 0).
    row = {f: behavior_row.get(f) for f in CHURN_FEATURES}  # None → NaN in DataFrame
    X = pd.DataFrame([row], columns=CHURN_FEATURES)

    proba = pipeline.predict_proba(X)[0][1]
    return round(float(max(0.0, min(1.0, proba))), 4)
