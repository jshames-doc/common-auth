"""Shared Firebase authentication and Gemini usage tracking package."""

from common_auth.errors import (
    AuthError,
    PermissionDeniedError,
    QuotaExceededError,
    UsageLimitExceededError,
)
from common_auth.verify_token import verify_firebase_token
from common_auth.users import get_user, is_active, get_limits
from common_auth.permissions import can_access_app
from common_auth.usage import log_gemini_usage, check_usage_limit

__version__ = "0.1.0"

__all__ = [
    "verify_firebase_token",
    "get_user",
    "is_active",
    "get_limits",
    "can_access_app",
    "log_gemini_usage",
    "check_usage_limit",
    "AuthError",
    "PermissionDeniedError",
    "QuotaExceededError",
    "UsageLimitExceededError",
    "__version__",
]
