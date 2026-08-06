"""Unit tests for common_auth.usage (log_gemini_usage, check_usage_limit, _estimate_cost)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from common_auth.errors import UsageLimitExceededError
from common_auth.usage import _estimate_cost, log_gemini_usage, check_usage_limit
from tests.conftest import make_doc


class TestEstimateCost:
    def test_known_model(self):
        cost = _estimate_cost("gemini-3.1-flash-lite", 1000, 1000)
        assert cost == pytest.approx(0.000075 + 0.0003)

    def test_unknown_model_uses_default(self):
        cost = _estimate_cost("unknown-model", 1000, 1000)
        assert cost == pytest.approx(0.0001 + 0.0004)

    def test_zero_tokens(self):
        assert _estimate_cost("gemini-3.1-flash-lite", 0, 0) == 0.0


class TestLogGeminiUsage:
    def test_writes_correct_fields(self, mock_firestore):
        mock_collection = MagicMock()
        mock_firestore.collection.return_value = mock_collection

        log_gemini_usage(
            uid="u1",
            app_id="medical_summarizer",
            model="gemini-3.1-flash-lite",
            input_tokens=2500,
            output_tokens=900,
            success=True,
        )

        mock_collection.add.assert_called_once()
        written = mock_collection.add.call_args[0][0]
        assert written["uid"] == "u1"
        assert written["app"] == "medical_summarizer"
        assert written["model"] == "gemini-3.1-flash-lite"
        assert written["input_tokens"] == 2500
        assert written["output_tokens"] == 900
        assert written["total_tokens"] == 3400
        assert written["success"] is True
        assert written["error"] is None
        assert "estimated_cost_usd" in written
        assert "timestamp" in written

    def test_logs_error_on_failure(self, mock_firestore):
        mock_collection = MagicMock()
        mock_firestore.collection.return_value = mock_collection

        log_gemini_usage(
            uid="u1",
            app_id="medical_summarizer",
            model="gemini-3.1-flash-lite",
            input_tokens=100,
            output_tokens=0,
            success=False,
            error="Gemini API timeout",
        )

        written = mock_collection.add.call_args[0][0]
        assert written["success"] is False
        assert written["error"] == "Gemini API timeout"


class TestCheckUsageLimit:
    def test_under_limit_returns_true(self, mock_firestore):
        # User doc with limit 100000
        user_doc = make_doc({"daily_token_limit": 100000, "role": "user"})
        # Usage docs summing to 50000
        usage_docs = [make_doc({"total_tokens": 30000}), make_doc({"total_tokens": 20000})]

        mock_query = MagicMock()
        mock_query.stream.return_value = iter(usage_docs)

        def _collection(name):
            m = MagicMock()
            if name == "users":
                m.document.return_value.get.return_value = user_doc
            elif name == "usage_logs":
                m.where.return_value.where.return_value = mock_query
            return m

        mock_firestore.collection.side_effect = _collection
        assert check_usage_limit("u1", "medical_summarizer") is True

    def test_over_limit_raises(self, mock_firestore):
        user_doc = make_doc({"daily_token_limit": 100000, "role": "user"})
        usage_docs = [make_doc({"total_tokens": 60000}), make_doc({"total_tokens": 50000})]

        mock_query = MagicMock()
        mock_query.stream.return_value = iter(usage_docs)

        def _collection(name):
            m = MagicMock()
            if name == "users":
                m.document.return_value.get.return_value = user_doc
            elif name == "usage_logs":
                m.where.return_value.where.return_value = mock_query
            return m

        mock_firestore.collection.side_effect = _collection
        with pytest.raises(UsageLimitExceededError, match="Daily token limit"):
            check_usage_limit("u1", "medical_summarizer")

    def test_no_usage_returns_true(self, mock_firestore):
        user_doc = make_doc({"daily_token_limit": 100000, "role": "user"})
        mock_query = MagicMock()
        mock_query.stream.return_value = iter([])

        def _collection(name):
            m = MagicMock()
            if name == "users":
                m.document.return_value.get.return_value = user_doc
            elif name == "usage_logs":
                m.where.return_value.where.return_value = mock_query
            return m

        mock_firestore.collection.side_effect = _collection
        assert check_usage_limit("u1", "medical_summarizer") is True

    def test_missing_user_uses_default_limit(self, mock_firestore):
        user_doc = make_doc(None)
        usage_docs = [make_doc({"total_tokens": 50000})]

        mock_query = MagicMock()
        mock_query.stream.return_value = iter(usage_docs)

        def _collection(name):
            m = MagicMock()
            if name == "users":
                m.document.return_value.get.return_value = user_doc
            elif name == "usage_logs":
                m.where.return_value.where.return_value = mock_query
            return m

        mock_firestore.collection.side_effect = _collection
        # 50000 < 100000 (default) → should pass
        assert check_usage_limit("ghost", "medical_summarizer") is True
