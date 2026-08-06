"""Initialize the Firebase Admin SDK and expose a cached Firestore client.

Call get_firestore() once at app startup; it initializes Firebase exactly once
per process and returns a shared firestore.Client.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore

from common_auth.config import get_config

logger = logging.getLogger(__name__)

_initialized = False


def _load_credentials() -> credentials.Certificate:
    """Build a Certificate from env vars (JSON string or file path)."""
    config = get_config()
    if config.credentials_json:
        return credentials.Certificate(json.loads(config.credentials_json))
    if config.credentials_path:
        return credentials.Certificate(config.credentials_path)
    # Fall back to Application Default Credentials (works on Cloud Run).
    logger.info("No explicit Firebase credentials found; using Application Default Credentials.")
    return None  # type: ignore[return-value]


def init_firebase() -> None:
    """Initialize the Firebase Admin SDK exactly once per process."""
    global _initialized
    if _initialized or firebase_admin._apps:
        _initialized = True
        return

    config = get_config()
    cert = _load_credentials()
    opts: dict[str, Any] = {"projectId": config.project_id}
    if cert is not None:
        firebase_admin.initialize_app(cert, opts)
    else:
        firebase_admin.initialize_app(options=opts)
    _initialized = True
    logger.info("Firebase Admin SDK initialized for project %s", config.project_id)


def get_firestore() -> firestore.Client:
    """Return a cached Firestore client, initializing Firebase if needed."""
    init_firebase()
    return firestore.client()


def reset_for_testing() -> None:
    """Reset the initialization flag so tests can re-initialize with new creds."""
    global _initialized
    for app_name in list(firebase_admin._apps.keys()):
        firebase_admin.delete_app(firebase_admin._apps[app_name])
    _initialized = False
