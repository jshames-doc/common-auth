"""Unit tests for common_auth.permissions.can_access_app."""

from __future__ import annotations

from tests.conftest import make_doc


class TestCanAccessApp:
    def test_admin_bypasses_app_check(self, mock_firestore):
        # Admin user — should return True without checking app_access
        mock_firestore.collection.return_value.document.return_value.get.return_value = make_doc(
            {"role": "admin", "active": True}
        )
        from common_auth.permissions import can_access_app
        assert can_access_app("admin-uid", "medical_summarizer") is True

    def test_allowed_user(self, mock_firestore):
        # Non-admin user with allowed app_access doc
        user_doc = make_doc({"role": "user", "active": True})
        access_doc = make_doc({"allowed": True})

        def _document(doc_id):
            if doc_id == "user-uid":
                return MagicMock(get=MagicMock(return_value=user_doc))
            return MagicMock(get=MagicMock(return_value=access_doc))

        mock_firestore.collection.side_effect = lambda name: MagicMock(document=MagicMock(side_effect=_document))
        from common_auth.permissions import can_access_app
        from unittest.mock import MagicMock
        assert can_access_app("user-uid", "medical_summarizer") is True

    def test_denied_user_no_access_doc(self, mock_firestore):
        from unittest.mock import MagicMock
        user_doc = make_doc({"role": "user", "active": True})
        no_doc = make_doc(None)

        def _document(doc_id):
            if doc_id == "user-uid":
                return MagicMock(get=MagicMock(return_value=user_doc))
            return MagicMock(get=MagicMock(return_value=no_doc))

        mock_firestore.collection.side_effect = lambda name: MagicMock(document=MagicMock(side_effect=_document))
        from common_auth.permissions import can_access_app
        assert can_access_app("user-uid", "medical_summarizer") is False

    def test_denied_user_allowed_false(self, mock_firestore):
        from unittest.mock import MagicMock
        user_doc = make_doc({"role": "user", "active": True})
        access_doc = make_doc({"allowed": False})

        def _document(doc_id):
            if doc_id == "user-uid":
                return MagicMock(get=MagicMock(return_value=user_doc))
            return MagicMock(get=MagicMock(return_value=access_doc))

        mock_firestore.collection.side_effect = lambda name: MagicMock(document=MagicMock(side_effect=_document))
        from common_auth.permissions import can_access_app
        assert can_access_app("user-uid", "medical_summarizer") is False

    def test_missing_user_denied(self, mock_firestore):
        mock_firestore.collection.return_value.document.return_value.get.return_value = make_doc(None)
        from common_auth.permissions import can_access_app
        assert can_access_app("ghost", "medical_summarizer") is False
