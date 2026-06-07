from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from backend.utils.logger import get_logger

load_dotenv()

logger = get_logger(__name__)

BASE_DIR    = os.path.dirname(__file__)
MODELS_DIR  = os.path.join(BASE_DIR, 'models')
MODEL_PATH  = os.path.join(MODELS_DIR, 'churn_model.pkl')
REPORT_PATH = os.path.join(BASE_DIR, 'training_report.json')

# Dataset path — override via env var, fallback to bundled CSV
DATASET_PATH = os.getenv(
    'CHURN_DATASET_PATH',
    os.path.join(BASE_DIR, 'ecommerce_churn.csv'),
)

FEATURES = [
    'purchase_frequency',
    'inactivity_days',
    'cart_abandonment_count',
    'refund_count',
    'complaint_count',
    'login_frequency',
]


# ---------------------------------------------------------------------------
# Synthetic data generator
# ---------------------------------------------------------------------------

def generate_synthetic_data(num_samples: int = 1000) -> str:
    """
    Fallback: generate a correlated synthetic dataset matching our schema.

    Unlike a purely random dataset, the features here have realistic
    correlations so the model learns more than a single threshold rule:
      - high inactivity_days  → low purchase_frequency, low login_frequency
      - high cart_abandonment → moderate refund/complaint
    """
    logger.info("Generating synthetic training data (%d samples)...", num_samples)
    np.random.seed(42)

    # Base inactivity drives the other features
    inactivity_days = np.random.randint(0, 61, num_samples)

    # purchase_frequency is inversely correlated with inactivity
    purchase_frequency = np.clip(
        np.random.randint(0, 20, num_samples) - (inactivity_days // 10),
        0, 20,
    ).astype(int)

    # login_frequency is also inversely correlated with inactivity
    login_frequency = np.clip(
        np.random.randint(1, 30, num_samples) - (inactivity_days // 8),
        0, 30,
    ).astype(int)

    # cart_abandonment weakly correlates with low purchase frequency
    cart_abandonment_count = np.clip(
        np.random.randint(0, 10, num_samples) + np.where(purchase_frequency < 3, 2, 0),
        0, 15,
    ).astype(int)

    refund_count    = np.random.randint(0, 6, num_samples)
    complaint_count = np.random.randint(0, 6, num_samples)

    df = pd.DataFrame({
        'purchase_frequency':     purchase_frequency,
        'inactivity_days':        inactivity_days,
        'cart_abandonment_count': cart_abandonment_count,
        'refund_count':           refund_count,
        'complaint_count':        complaint_count,
        'login_frequency':        login_frequency,
    })

    # Churn definition per Phase 2A spec: inactivity_days > 30 → churned
    df['churned'] = (df['inactivity_days'] > 30).astype(int)

    # 10% label noise to make training non-trivial
    flip_idx = np.random.choice(df.index, size=int(0.1 * num_samples), replace=False)
    df.loc[flip_idx, 'churned'] = 1 - df.loc[flip_idx, 'churned']

    synthetic_path = os.path.join(BASE_DIR, 'ecommerce_churn.csv')
    df.to_csv(synthetic_path, index=False)
    logger.info("Synthetic dataset saved to %s", synthetic_path)
    return synthetic_path


# ---------------------------------------------------------------------------
# Dataset loader
# ---------------------------------------------------------------------------

def load_dataset() -> pd.DataFrame:
    """Load dataset from CSV, falling back to synthetic data if unavailable."""
    if os.path.exists(DATASET_PATH):
        logger.info("Loading dataset from %s", DATASET_PATH)
        df = pd.read_csv(DATASET_PATH)

        missing = [c for c in FEATURES if c not in df.columns]
        if missing:
            logger.warning(
                "Dataset at %s is missing columns %s — falling back to synthetic.",
                DATASET_PATH, missing,
            )
        elif 'churned' in df.columns or 'Churn' in df.columns:
            if 'Churn' in df.columns and 'churned' not in df.columns:
                df = df.rename(columns={'Churn': 'churned'})
            logger.info(
                "Dataset loaded: %d rows, %d churned (%.1f%%)",
                len(df),
                df['churned'].sum(),
                100 * df['churned'].mean(),
            )
            return df[FEATURES + ['churned']]
        else:
            logger.warning(
                "No churn label column ('churned' or 'Churn') in %s — falling back to synthetic.",
                DATASET_PATH,
            )

    path = generate_synthetic_data()
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Model versioning helper
# ---------------------------------------------------------------------------

def _backup_existing_model() -> None:
    """Rename current model file with a UTC timestamp before overwriting."""
    if os.path.exists(MODEL_PATH):
        ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        backup = MODEL_PATH.replace('.pkl', f'_{ts}.pkl')
        os.rename(MODEL_PATH, backup)
        logger.info("Previous model backed up to %s", backup)


# ---------------------------------------------------------------------------
# Training entry point
# ---------------------------------------------------------------------------

def train_model() -> None:
    df = load_dataset()

    # Assign label if not already present (should always be there after load_dataset)
    if 'churned' not in df.columns:
        df['churned'] = (df['inactivity_days'] > 30).astype(int)

    X = df[FEATURES]
    y = df['churned']

    logger.info("Splitting dataset 80/20 (random_state=42)...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42,
    )

    # ------------------------------------------------------------------
    # Build a Pipeline:
    #   1. SimpleImputer  — replaces NaN with column median (same strategy
    #      must be used at inference time; the pipeline guarantees this)
    #   2. RandomForestClassifier — no scaling needed for tree models
    #
    # The entire pipeline is saved as one artifact so training and inference
    # always apply identical preprocessing.  predict_churn() loads this
    # pipeline and calls pipeline.predict_proba() directly.
    # ------------------------------------------------------------------
    pipeline = Pipeline([
        ('imputer', SimpleImputer(strategy='median')),
        ('classifier', RandomForestClassifier(n_estimators=100, random_state=42)),
    ])

    logger.info("Training Pipeline(SimpleImputer → RandomForestClassifier, n_estimators=100)...")
    pipeline.fit(X_train, y_train)

    logger.info("Evaluating model...")
    y_pred = pipeline.predict(X_test)
    y_prob = pipeline.predict_proba(X_test)[:, 1]

    metrics = {
        "accuracy":      round(accuracy_score(y_test, y_pred), 4),
        "precision":     round(precision_score(y_test, y_pred, zero_division=0), 4),
        "recall":        round(recall_score(y_test, y_pred, zero_division=0), 4),
        "f1_score":      round(f1_score(y_test, y_pred, zero_division=0), 4),
        "auc_roc":       round(roc_auc_score(y_test, y_prob), 4),
        "train_samples": int(len(X_train)),
        "test_samples":  int(len(X_test)),
        "trained_at":    datetime.now(timezone.utc).isoformat(),
        "features":      FEATURES,
    }

    for k, v in metrics.items():
        logger.info("%s: %s", k, v)

    os.makedirs(MODELS_DIR, exist_ok=True)
    _backup_existing_model()
    joblib.dump(pipeline, MODEL_PATH)
    logger.info("Pipeline saved to %s", MODEL_PATH)

    with open(REPORT_PATH, 'w') as f:
        json.dump(metrics, f, indent=2)
    logger.info("Training report saved to %s", REPORT_PATH)


if __name__ == '__main__':
    train_model()
