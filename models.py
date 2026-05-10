from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()

def get_current_time():
    return datetime.now(timezone.utc)

class ChatbotLogs(db.Model):
    __tablename__ = 'chatbot_logs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)
    user_query = db.Column(db.Text, nullable=False)
    detected_intent = db.Column(db.String(255), nullable=True)
    chatbot_response = db.Column(db.Text, nullable=True)
    confidence_score = db.Column(db.Float, nullable=True)
    escalated = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=get_current_time)

    # Relationship to Escalations
    escalations = db.relationship('Escalations', backref='chatbot_log', lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_query": self.user_query,
            "detected_intent": self.detected_intent,
            "chatbot_response": self.chatbot_response,
            "confidence_score": self.confidence_score,
            "escalated": self.escalated,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }

class Escalations(db.Model):
    __tablename__ = 'escalations'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)
    log_id = db.Column(db.Integer, db.ForeignKey('chatbot_logs.id'), nullable=True)
    issue_summary = db.Column(db.Text, nullable=True)
    escalation_reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), default='escalated')
    created_at = db.Column(db.DateTime, default=get_current_time)
    resolved_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "log_id": self.log_id,
            "issue_summary": self.issue_summary,
            "escalation_reason": self.escalation_reason,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None
        }
