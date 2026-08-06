"""Unit tests for common_auth.users (get_user, is_active, get_limits)."""

from __future__ import annotations

from tests.conftest import make_doc


class TestGetUser:
    def test_returns_dict_when_doc_exists(self, mock_firestore):
        data = {"uid": "u1", "email": "a@b.com", "active": True, "role": "admin"}
        mock_firestore.collection.return_value.document.return_value.get.return_value = make_doc(data)
        from common_auth.users import get_user
        result = get_user("u1")
        assert result == data

    def test_returns_none_when_doc_missing(self, mock_firestore):
        mock_firestore.collection.return_value.document.return_value.get.return_value = make_doc(None)
        from common_auth.users import get_user
        assert get_user("missing") is None


class TestIsActive:
    def test_active_user(self, mock_firestore):
        mock_firestore.collection.return_value.document.return_value.get.return_value = make_doc(
            {"active": True, "role": "user"}
        )
        from common_auth.users import is_active
        assert is_active("u1") is True

    def test_inactive_user(self, mock_firestore):
        mock_firestore.collection.return_value.document.return_value.get.return_value = make_doc(
            {"active": False, "role": "user"}
        )
        from common_auth.users import is_active
        assert is_active("u1") is False

    def test_missing_user(self, mock_firestore):
        mock_firestore.collection.return_value.document.return_value.get.return_value = make_doc(None)
        from common_auth.users import is_active
        assert is_active("ghost") is False

    def test_no_active_field(self, mock_firestore):
        mock_firestore.collection.return_value.document.return_value.get.return_value = make_doc(
            {"role": "user"}
        )
        from common_auth.users import is_active
        assert is_active("u1") is False


class TestGetLimits:
    def test_returns_limit_from_doc(self, mock_firestore):
        mock_firestore.collection.return_value.document.return_value.get.return_value = make_doc(
            {"daily_token_limit": 50000}
        )
        from common_auth.users import get_limits
        assert get_limits("u1") == {"daily_token_limit": 50000}

    def test_returns_default_when_field_missing(self, mock_firestore):
        mock_firestore.collection.return_value.document.return_value.get.return_value = make_doc(
            {"role": "user"}
        )
        from common_auth.users import get_limits
        assert get_limits("u1") == {"daily_token_limit": 100000}

    def test_returns_default_when_user_missing(self, mock_firestore):
        mock_firestore.collection.return_value.document.return_value.get.return_value = make_doc(None)
        from common_auth.users import get_limits
        assert get_limits("ghost") == {"daily_token_limit": 100000}
