"""Shared test fixtures for common-auth unit tests.

All tests mock firebase_admin and firestore so no live Firebase connection is needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_firebase_init():
    """Prevent real Firebase initialization during tests."""
    with patch("common_auth.firebase_init.init_firebase") as mock_init:
        mock_init.return_value = None
        yield mock_init


@pytest.fixture
def mock_firestore():
    """Return a MagicMock that stands in for a firestore.Client.

    Tests configure .collection().document().get() chains as needed.
    """
    client = MagicMock()
    with patch("common_auth.firebase_init.get_firestore", return_value=client):
        yield client


@pytest.fixture
def mock_verify_token():
    """Mock firebase_admin.auth.verify_id_token to return a fake decoded token."""
    def _fake_verify(token, check_revoked=True, clock_skew_seconds=0):
        if token == "valid-token":
            return {"uid": "test-uid-123", "email": "test@example.com"}
        if token == "expired-token":
            raise Exception("Token expired")
        if token == "revoked-token":
            raise Exception("Token revoked")
        raise Exception("Invalid token")
    with patch("firebase_admin.auth.verify_id_token", side_effect=_fake_verify):
        yield _fake_verify


def make_doc(data: dict | None):
    """Create a mock Firestore document snapshot."""
    doc = MagicMock()
    doc.exists = data is not None
    doc.to_dict.return_value = data
    return doc
