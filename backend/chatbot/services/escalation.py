from __future__ import annotations


def should_escalate(confidence_score: float, threshold: float = 0.75) -> bool:
    """Return True when confidence is below *threshold*."""
    return confidence_score < threshold


def get_escalation_message() -> str:
    return "I'm not entirely sure how to help with that. Let me connect you to an agent."
