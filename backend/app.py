from __future__ import annotations

from flask import Flask, jsonify
from flask_cors import CORS
from backend.config import Config
from backend.chatbot.routes import chatbot_bp
from backend.chatbot.services.nlp_engine import init_model, is_model_loaded
from backend.database.db import init_db
from backend.utils.helpers import build_response


def create_app(config_class=Config):
    """Flask application factory."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    # Fail fast in production if insecure defaults are still in place
    config_class.validate_production()

    CORS(app, origins=config_class.ALLOWED_ORIGINS)

    app.register_blueprint(chatbot_bp, url_prefix='/api/chatbot')

    try:
        from backend.churn.routes import churn_bp
        app.register_blueprint(churn_bp, url_prefix='/api/churn')
    except ImportError as e:
        app.logger.warning("Churn blueprint unavailable: %s", e)

    with app.app_context():
        db_path = app.config.get("DATABASE_URL")
        result = init_db(db_path=db_path)
        if result["status"] != "success":
            raise RuntimeError(f"Failed to initialize database: {result['message']}")

        if app.config.get("WARMUP_NLP_ON_STARTUP"):
            try:
                init_model()
                if not is_model_loaded():
                    raise RuntimeError("Failed to initialize NLP model during startup")
            except Exception as e:
                app.logger.error(f"Failed to warm up NLP model on startup: {e}")
                raise

    @app.errorhandler(404)
    def not_found_error(error):
        return jsonify(build_response(status="error", data={}, message="Resource not found")), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify(build_response(status="error", data={}, message="An internal server error occurred")), 500

    return app


if __name__ == "__main__":
    app = create_app()
    port = app.config.get('PORT', 5000)
    app.run(host="0.0.0.0", port=port, debug=app.config.get('DEBUG', False))
