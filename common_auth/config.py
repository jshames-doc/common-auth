"""Configuration for the common-auth package.

Reads from environment variables:
- APP_ID: the identifier for the current app (e.g. "medical_summarizer").
- FIREBASE_CREDENTIALS_JSON: service account JSON as a string (preferred for Cloud Run).
- FIREBASE_CREDENTIALS_PATH: path to a service account JSON file (for local dev).
- FIREBASE_PROJECT_ID: GCP project ID (defaults to the one in the service account).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_PROJECT_ID = "gen-lang-client-0026629090"
_DEFAULT_DAILY_TOKEN_LIMIT = 100_000


@dataclass(frozen=True)
class AuthConfig:
    """Resolved configuration for the auth package."""

    app_id: str
    project_id: str
    credentials_json: str | None
    credentials_path: str | None


def get_config() -> AuthConfig:
    """Build an AuthConfig from environment variables.

    Raises:
        ValueError: if APP_ID is not set.
    """
    app_id = os.environ.get("APP_ID", "").strip()
    if not app_id:
        raise ValueError("APP_ID environment variable is not set.")
    return AuthConfig(
        app_id=app_id,
        project_id=os.environ.get("FIREBASE_PROJECT_ID", DEFAULT_PROJECT_ID).strip(),
        credentials_json=os.environ.get("FIREBASE_CREDENTIALS_JSON"),
        credentials_path=os.environ.get("FIREBASE_CREDENTIALS_PATH"),
    )


def default_daily_token_limit() -> int:
    """Return the default daily token limit when a user doc has no limit set."""
    return _DEFAULT_DAILY_TOKEN_LIMIT
