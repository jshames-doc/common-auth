"""Flask adapter — provides a decorator that verifies Firebase tokens
and checks user status + app permission before allowing a request.

Usage:
    from common_auth.adapters.flask_auth import login_required

    @app.route("/api/interpret", methods=["POST"])
    @login_required(os.environ["APP_ID"])
    def interpret():
        uid = flask.request.user.uid
        ...
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable

from flask import jsonify, request

from common_auth import firebase_init
from common_auth.errors import AuthError
from common_auth.permissions import can_access_app
from common_auth.users import is_active
from common_auth.verify_token import verify_firebase_token


@dataclass
class UserContext:
    """The authenticated user context attached to flask.request.user after auth succeeds."""

    uid: str
    email: str
    app_id: str


def _extract_bearer_token() -> str | None:
    """Pull the Firebase ID token from the Authorization: Bearer <token> header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header[len("Bearer "):].strip()


def _error_response(status: int, error: str, message: str) -> Any:
    """Return a Flask JSON error response."""
    return jsonify({"error": error, "message": message}), status


def login_required(app_id: str) -> Callable[..., Callable[..., Any]]:
    """Return a decorator that authenticates the request for the given app.

    Args:
        app_id: The app identifier (e.g. "neuro_exam").

    Returns:
        A decorator that wraps the view function. On success, attaches
        `request.user` as a UserContext. On failure, returns a 401/403 JSON response.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            firebase_init.init_firebase()
            token = _extract_bearer_token()
            if not token:
                return _error_response(401, "AUTH_REQUIRED", "Missing or invalid Authorization header.")

            try:
                identity = verify_firebase_token(token)
            except AuthError as exc:
                return _error_response(401, "INVALID_TOKEN", str(exc))

            uid = identity["uid"]
            email = identity["email"]

            if not is_active(uid):
                return _error_response(403, "USER_DISABLED", "This account is disabled.")

            if not can_access_app(uid, app_id):
                return _error_response(403, "ACCESS_DENIED", f"Access to {app_id} is not allowed.")

            request.user = UserContext(uid=uid, email=email, app_id=app_id)
            return func(*args, **kwargs)

        return wrapper

    return decorator
