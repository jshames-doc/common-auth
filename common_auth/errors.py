"""Custom exception classes for the common-auth package."""

from __future__ import annotations


class AuthError(Exception):
    """Base exception for authentication failures."""


class PermissionDeniedError(AuthError):
    """User is authenticated but not allowed to access a resource."""


class QuotaExceededError(AuthError):
    """User has exceeded their daily token quota."""


class UsageLimitExceededError(QuotaExceededError):
    """Alias for QuotaExceededError — used when daily token limit is hit."""
