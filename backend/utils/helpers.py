from __future__ import annotations

from datetime import datetime, timezone


def get_current_time_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_response(status: str = "success", data=None, message: str = "") -> dict:
    # Use 'is not None' so falsy-but-valid values ([], 0, False) are preserved
    # rather than silently replaced with {}.
    return {
        "status": status,
        "data": data if data is not None else {},
        "message": message,
    }
