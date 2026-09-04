"""Unit tests for the FastAPI adapter (common_auth.adapters.fastapi_auth).

Uses fastapi.TestClient with mocked verify_token / Firestore so no live Firebase.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from common_auth.adapters.fastapi_auth import UserContext, build_auth_check_router, require_user


def _build_test_app(app_id: str) -> FastAPI:
    """Create a minimal FastAPI app with a protected route for testing."""
    app = FastAPI()

    @app.get("/protected")
    async def protected(user: UserContext = Depends(require_user(app_id))):
        return {"uid": user.uid, "email": user.email, "app_id": user.app_id}

    @app.get("/public")
    async def public():
        return {"status": "ok"}

    return app


@pytest.fixture
def mock_auth():
    """Mock the full auth chain: verify_token, is_active, can_access_app."""
    with (
        patch("common_auth.adapters.fastapi_auth.verify_firebase_token") as mock_verify,
        patch("common_auth.adapters.fastapi_auth.is_active") as mock_active,
        patch("common_auth.adapters.fastapi_auth.can_access_app") as mock_access,
        patch("common_auth.adapters.fastapi_auth.firebase_init.init_firebase") as mock_init,
    ):
        mock_init.return_value = None
        mock_verify.return_value = {"uid": "u1", "email": "test@example.com"}
        mock_active.return_value = True
        mock_access.return_value = True
        yield {
            "verify": mock_verify,
            "active": mock_active,
            "access": mock_access,
            "init": mock_init,
        }


class TestFastAPIAdapter:
    def test_valid_token_returns_user_context(self, mock_auth):
        app = _build_test_app("medical_summarizer")
        client = TestClient(app)
        resp = client.get(
            "/protected",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["uid"] == "u1"
        assert body["email"] == "test@example.com"
        assert body["app_id"] == "medical_summarizer"

    def test_missing_auth_header_returns_401(self, mock_auth):
        app = _build_test_app("medical_summarizer")
        client = TestClient(app)
        resp = client.get("/protected")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "AUTH_REQUIRED"

    def test_invalid_token_returns_401(self, mock_auth):
        from common_auth.errors import AuthError
        mock_auth["verify"].side_effect = AuthError("Token expired")
        app = _build_test_app("medical_summarizer")
        client = TestClient(app)
        resp = client.get(
            "/protected",
            headers={"Authorization": "Bearer bad-token"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "INVALID_TOKEN"

    def test_inactive_user_returns_403(self, mock_auth):
        mock_auth["active"].return_value = False
        app = _build_test_app("medical_summarizer")
        client = TestClient(app)
        resp = client.get(
            "/protected",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"] == "USER_DISABLED"

    def test_no_app_permission_returns_403(self, mock_auth):
        mock_auth["access"].return_value = False
        app = _build_test_app("medical_summarizer")
        client = TestClient(app)
        resp = client.get(
            "/protected",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"] == "ACCESS_DENIED"

    def test_public_route_not_protected(self, mock_auth):
        app = _build_test_app("medical_summarizer")
        client = TestClient(app)
        resp = client.get("/public")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def _build_check_app(app_id: str) -> FastAPI:
    """Create a FastAPI app that mounts the /auth/check router."""
    app = FastAPI()
    app.include_router(build_auth_check_router(app_id))
    return app


class TestAuthCheckRouter:
    def test_valid_token_returns_ok(self, mock_auth):
        app = _build_check_app("clinical_dictation")
        client = TestClient(app)
        resp = client.get(
            "/auth/check",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["uid"] == "u1"
        assert body["email"] == "test@example.com"
        assert body["app_id"] == "clinical_dictation"

    def test_missing_auth_header_returns_401(self, mock_auth):
        app = _build_check_app("clinical_dictation")
        client = TestClient(app)
        resp = client.get("/auth/check")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "AUTH_REQUIRED"

    def test_inactive_user_returns_403(self, mock_auth):
        mock_auth["active"].return_value = False
        app = _build_check_app("clinical_dictation")
        client = TestClient(app)
        resp = client.get(
            "/auth/check",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"] == "USER_DISABLED"

    def test_no_app_permission_returns_403(self, mock_auth):
        mock_auth["access"].return_value = False
        app = _build_check_app("clinical_dictation")
        client = TestClient(app)
        resp = client.get(
            "/auth/check",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"] == "ACCESS_DENIED"
