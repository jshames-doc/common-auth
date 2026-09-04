"""FastAPI adapter — provides a dependency that verifies Firebase tokens
and checks user status + app permission before allowing a request.

Usage:
    from common_auth.adapters.fastapi_auth import require_user
    from fastapi import Depends

    user = Depends(require_user(os.environ["APP_ID"]))

    @app.post("/extract")
    async def extract(payload: ExtractRequest, user: UserContext):
        ...
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request

from common_auth import firebase_init
from common_auth.errors import AuthError, UsageLimitExceededError
from common_auth.permissions import can_access_app
from common_auth.users import is_active
from common_auth.verify_token import verify_firebase_token


@dataclass
class UserContext:
    """The authenticated user context attached to a request after auth succeeds."""

    uid: str
    email: str
    app_id: str


def _extract_bearer_token(request: Request) -> str:
    """Pull the Firebase ID token from the Authorization: Bearer <token> header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"error": "AUTH_REQUIRED", "message": "Missing or invalid Authorization header."},
        )
    return auth_header[len("Bearer "):].strip()


def require_user(app_id: str) -> Callable[..., UserContext]:
    """Return a FastAPI dependency that authenticates the request for the given app.

    Args:
        app_id: The app identifier (e.g. "medical_summarizer").

    Returns:
        A dependency callable that reads the Bearer token, verifies it via
        Firebase, checks the user is active and has app permission, and returns
        a UserContext.
    """

    def _dependency(request: Request) -> UserContext:
        firebase_init.init_firebase()
        token = _extract_bearer_token(request)

        try:
            identity = verify_firebase_token(token)
        except AuthError as exc:
            raise HTTPException(
                status_code=401,
                detail={"error": "INVALID_TOKEN", "message": str(exc)},
            ) from exc

        uid = identity["uid"]
        email = identity["email"]

        if not is_active(uid):
            raise HTTPException(
                status_code=403,
                detail={"error": "USER_DISABLED", "message": "This account is disabled."},
            )

        if not can_access_app(uid, app_id):
            raise HTTPException(
                status_code=403,
                detail={"error": "ACCESS_DENIED", "message": f"Access to {app_id} is not allowed."},
            )

        return UserContext(uid=uid, email=email, app_id=app_id)

    return _dependency


def build_auth_check_router(app_id: str) -> APIRouter:
    """Return an APIRouter exposing a lightweight GET /auth/check endpoint.

    The route runs the same checks as ``require_user(app_id)`` (token verify,
    active user, app permission) but does NOT call any downstream service
    (e.g. Gemini). This lets a frontend verify access immediately after
    Firebase login, independent of AI availability.

    Returns:
        An APIRouter with a single ``GET /auth/check`` route. On success it
        responds ``200 {"ok": true, "uid", "email", "app_id"}``. On failure
        the dependency raises ``401`` (missing/invalid token) or ``403``
        (``USER_DISABLED`` / ``ACCESS_DENIED``) — identical to ``require_user``.
    """
    router = APIRouter()

    @router.get("/auth/check", response_model=None)
    async def auth_check(
        user: UserContext = Depends(require_user(app_id)),
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "uid": user.uid,
            "email": user.email,
            "app_id": user.app_id,
        }

    return router
