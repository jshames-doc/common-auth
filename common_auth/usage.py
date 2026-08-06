"""Gemini usage logging and quota enforcement backed by Firestore usage_logs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from common_auth import firebase_init
from common_auth.config import default_daily_token_limit
from common_auth.errors import UsageLimitExceededError
from common_auth.users import get_user

# Per-model cost table (USD per 1K tokens). Update with real pricing as needed.
COST_PER_1K: dict[str, dict[str, float]] = {
    "gemini-3.1-flash-lite": {"input": 0.000075, "output": 0.0003},
    "gemini-3-flash": {"input": 0.0001, "output": 0.0004},
    "gemini-2.5-flash": {"input": 0.0001, "output": 0.0004},
    "_default": {"input": 0.0001, "output": 0.0004},
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate the USD cost of a Gemini call based on the cost table."""
    rates = COST_PER_1K.get(model, COST_PER_1K["_default"])
    return (input_tokens / 1000) * rates["input"] + (output_tokens / 1000) * rates["output"]


def _start_of_today_utc() -> datetime:
    """Return the start of the current day in UTC (midnight)."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def log_gemini_usage(
    uid: str,
    app_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    success: bool,
    error: str | None = None,
) -> None:
    """Append a usage log document to the usage_logs collection.

    Args:
        uid: Firebase user ID.
        app_id: The app identifier (e.g. "medical_summarizer").
        model: Gemini model name (e.g. "gemini-3.1-flash-lite").
        input_tokens: Prompt token count from usage_metadata.
        output_tokens: Candidates token count from usage_metadata.
        success: Whether the Gemini call succeeded.
        error: Sanitized error message (no prompts, responses, or keys).
    """
    db = firebase_init.get_firestore()
    total_tokens = input_tokens + output_tokens
    estimated_cost = _estimate_cost(model, input_tokens, output_tokens)
    db.collection("usage_logs").add({
        "uid": uid,
        "app": app_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(estimated_cost, 6),
        "success": success,
        "error": error,
    })


def check_usage_limit(uid: str, app_id: str) -> bool:
    """Return True if the user is under their daily token limit.

    Sums total_tokens from usage_logs for today (UTC) for this uid and compares
    to the user's daily_token_limit. If the user doc is missing, uses the default
    limit.

    Raises:
        UsageLimitExceededError: if the user is over their daily limit.
    """
    user = get_user(uid)
    if user is not None:
        limit = user.get("daily_token_limit", default_daily_token_limit())
    else:
        limit = default_daily_token_limit()

    db = firebase_init.get_firestore()
    start_of_day = _start_of_today_utc().isoformat()
    query = (
        db.collection("usage_logs")
        .where("uid", "==", uid)
        .where("timestamp", ">=", start_of_day)
    )
    total = sum(doc.to_dict().get("total_tokens", 0) for doc in query.stream())
    if total >= limit:
        raise UsageLimitExceededError(
            f"Daily token limit ({limit}) exceeded for user {uid}."
        )
    return True
