"""User lookup helpers backed by Firestore users/{uid} documents."""

from __future__ import annotations

from typing import Any

from common_auth import firebase_init
from common_auth.config import default_daily_token_limit


def get_user(uid: str) -> dict[str, Any] | None:
    """Return the users/{uid} document as a dict, or None if it doesn't exist."""
    db = firebase_init.get_firestore()
    doc = db.collection("users").document(uid).get()
    if not doc.exists:
        return None
    return doc.to_dict()


def is_active(uid: str) -> bool:
    """Return True if the user exists and active == True."""
    user = get_user(uid)
    if user is None:
        return False
    return bool(user.get("active", False))


def get_limits(uid: str) -> dict[str, Any]:
    """Return the user's limits, with defaults for missing fields.

    Returns:
        {'daily_token_limit': int} — defaults to 100000 if the user doc
        or the field is missing.
    """
    user = get_user(uid)
    if user is None:
        return {"daily_token_limit": default_daily_token_limit()}
    return {
        "daily_token_limit": user.get("daily_token_limit", default_daily_token_limit()),
    }
