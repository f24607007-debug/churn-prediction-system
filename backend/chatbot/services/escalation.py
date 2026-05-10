import os

# Load configuration
CONFIDENCE_THRESHOLD = float(os.environ.get('CONFIDENCE_THRESHOLD', '0.75'))

def should_escalate(confidence_score: float) -> bool:
    """
    Determines if a query should be escalated based on the strict threshold.
    """
    return confidence_score < CONFIDENCE_THRESHOLD

def get_escalation_message() -> str:
    """Returns the standard fallback message when confidence is low."""
    return "I'm not entirely sure how to help with that. Let me connect you to an agent."
