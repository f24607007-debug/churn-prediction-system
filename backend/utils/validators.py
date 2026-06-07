from __future__ import annotations

def validate_query(query: str, max_len: int = 2000) -> tuple[bool, str]:
    if not isinstance(query, str) or not query.strip():
        return False, "Query must be a non-empty string."
    if len(query.strip()) > max_len:
        return False, f"Query must be under {max_len} characters."
    return True, ""


def validate_user_id(user_id) -> tuple[bool, str]:
    try:
        uid = int(user_id)
        if uid <= 0:
            return False, "user_id must be a positive integer."
        return True, ""
    except (TypeError, ValueError):
        return False, "user_id must be an integer."


def validate_confidence(confidence) -> tuple[bool, str]:
    try:
        c = float(confidence)
        if not (0.0 <= c <= 1.0):
            return False, "confidence must be between 0.0 and 1.0."
        return True, ""
    except (TypeError, ValueError):
        return False, "confidence must be a number."
