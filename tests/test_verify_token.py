"""Unit tests for common_auth.verify_token.verify_firebase_token."""

from __future__ import annotations

import pytest

from common_auth.errors import AuthError
from common_auth.verify_token import verify_firebase_token


class TestVerifyFirebaseToken:
    def test_valid_token_returns_uid_and_email(self, mock_verify_token):
        result = verify_firebase_token("valid-token")
        assert result["uid"] == "test-uid-123"
        assert result["email"] == "test@example.com"

    def test_expired_token_raises_auth_error(self, mock_verify_token):
        with pytest.raises(AuthError, match="Invalid or expired Firebase token"):
            verify_firebase_token("expired-token")

    def test_revoked_token_raises_auth_error(self, mock_verify_token):
        with pytest.raises(AuthError, match="Invalid or expired Firebase token"):
            verify_firebase_token("revoked-token")

    def test_malformed_token_raises_auth_error(self, mock_verify_token):
        with pytest.raises(AuthError, match="Invalid or expired Firebase token"):
            verify_firebase_token("garbage")

    def test_empty_token_raises_auth_error(self, mock_verify_token):
        with pytest.raises(AuthError, match="Invalid or expired Firebase token"):
            verify_firebase_token("")
