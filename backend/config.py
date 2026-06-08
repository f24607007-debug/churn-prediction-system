from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-change-me')
    DATABASE_URL = os.getenv(
    'DATABASE_URL',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', 'database', 'churn.db')
)  # None → db_core uses its own default path
    CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD', '0.75'))
    HUGGINGFACE_MODEL = os.getenv('HUGGINGFACE_MODEL', 'typeform/distilbert-base-uncased-mnli')
    APP_ENV = os.getenv('APP_ENV', 'development')
    # Read WARMUP_NLP_ON_STARTUP independently — not derived from APP_ENV
    # so explicit env-var overrides always win and the conditional is not dead code.
    WARMUP_NLP_ON_STARTUP = os.getenv('WARMUP_NLP_ON_STARTUP', 'false').lower() in ('true', '1', 't')
    ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173').split(',')

    @classmethod
    def validate_production(cls):
        """Raise if required production settings are missing or insecure."""
        if cls.APP_ENV == 'production':
            if cls.SECRET_KEY == 'dev-secret-change-me' or len(cls.SECRET_KEY) < 32:
                raise RuntimeError(
                    "SECRET_KEY must be a secure random string of at least 32 characters in production"
                )
