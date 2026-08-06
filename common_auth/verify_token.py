"""Verify Firebase ID tokens using the Admin SDK."""

from __future__ import annotations

from typing import Any

from firebase_admin import auth

from common_auth import firebase_init
from common_auth.errors import AuthError


def verify_firebase_token(id_token: str) -> dict[str, str]:
    """Verify a Firebase ID token and return the user's uid and email.

    Args:
        id_token: A Firebase ID token from the client SDK (Authorization: Bearer <token>).

    Returns:
        A dict with keys 'uid' and 'email'.

    Raises:
        AuthError: if the token is invalid, expired, or revoked.
    """
    firebase_init.init_firebase()
    try:
        decoded: dict[str, Any] = auth.verify_id_token(
            id_token, check_revoked=True, clock_skew_seconds=30
        )
    except Exception as exc:
        raise AuthError(f"Invalid or expired Firebase token: {exc}") from exc

    uid = decoded.get("uid")
    email = decoded.get("email")
    if not uid:
        raise AuthError("Token is missing 'uid' claim.")
    return {"uid": uid, "email": email or ""}
