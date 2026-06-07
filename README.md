# churn-prediction-system

E-commerce customer churn prediction with AI customer support chatbot.

## Stack

- **Backend**: Python / Flask
- **AI/NLP**: HuggingFace distilBERT (zero-shot classification)
- **ML**: scikit-learn Random Forest
- **Database**: SQLite (dev) → PostgreSQL (prod)
- **Gateway**: Rust / Actix-web (port 8080)
- **Frontend**: React

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env          # then edit .env with your values

# 3. Train the churn model (required before /api/churn/predict works)
#    Must be run from the project root — NOT from inside backend/churn/
python -m backend.churn.train   # recommended (works from any shell in project root)
# or: python backend/churn/train.py  (also fine from project root)

# 4. Run the Flask server
flask --app backend.app run --port 5000

# 5. Run all tests
pytest
```

## Environment variables

See `.env.example` for the full list. Key variables:

| Variable | Default | Notes |
|---|---|---|
| `SECRET_KEY` | `dev-secret-change-me` | Must be 32+ chars in production |
| `DATABASE_URL` | auto | Path to SQLite file; omit for default |
| `CONFIDENCE_THRESHOLD` | `0.75` | NLP score below this → escalate |
| `APP_ENV` | `development` | Set to `production` to enable security checks |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated CORS origins |
| `CHURN_DATASET_PATH` | bundled CSV | Path to real training data |

## API endpoints

### Chatbot (`/api/chatbot`)
- `POST /api/chatbot/ask` — submit a user query
- `POST /api/chatbot/escalate` — manually escalate a query
- `POST /api/chatbot/log` — save an externally-processed interaction
- `GET  /api/chatbot/health` — service health check

### Churn (`/api/churn`)
- `POST /api/churn/predict` — run churn prediction for a user
- `GET  /api/churn/report?user_id=N` — fetch churn report for a user

## Running tests

```bash
pytest                          # all tests
pytest backend/chatbot/tests/   # chatbot unit tests only
pytest backend/churn/tests/     # churn unit tests only
pytest tests/                   # integration + performance
```
