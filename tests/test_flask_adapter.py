"""Unit tests for the Flask adapter (common_auth.adapters.flask_auth).

Uses flask test client with mocked verify_token / Firestore so no live Firebase.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from flask import Flask

from common_auth.adapters.flask_auth import login_required


def _build_test_app(app_id: str) -> Flask:
    """Create a minimal Flask app with a protected route for testing."""
    app = Flask(__name__)

    @app.route("/protected", methods=["GET"])
    @login_required(app_id)
    def protected():
        from flask import request as req
        return {"uid": req.user.uid, "email": req.user.email, "app_id": req.user.app_id}

    @app.route("/public", methods=["GET"])
    def public():
        return {"status": "ok"}

    return app


@pytest.fixture
def mock_auth():
    """Mock the full auth chain: verify_token, is_active, can_access_app."""
    with (
        patch("common_auth.adapters.flask_auth.verify_firebase_token") as mock_verify,
        patch("common_auth.adapters.flask_auth.is_active") as mock_active,
        patch("common_auth.adapters.flask_auth.can_access_app") as mock_access,
        patch("common_auth.adapters.flask_auth.firebase_init.init_firebase") as mock_init,
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


class TestFlaskAdapter:
    def test_valid_token_returns_user_context(self, mock_auth):
        app = _build_test_app("neuro_exam")
        with app.test_client() as client:
            resp = client.get(
                "/protected",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["uid"] == "u1"
            assert body["email"] == "test@example.com"
            assert body["app_id"] == "neuro_exam"

    def test_missing_auth_header_returns_401(self, mock_auth):
        app = _build_test_app("neuro_exam")
        with app.test_client() as client:
            resp = client.get("/protected")
            assert resp.status_code == 401
            assert resp.get_json()["error"] == "AUTH_REQUIRED"

    def test_invalid_token_returns_401(self, mock_auth):
        from common_auth.errors import AuthError
        mock_auth["verify"].side_effect = AuthError("Token expired")
        app = _build_test_app("neuro_exam")
        with app.test_client() as client:
            resp = client.get(
                "/protected",
                headers={"Authorization": "Bearer bad-token"},
            )
            assert resp.status_code == 401
            assert resp.get_json()["error"] == "INVALID_TOKEN"

    def test_inactive_user_returns_403(self, mock_auth):
        mock_auth["active"].return_value = False
        app = _build_test_app("neuro_exam")
        with app.test_client() as client:
            resp = client.get(
                "/protected",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert resp.status_code == 403
            assert resp.get_json()["error"] == "USER_DISABLED"

    def test_no_app_permission_returns_403(self, mock_auth):
        mock_auth["access"].return_value = False
        app = _build_test_app("neuro_exam")
        with app.test_client() as client:
            resp = client.get(
                "/protected",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert resp.status_code == 403
            assert resp.get_json()["error"] == "ACCESS_DENIED"

    def test_public_route_not_protected(self, mock_auth):
        app = _build_test_app("neuro_exam")
        with app.test_client() as client:
            resp = client.get("/public")
            assert resp.status_code == 200
            assert resp.get_json() == {"status": "ok"}
